"""Run reproducible A/B evaluations for recommendation-card prompts.

Raw MinerU inputs and full model outputs are written to a private directory outside
the repository. The committed report contains aggregate scores and source hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse


SEVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SEVER_ROOT.parent
if str(SEVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SEVER_ROOT))

from config.recommend_card_prompts import (  # noqa: E402
    ACTIVE_GENERATION_VERSION,
    GENERATION_CANDIDATES,
    LEGACY_REFINEMENT_LIMITS,
    LEGACY_REFINEMENT_PROMPTS,
    REFINEMENT_CANDIDATES,
)
from services.recommend_card_prompt_eval import (  # noqa: E402
    FIELD_LABELS,
    FIELD_ORDER,
    JUDGE_SYSTEM_PROMPT,
    aggregate_version_scores,
    build_judge_user_prompt,
    combine_scores,
    deterministic_report,
    extract_json_object,
    parse_card,
    promotion_table,
)


DEFAULT_REPORT = REPO_ROOT / "docs" / "recommend_card_prompt_ab_results.md"
DEFAULT_LEDGER = REPO_ROOT / "docs" / "recommend_card_prompt_ab_ledger.json"
DEFAULT_PRIVATE_ROOT = (
    Path(os.environ.get("CODEX_VISUALIZATION_ROOT", ""))
    if os.environ.get("CODEX_VISUALIZATION_ROOT")
    else Path.home() / ".codex" / "private_eval" / "recommend_card_prompt"
)

GENERATION_ROUNDS = (
    "g1_field_contracts",
    "g2_evidence_ladder",
    "g3_type_aware_dedup",
    "g4_current_type_guard",
    "g5_theory_branch_minimal",
    "g6_theory_exception_only",
)
REFINEMENT_ROUNDS = (
    "r1_field_limits",
    "r2_evidence_preservation",
    "r3_type_aware_dedup",
)
REFINEMENT_DRAFT_VERSION = "zero"
EVALUATOR_VERSION = 6
JUDGE_VERSION = "deepseek-v4-pro-nonthinking-calibrated-v2"


def _read_secret_env(name: str) -> str:
    """Read a secret from the process env, then the current Windows user env.

    Windows desktop applications do not see user environment changes made after
    they start. Reading ``HKCU\\Environment`` lets an already-open Codex session
    use the newly configured value without copying it into source or arguments.
    """
    value = str(os.environ.get(name, "") or "").strip()
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            stored, _ = winreg.QueryValueEx(key, name)
        return str(stored or "").strip()
    except (FileNotFoundError, OSError):
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sample_manifest(sample_root: Path) -> Dict[str, list[Dict[str, Any]]]:
    manifest: Dict[str, list[Dict[str, Any]]] = {"dev": [], "holdout": []}
    for split in manifest:
        folder = sample_root / split
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            manifest[split].append(
                {
                    "paper_id": path.stem,
                    "sha256": _sha256(path),
                    "bytes": path.stat().st_size,
                }
            )
    return manifest


def _make_deepseek_client() -> Tuple[Any, Dict[str, Any], Dict[str, Any]]:
    from openai import OpenAI

    api_key = _read_secret_env("DEEPSEEK_API_KEY")
    # This experiment is explicitly authorized only for DeepSeek's official API.
    # Keep the destination constant instead of accepting a user-controlled URL.
    base_url = "https://api.deepseek.com"
    if not api_key:
        raise SystemExit(
            "DEEPSEEK_API_KEY is required; do not put the key in source code or CLI arguments"
        )
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or parsed.hostname != "api.deepseek.com":
        raise RuntimeError("invalid hardcoded DeepSeek endpoint")
    # Do not use the user-URL factory here: local proxy software resolves public
    # domains to RFC 2544 fake-IP addresses (198.18/15), which that SSRF guard
    # correctly rejects for user-controlled targets. The exact HTTPS destination
    # above is code-controlled and allowlisted, so it cannot be redirected by input.
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=180.0, max_retries=0)
    generator_cfg = {
        "provider": "DeepSeek",
        "base_url": base_url,
        "model": "deepseek-v4-flash",
        "temperature": 0.0,
        "max_tokens": 4096,
        "thinking": False,
    }
    judge_cfg = {
        "provider": "DeepSeek",
        "base_url": base_url,
        "model": "deepseek-v4-pro",
        "temperature": 0.0,
        "max_tokens": 4096,
        "thinking": False,
    }
    return client, generator_cfg, judge_cfg


def _choice_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "").strip()


def _complete(
    client: Any,
    model_cfg: Mapping[str, Any],
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: Optional[int] = None,
    json_mode: bool = False,
    retries: int = 3,
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    last_error: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            request: Dict[str, Any] = {
                "model": model_cfg["model"],
                "messages": messages,
                "max_tokens": int(max_tokens or model_cfg["max_tokens"]),
                "stream": False,
                "extra_body": {
                    "thinking": {
                        "type": "enabled" if model_cfg.get("thinking") else "disabled"
                    }
                },
            }
            if model_cfg.get("thinking"):
                request["reasoning_effort"] = model_cfg.get("reasoning_effort", "high")
            elif model_cfg.get("temperature") is not None:
                request["temperature"] = float(model_cfg["temperature"])
            if json_mode:
                request["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(
                **request,
            )
            text = _choice_text(response)
            if text:
                return text
            raise ValueError("empty completion")
        except Exception as exc:  # pragma: no cover - network/provider path
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM completion failed after {retries} attempts: {last_error!r}")


def _zero_user_prompt(source_text: str) -> str:
    return (
        "请从下面论文中直接抽取八项内容：中文短标题、推荐理由、研究问题、主要贡献、"
        "重点思路、分析总结、个人观点、一句话记忆。使用中文并标明字段名。\n\n"
        f"{source_text}"
    )


def _generate(
    client: Any,
    model_cfg: Mapping[str, Any],
    *,
    version: str,
    source_text: str,
) -> str:
    prompt = GENERATION_CANDIDATES[version]
    if version == "zero":
        return _complete(
            client,
            model_cfg,
            system_prompt="",
            user_prompt=_zero_user_prompt(source_text),
        )
    return _complete(
        client,
        model_cfg,
        system_prompt=prompt,
        user_prompt=source_text,
    )


def _legacy_refine(
    client: Any,
    model_cfg: Mapping[str, Any],
    *,
    draft: str,
) -> str:
    """Approximate the currently deployed multi-call compression for the A/B baseline."""
    card = parse_card(draft)
    values: Dict[str, Any] = {
        "headline": card.short_title,
        "intro": f"🔸研究问题：{card.research_question}\n🔸主要贡献：{card.main_contribution}",
        "key_ideas": "\n".join(f"🔸{item}" for item in card.key_ideas),
        "analysis_summary": "\n".join(f"🔸{item}" for item in card.analysis_summary),
        "personal_opinion": card.personal_opinion,
    }
    for key, prompt in LEGACY_REFINEMENT_PROMPTS.items():
        text = str(values.get(key, "") or "").strip()
        if not text:
            continue
        if len(re.sub(r"\s+", "", text)) <= LEGACY_REFINEMENT_LIMITS[key]:
            continue
        values[key] = _complete(
            client,
            model_cfg,
            system_prompt=prompt,
            user_prompt=text,
            max_tokens=2048,
        )

    headline = str(values["headline"] or card.short_title).strip()
    if "：" in headline:
        headline = headline.split("：", 1)[1].strip()
    intro = parse_card(
        "🛎️文章简介\n" + str(values["intro"] or "") + "\n📝重点思路\n"
    )
    key_ideas = parse_card(
        "📝重点思路\n" + str(values["key_ideas"] or "") + "\n🔎分析总结\n"
    ).key_ideas
    analysis_summary = parse_card(
        "🔎分析总结\n" + str(values["analysis_summary"] or "") + "\n💡个人观点\n"
    ).analysis_summary
    card.short_title = headline or card.short_title
    card.research_question = intro.research_question or card.research_question
    card.main_contribution = intro.main_contribution or card.main_contribution
    card.key_ideas = key_ideas or card.key_ideas
    card.analysis_summary = analysis_summary or card.analysis_summary
    card.personal_opinion = str(values["personal_opinion"] or card.personal_opinion).strip()
    from services.recommend_card_prompt_eval import render_card

    return render_card(card)


def _refine(
    client: Any,
    model_cfg: Mapping[str, Any],
    *,
    version: str,
    draft: str,
) -> str:
    if version == "legacy":
        return _legacy_refine(client, model_cfg, draft=draft)
    return _complete(
        client,
        model_cfg,
        system_prompt=REFINEMENT_CANDIDATES[version],
        user_prompt=draft,
    )


def _blind_label(seed: int, *parts: str) -> str:
    joined = "|".join(parts)
    digest = hashlib.sha256(f"{seed}|{joined}".encode("utf-8")).hexdigest()
    return f"candidate-{digest[:8]}"


def _judge(
    client: Any,
    model_cfg: Mapping[str, Any],
    *,
    paper_id: str,
    source_text: str,
    candidate_text: str,
    stage: str,
    refinement_input: str = "",
) -> Dict[str, Any]:
    user_prompt = build_judge_user_prompt(
        paper_id=paper_id,
        source_text=source_text,
        candidate_text=candidate_text,
        stage=stage,
        refinement_input=refinement_input,
    )
    last_error: Optional[BaseException] = None
    for attempt in range(3):
        retry_note = ""
        if attempt:
            retry_note = (
                "\n\n上一次响应不是完整合法的JSON。本次必须检查所有引号、逗号和括号，"
                "八个字段都填写完后再结束输出。"
            )
        reply = _complete(
            client,
            model_cfg,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            user_prompt=user_prompt + retry_note,
            max_tokens=int(model_cfg.get("max_tokens") or 8192),
            json_mode=True,
        )
        try:
            return extract_json_object(reply)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
    raise RuntimeError(f"judge returned invalid JSON after 3 attempts: {last_error!r}")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _version_score_store(root: Path, stage: str, split: str) -> Path:
    return root / "scores" / f"{stage}_{split}.json"


def _run_generation_split(
    *,
    client: Any,
    generator_cfg: Mapping[str, Any],
    judge_cfg: Mapping[str, Any],
    sample_root: Path,
    output_root: Path,
    split: str,
    versions: Sequence[str],
    seed: int,
    workers: int,
) -> Dict[str, Dict[str, Any]]:
    score_path = _version_score_store(output_root, "generation", split)
    scores: Dict[str, Dict[str, Any]] = _read_json(score_path, {})
    samples = sorted((sample_root / split).glob("*.md"))
    tasks = [
        (version, path, dict(scores.get(version, {}).get(path.stem, {})))
        for version in versions
        for path in samples
        if scores.get(version, {}).get(path.stem, {}).get("evaluator_version")
        != EVALUATOR_VERSION
    ]
    random.Random(seed).shuffle(tasks)

    def evaluate(task: Tuple[str, Path, Dict[str, Any]]) -> Tuple[str, str, Dict[str, Any]]:
        version, path, existing = task
        paper_id = path.stem
        output_file = output_root / "outputs" / "generation" / split / version / f"{paper_id}.md"
        source_text = path.read_text(encoding="utf-8", errors="ignore")
        if output_file.is_file():
            candidate = output_file.read_text(encoding="utf-8", errors="ignore")
        else:
            candidate = _generate(
                client, generator_cfg, version=version, source_text=source_text
            )
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(candidate, encoding="utf-8")
        deterministic = deterministic_report(candidate, source_text=source_text)
        judge = (
            existing.get("judge")
            if existing.get("judge_version") == JUDGE_VERSION
            else None
        ) or _judge(
            client,
            judge_cfg,
            paper_id=paper_id,
            source_text=source_text,
            candidate_text=candidate,
            stage="生成",
        )
        combined = combine_scores(judge_result=judge, deterministic=deterministic)
        combined["evaluator_version"] = EVALUATOR_VERSION
        combined["judge_version"] = JUDGE_VERSION
        combined["blind_label"] = _blind_label(seed, "generation", split, version, paper_id)
        return version, paper_id, combined

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = {executor.submit(evaluate, task): task for task in tasks}
        for future in as_completed(futures):
            version, path, _ = futures[future]
            try:
                result_version, paper_id, combined = future.result()
            except Exception as exc:
                message = f"{version}/{path.stem}: {exc!r}"
                errors.append(message)
                print(f"[generation/{split}] ERROR {message}", flush=True)
                continue
            scores.setdefault(result_version, {})[paper_id] = combined
            _write_json(score_path, scores)
            print(
                f"[generation/{split}] {result_version} {paper_id}: {combined['score']}",
                flush=True,
            )
    if errors:
        raise RuntimeError("generation evaluation failures: " + "; ".join(errors))
    return scores


def _run_refinement_split(
    *,
    client: Any,
    generator_cfg: Mapping[str, Any],
    judge_cfg: Mapping[str, Any],
    sample_root: Path,
    output_root: Path,
    split: str,
    draft_version: str,
    versions: Sequence[str],
    seed: int,
    workers: int,
) -> Dict[str, Dict[str, Any]]:
    score_path = _version_score_store(output_root, "refinement", split)
    scores: Dict[str, Dict[str, Any]] = _read_json(score_path, {})
    samples = sorted((sample_root / split).glob("*.md"))
    tasks = [
        (version, path, dict(scores.get(version, {}).get(path.stem, {})))
        for version in versions
        for path in samples
        if (
            scores.get(version, {}).get(path.stem, {}).get("evaluator_version")
            != EVALUATOR_VERSION
            or scores.get(version, {}).get(path.stem, {}).get("draft_version")
            != draft_version
        )
    ]
    random.Random(seed + 17).shuffle(tasks)

    def evaluate(task: Tuple[str, Path, Dict[str, Any]]) -> Tuple[str, str, Dict[str, Any]]:
        version, path, existing = task
        paper_id = path.stem
        source_text = path.read_text(encoding="utf-8", errors="ignore")
        generation_file = (
            output_root / "outputs" / "generation" / split / draft_version / f"{paper_id}.md"
        )
        if not generation_file.is_file():
            raise FileNotFoundError(f"missing generation draft: {generation_file}")
        draft = generation_file.read_text(encoding="utf-8", errors="ignore")
        output_file = (
            output_root
            / "outputs"
            / "refinement"
            / split
            / draft_version
            / version
            / f"{paper_id}.md"
        )
        if output_file.is_file():
            candidate = output_file.read_text(encoding="utf-8", errors="ignore")
        else:
            candidate = _refine(client, generator_cfg, version=version, draft=draft)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(candidate, encoding="utf-8")
        deterministic = deterministic_report(
            candidate,
            source_text=source_text,
            refinement_input=draft,
        )
        judge = (
            existing.get("judge")
            if (
                existing.get("judge_version") == JUDGE_VERSION
                and existing.get("draft_version") == draft_version
            )
            else None
        ) or _judge(
            client,
            judge_cfg,
            paper_id=paper_id,
            source_text=source_text,
            candidate_text=candidate,
            stage="精简",
            refinement_input=draft,
        )
        combined = combine_scores(judge_result=judge, deterministic=deterministic)
        combined["evaluator_version"] = EVALUATOR_VERSION
        combined["judge_version"] = JUDGE_VERSION
        combined["draft_version"] = draft_version
        combined["blind_label"] = _blind_label(seed, "refinement", split, version, paper_id)
        return version, paper_id, combined

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = {executor.submit(evaluate, task): task for task in tasks}
        for future in as_completed(futures):
            version, path, _ = futures[future]
            try:
                result_version, paper_id, combined = future.result()
            except Exception as exc:
                message = f"{version}/{path.stem}: {exc!r}"
                errors.append(message)
                print(f"[refinement/{split}] ERROR {message}", flush=True)
                continue
            scores.setdefault(result_version, {})[paper_id] = combined
            _write_json(score_path, scores)
            print(
                f"[refinement/{split}] {result_version} {paper_id}: {combined['score']}",
                flush=True,
            )
    if errors:
        raise RuntimeError("refinement evaluation failures: " + "; ".join(errors))
    return scores


def _select_champion(rows: Sequence[Mapping[str, Any]], baseline: str) -> str:
    return str(rows[-1]["champion_after"]) if rows else baseline


def _field_delta_rows(
    scores: Mapping[str, Mapping[str, Mapping[str, Any]]],
    baseline: str,
    champion: str,
) -> list[Tuple[str, float, float, float]]:
    base = aggregate_version_scores(scores.get(baseline, {}))
    winner = aggregate_version_scores(scores.get(champion, {}))
    return [
        (
            FIELD_LABELS[key],
            float(base["field_scores"][key]),
            float(winner["field_scores"][key]),
            round(float(winner["field_scores"][key]) - float(base["field_scores"][key]), 2),
        )
        for key in FIELD_ORDER
    ]


def _markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(out)


def _build_report(ledger: Mapping[str, Any]) -> str:
    generation_rows = ledger["generation"]["rounds"]
    refinement_rows = ledger["refinement"]["rounds"]
    generation_versions = ledger["generation"]["version_scores"]
    zero_score = generation_versions["zero"]["score"]
    current_score = generation_versions["current"]["score"]
    generation_champion = ledger["generation"]["champion"]
    champion_score = generation_versions[generation_champion]["score"]
    type1_rows: list[Tuple[Any, ...]] = [
        ("A 无系统提示词", "zero", zero_score, "+0.00"),
        (
            "B 现有系统提示词",
            "current",
            current_score,
            f"{current_score - zero_score:+.2f}",
        ),
    ]
    if generation_champion != "current":
        type1_rows.append(
            (
                "B 冻结冠军",
                generation_champion,
                champion_score,
                f"{champion_score - zero_score:+.2f}",
            )
        )
    holdout = ledger.get("holdout", {})
    sample_rows = []
    for split, items in ledger["samples"].items():
        for item in items:
            sample_rows.append((split, item["paper_id"], item["bytes"], item["sha256"][:12]))

    def round_rows(rows: Sequence[Mapping[str, Any]]) -> list[Tuple[Any, ...]]:
        return [
            (
                row["round"],
                row["baseline"],
                row["challenger"],
                row["baseline_score"],
                row["challenger_score"],
                f"{row['delta']:+.2f}",
                f"{row['wins']}/{row['paper_count']}",
                f"{row['factuality_delta']:+.2f}",
                f"{row['worst_field']} {row['worst_field_delta']:+.2f}",
                "晋级" if row["promoted"] else "保留基线",
            )
            for row in rows
        ]

    report = [
        "# 推荐卡片提示词 A/B 实验记录",
        "",
        f"- 运行时间（UTC）：{ledger['run']['finished_at']}",
        f"- 生成模型：`{ledger['run']['generation_model']}`（非思考模式，temperature={ledger['run']['generation_temperature']}）",
        f"- 盲评模型：`{ledger['run']['judge_model']}`（非思考、严格 JSON 模式）",
        "- 原始 MinerU 文件与完整模型输出保存在仓库外；本文件只提交哈希、聚合分数和晋级结论。",
        "- 开发集用于逐轮迭代；隐藏留出集只在冠军冻结后打开并评测。",
        "",
        "## 样本清单",
        "",
        _markdown_table(("划分", "论文 ID", "字节", "SHA-256 前缀"), sample_rows),
        "",
        "## 固定评分与晋级规则",
        "",
        "每个字段按事实与可追溯性35、字段职责20、信息价值20、精简度15、跨字段不重复10评分；LLM盲评占80%，确定性检查占20%。出现主要幻觉或来源不存在的数字时总分封顶59，缺少字段时封顶69。挑战者须同时满足：开发集均分至少提高3分、至少赢2/3篇、事实性不下降、任一字段均分不下降超过5分；平局保留现任基线。",
        "",
        "## 生成环节",
        "",
        "### 类型 1：无系统提示词 vs 有提示词",
        "",
        _markdown_table(
            ("候选", "版本", "开发集均分", "相对无提示词"),
            type1_rows,
        ),
        "",
        "### 类型 2：当前基线 vs 新提示词",
        "",
        _markdown_table(
            ("轮", "A 基线", "B 挑战者", "A分", "B分", "差值", "胜篇", "事实差", "最差字段", "结论"),
            round_rows(generation_rows),
        ),
        "",
        f"生成冠军：`{ledger['generation']['champion']}`。冻结零提示基线：`zero`。",
        "",
        _markdown_table(
            ("字段", "现有提示词", "冠军", "变化"),
            ledger["generation"]["field_deltas"],
        ),
        "",
        "## 精简环节",
        "",
        f"压力输入固定为同一批 `{ledger['refinement']['draft_version']}` 长草稿；旧逻辑和所有新提示词处理完全相同的内容。",
        "",
        _markdown_table(
            ("轮", "A 基线", "B 挑战者", "A分", "B分", "差值", "胜篇", "事实差", "最差字段", "结论"),
            round_rows(refinement_rows),
        ),
        "",
        f"精简冠军：`{ledger['refinement']['champion']}`。",
        "",
        _markdown_table(
            ("字段", "现有精简", "冠军", "变化"),
            ledger["refinement"]["field_deltas"],
        ),
        "",
        "## 隐藏留出集",
        "",
    ]
    if holdout:
        report.extend(
            [
                _markdown_table(
                    ("环节", "旧基线", "旧分", "冠军", "冠军分", "变化"),
                    (
                        (
                            "生成",
                            "zero",
                            holdout["generation"]["zero_score"],
                            "current",
                            holdout["generation"]["baseline_score"],
                            f"{holdout['generation']['prompt_delta']:+.2f}",
                        ),
                        (
                            "精简",
                            "legacy",
                            holdout["refinement"]["baseline_score"],
                            ledger["refinement"]["champion"],
                            holdout["refinement"]["champion_score"],
                            f"{holdout['refinement']['delta']:+.2f}",
                        ),
                    ),
                ),
                "",
                f"留出集结论：{holdout['decision']}。",
            ]
        )
    else:
        report.append("尚未运行隐藏留出集。")
    report.extend(
        [
            "",
            "## 解释限制",
            "",
            "样本量很小，分数用于在固定模型与固定论文集上做工程选择，不代表普适的人类偏好估计。生成器与自动评审均使用同一模型家族，可能存在风格偏好；确定性校验、隐藏留出集和晋级护栏用于降低但不能消除这一风险。",
            "",
        ]
    )
    return "\n".join(report)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    sample_root = args.sample_root.resolve()
    output_root = args.private_output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    samples = _sample_manifest(sample_root)
    if len(samples["dev"]) < 3:
        raise SystemExit("at least 3 dev MinerU markdown files are required")
    if args.include_holdout and len(samples["holdout"]) < 2:
        raise SystemExit("at least 2 holdout MinerU markdown files are required")

    client, generator_cfg, judge_cfg = _make_deepseek_client()
    started_at = datetime.now(timezone.utc).isoformat()

    generation_versions = ("zero", "current", *GENERATION_ROUNDS)
    generation_dev = _run_generation_split(
        client=client,
        generator_cfg=generator_cfg,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="dev",
        versions=generation_versions,
        seed=args.seed,
        workers=args.workers,
    )
    generation_rounds = promotion_table(
        generation_dev,
        baseline="current",
        challengers=GENERATION_ROUNDS,
        zero_version="zero",
    )
    generation_champion = _select_champion(generation_rounds, "current")

    refinement_versions = ("legacy", *REFINEMENT_ROUNDS)
    refinement_dev = _run_refinement_split(
        client=client,
        generator_cfg=generator_cfg,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="dev",
        draft_version=REFINEMENT_DRAFT_VERSION,
        versions=refinement_versions,
        seed=args.seed,
        workers=args.workers,
    )
    refinement_rounds = promotion_table(
        refinement_dev,
        baseline="legacy",
        challengers=REFINEMENT_ROUNDS,
    )
    refinement_champion = _select_champion(refinement_rounds, "legacy")

    ledger: Dict[str, Any] = {
        "schema_version": 2,
        "run": {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "seed": args.seed,
            "generation_model": generator_cfg["model"],
            "judge_model": judge_cfg["model"],
            "base_url_host": "api.deepseek.com",
            "generation_temperature": generator_cfg["temperature"],
            "generation_thinking": generator_cfg["thinking"],
            "judge_thinking": judge_cfg["thinking"],
            "judge_weight": 0.8,
            "deterministic_weight": 0.2,
        },
        "samples": samples,
        "generation": {
            "rounds": generation_rounds,
            "champion": generation_champion,
            "version_scores": {
                key: aggregate_version_scores(value) for key, value in generation_dev.items()
            },
            "field_deltas": _field_delta_rows(
                generation_dev, "current", generation_champion
            ),
            "zero_comparison": {
                "zero_score": aggregate_version_scores(generation_dev["zero"])["score"],
                "current_score": aggregate_version_scores(generation_dev["current"])["score"],
                "delta": round(
                    aggregate_version_scores(generation_dev["current"])["score"]
                    - aggregate_version_scores(generation_dev["zero"])["score"],
                    2,
                ),
            },
        },
        "refinement": {
            "draft_version": REFINEMENT_DRAFT_VERSION,
            "rounds": refinement_rounds,
            "champion": refinement_champion,
            "version_scores": {
                key: aggregate_version_scores(value) for key, value in refinement_dev.items()
            },
            "field_deltas": _field_delta_rows(
                refinement_dev, "legacy", refinement_champion
            ),
        },
    }

    if args.include_holdout:
        generation_holdout = _run_generation_split(
            client=client,
            generator_cfg=generator_cfg,
            judge_cfg=judge_cfg,
            sample_root=sample_root,
            output_root=output_root,
            split="holdout",
            versions=tuple(dict.fromkeys((REFINEMENT_DRAFT_VERSION, "current", generation_champion))),
            seed=args.seed,
            workers=args.workers,
        )
        refinement_holdout = _run_refinement_split(
            client=client,
            generator_cfg=generator_cfg,
            judge_cfg=judge_cfg,
            sample_root=sample_root,
            output_root=output_root,
            split="holdout",
            draft_version=REFINEMENT_DRAFT_VERSION,
            versions=("legacy", refinement_champion),
            seed=args.seed,
            workers=args.workers,
        )
        gen_base = aggregate_version_scores(generation_holdout["current"])
        gen_zero = aggregate_version_scores(generation_holdout["zero"])
        gen_winner = aggregate_version_scores(generation_holdout[generation_champion])
        ref_base = aggregate_version_scores(refinement_holdout["legacy"])
        ref_winner = aggregate_version_scores(refinement_holdout[refinement_champion])
        gen_delta = round(gen_winner["score"] - gen_base["score"], 2)
        ref_delta = round(ref_winner["score"] - ref_base["score"], 2)
        holdout_passed = (
            gen_delta >= 0
            and ref_delta >= 0
            and gen_winner["factuality_score"] >= gen_base["factuality_score"]
            and ref_winner["factuality_score"] >= ref_base["factuality_score"]
        )
        ledger["holdout"] = {
            "generation": {
                "zero_score": gen_zero["score"],
                "baseline_score": gen_base["score"],
                "champion_score": gen_winner["score"],
                "delta": gen_delta,
                "prompt_delta": round(gen_base["score"] - gen_zero["score"], 2),
            },
            "refinement": {
                "baseline_score": ref_base["score"],
                "champion_score": ref_winner["score"],
                "delta": ref_delta,
            },
            "passed": holdout_passed,
            "decision": "冠军通过，允许集成" if holdout_passed else "冠军未通过，不应集成",
        }

    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.ledger, ledger)
    args.report.write_text(_build_report(ledger), encoding="utf-8")
    return ledger


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser("recommend_card_prompt_ab")
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, default=DEFAULT_PRIVATE_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--include-holdout", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    result = run(parse_args())
    print(
        json.dumps(
            {
                "generation_champion": result["generation"]["champion"],
                "refinement_champion": result["refinement"]["champion"],
                "holdout": result.get("holdout", {}),
            },
            ensure_ascii=False,
        )
    )
