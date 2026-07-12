"""Controlled A/B evaluation for the paper-assets extraction prompt.

Uses one configured fixed model, one source document and an anonymized judge.
It prints only scores, judge feedback and the winning reader-facing fields; no
credentials or full prompts are written to disk.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Controller.paper_assets import ensure_blocks_structure, parse_json_from_text
from config.config import (
    paper_assets_system_prompt,
    summary_apikey_3,
    summary_base_url_2,
    summary_base_url_3,
    summary_gptgod_apikey,
    summary_model_2,
    summary_model_3,
)
from services.llm_client_factory import build_llm_client


READER_QUALITY_CONTRACT = """

【沉浸阅读内容质量契约】
这些字段会直接展示给研究者，不是内部草稿。请遵守：
1. 专用字段必须各司其职，禁止把多个概念混在同一条：
   - research_questions 只写论文要回答的问题；
   - claimed_contributions 只写作者声称新增了什么；
   - main_findings 写论文观察到的主要结论；
   - numerical_results 写“对象/数据集 + 指标 + 数值 + 对照”；
   - phenomena 写可观察现象；mechanism_explanations 写作者解释或推断，并标明证据强弱；
   - scope_boundaries、threats_to_validity、generalization_limits 分别写适用范围、有效性威胁、外推限制。
2. text 仅作本块 1 句导航（不超过 60 个汉字）；bullets 仅在专用字段无法承载时使用。不得在 text、bullets、专用字段中重复同一事实。
3. 每条只表达一个可独立理解的事实。优先写“做了什么—在什么条件下—得到什么证据”，不要写“效果显著、表现优秀、具有价值”等空话。
4. 数值结果必须带比较对象和指标；缺一项时明确写“原文未给出”，不得补猜。
5. claimed_contributions 不得伪装成已证实结论；机制解释若非直接验证，明确写“作者解释”或“推断”。
6. 每个数组保留 1–4 条高信息密度内容；单条尽量不超过 80 个汉字。宁缺毋滥。
7. 表述使用清楚、自然、可扫描的中文，保留必要的模型名、数据集名与指标名。
"""


READER_QUALITY_EXAMPLES = """

【正反例约束】
- 差："模型在多个基准上显著提升。"
- 好："Gen-ViRe Avg 从 0.304 升至 0.391（+0.087，相对 Wan-CoF）。"
- 差："提出视觉/文本推理令牌机制，显著提升推理能力。"
- 好："贡献：提出 vt/tt 两类推理令牌；证据：消融显示二者相对无令牌基线均有增益。"
- 差：把“研究问题、目标、贡献”写在同一条。
- 好：research_questions 用问句；claimed_contributions 用“提出/构建/发布”；strongly_supported_claims 只保留有直接证据的结论。
- 差："泛化能力仍需验证。"
- 好："仅在 Wan2.2-I2V-A14B 上训练与评测，尚不能外推到其他视频生成骨干。"
"""


MINIMAL_PROMPT = """你是论文信息抽取器。仅依据输入文本输出合法 JSON，不要解释、不要 Markdown、不要猜测。
请填写下面 JSON 中的各部分；没有信息时保留空字符串、空数组或 null：
{schema}
所有描述使用中文，模型名、数据集名和指标名保留原文。"""


JUDGE_PROMPT = """你是严格的科研阅读产品编辑。比较同一来源生成的两个匿名结构化结果。
按以下权重给分，总分严格为 100：
1) 语义分离（20）：研究问题、贡献、方法、数据、评估、结果、机制、局限是否各自明确；
2) 具体性（20）：是否有对象、条件、指标、数值和对照，少用空话；
3) 证据忠实（20）：作者声称、直接证据、推断和边界是否区分；
4) 去重复（15）：text、bullets、专用字段是否避免重复；
5) 可读性（15）：每条是否原子化、简洁、能直接在沉浸页面展示；
6) 完整性（10）：来源中重要信息是否被覆盖且没有编造。
只输出 JSON：
{"a":{"total":0,"subscores":{}},"b":{"total":0,"subscores":{}},"winner":"a|b|tie","reasons":[],"next_improvements":[],"critical_issue":false}
若存在编造、字段严重混淆或 JSON 结构不可用，critical_issue=true。"""


VISIBLE_FIELDS = {
    "objective": ["research_questions", "claimed_contributions"],
    "method": ["architecture_or_paradigm", "key_mechanisms", "training_or_optimization", "inference_strategy", "novelty"],
    "data": ["datasets_or_materials", "data_source", "data_scale", "domain_scope"],
    "experiment_or_argumentation": ["design", "baselines_or_comparators", "variables_or_modules", "ablation_or_counterfactual"],
    "metrics": ["metric_names", "evaluation_protocol", "judge_or_annotation_method"],
    "results": ["main_findings", "numerical_results", "phenomena", "mechanism_explanations"],
    "limitations": ["scope_boundaries", "threats_to_validity", "generalization_limits"],
    "critical_analysis": ["strongest_argument", "weakest_argument", "needs_more_evidence", "reproduction_or_extension_priorities"],
}


def configured_client(slot: int, config_id: int | None = None, model_override: str = ""):
    if config_id is not None:
        from services import llm_config_service
        config = llm_config_service.get_config(config_id)
        if not config:
            raise SystemExit(f"LLM config {config_id} was not found")
        key = (config.get("api_key") or "").strip()
        base_url = (config.get("base_url") or "").strip()
        model = model_override.strip() or (config.get("model") or "").strip()
        if not key or not model:
            raise SystemExit(f"LLM config {config_id} is incomplete")
        return build_llm_client({"api_key": key, "base_url": base_url}), model
    if slot == 3:
        key, base_url, model = summary_apikey_3, summary_base_url_3, summary_model_3
    else:
        key, base_url, model = summary_gptgod_apikey, summary_base_url_2, summary_model_2
    if not key:
        raise SystemExit(f"model slot {slot} has no configured API key")
    return build_llm_client({"api_key": key, "base_url": base_url}), model_override.strip() or model


def fetch_source(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    summary = payload.get("summary") if isinstance(payload, dict) else payload
    return json.dumps(summary, ensure_ascii=False, indent=2)


def complete_json(
    client: Any,
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 16384,
    json_mode: bool = False,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        max_tokens=max_tokens,
        stream=False,
        **kwargs,
    )
    text = response.choices[0].message.content if response.choices else ""
    parsed = parse_json_from_text(text or "")
    if not isinstance(parsed, dict) or not parsed:
        finish_reason = response.choices[0].finish_reason if response.choices else "no_choice"
        raise RuntimeError(f"model returned no parseable JSON (finish_reason={finish_reason}, content_length={len(text or '')})")
    return parsed


def visible_projection(output: dict[str, Any]) -> dict[str, Any]:
    blocks = output.get("blocks") if isinstance(output.get("blocks"), dict) else output
    normalized = ensure_blocks_structure(blocks)
    return {
        block_name: {field: normalized.get(block_name, {}).get(field) for field in fields}
        for block_name, fields in VISIBLE_FIELDS.items()
    }


def judge(client: Any, model: str, source: str, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    payload = "来源：\n" + source + "\n\n候选 A：\n" + json.dumps(a, ensure_ascii=False)
    payload += "\n\n候选 B：\n" + json.dumps(b, ensure_ascii=False)
    return complete_json(client, model, JUDGE_PROMPT, payload, max_tokens=12000, json_mode=True)


def score_of(result: dict[str, Any], side: str) -> int:
    try:
        return int(result.get(side, {}).get("total", 0))
    except (TypeError, ValueError):
        return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--model-slot", type=int, choices=[2, 3], default=2)
    parser.add_argument("--llm-config-id", type=int)
    parser.add_argument("--model-override", default="")
    parser.add_argument("--max-rounds", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--satisfaction-score", type=int, default=88)
    args = parser.parse_args()

    client, model = configured_client(args.model_slot, args.llm_config_id, args.model_override)
    source = fetch_source(args.source_url)
    schema = json.dumps(ensure_blocks_structure({}), ensure_ascii=False)
    prompts = [
        ("minimal", MINIMAL_PROMPT.format(schema=schema)),
        ("current", paper_assets_system_prompt),
        ("reader_contract", paper_assets_system_prompt + READER_QUALITY_CONTRACT),
        ("reader_contract_examples", paper_assets_system_prompt + READER_QUALITY_CONTRACT + READER_QUALITY_EXAMPLES),
    ]
    prompts = prompts[: max(2, min(len(prompts), args.max_rounds + 1))]

    incumbent_name = prompts[0][0]
    print(f"[AB] generating {incumbent_name} with {model}", flush=True)
    incumbent = visible_projection(complete_json(
        client,
        model,
        prompts[0][1],
        "请根据系统提示词分析下面的论文摘要：\n\n" + source,
    ))
    reports = []
    for round_index, (challenger_name, challenger_prompt) in enumerate(prompts[1:], start=1):
        if round_index > args.max_rounds:
            break
        print(f"[AB] round {round_index}: generating {challenger_name}", flush=True)
        challenger = visible_projection(complete_json(
            client,
            model,
            challenger_prompt,
            "请根据系统提示词分析下面的论文摘要：\n\n" + source,
        ))
        print(f"[AB] round {round_index}: judging {incumbent_name} vs {challenger_name}", flush=True)
        report = judge(client, model, source, incumbent, challenger)
        winner = report.get("winner")
        if winner == "b" or (winner == "tie" and score_of(report, "b") > score_of(report, "a")):
            incumbent_name = challenger_name
            incumbent = challenger
            winning_score = score_of(report, "b")
        else:
            winning_score = score_of(report, "a")
        reports.append({
            "round": round_index,
            "a": reports[-1]["winner"] if reports else prompts[0][0],
            "b": challenger_name,
            "scores": {"a": score_of(report, "a"), "b": score_of(report, "b")},
            "winner": incumbent_name,
            "reasons": report.get("reasons", []),
            "next_improvements": report.get("next_improvements", []),
            "critical_issue": bool(report.get("critical_issue", False)),
        })
        if winning_score >= args.satisfaction_score and not report.get("critical_issue") and challenger_name.startswith("reader_contract"):
            break

    print(json.dumps({
        "model": model,
        "rounds": reports,
        "winner": incumbent_name,
        "winning_visible_fields": incumbent,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
