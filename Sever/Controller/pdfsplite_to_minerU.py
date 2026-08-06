import argparse
import json
import logging
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import List

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.config import PDF_PREVIEW_DIR, PREVIEW_MINERU_DIR, MANIFEST_FILENAME, minerU_Token  # noqa: E402
from services.mineru_api_support import (  # noqa: E402
    find_resumable_batch,
    load_batch_journal,
    request_json_with_rate_limit_retry,
    update_batch_journal,
)


def setup_logging():
    logger = logging.getLogger("pdf_mineru")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("[%(levelname)s] %(message)s")
        sh = logging.StreamHandler(stream=sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    logger.propagate = False
    return logger


def today_str() -> str:
    # Prefer RUN_DATE env so the correct date is used even when the clock has
    # advanced past midnight or sits in a different timezone from the scheduler.
    _run_date = os.environ.get("RUN_DATE", "").strip()
    if _run_date:
        return _run_date
    from datetime import datetime
    return datetime.now().date().isoformat()


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_latest_manifest(root_dir: Path) -> Path:
    if not root_dir.exists():
        raise FileNotFoundError(f"preview pdf dir not found: {root_dir}")
    latest = None
    latest_mtime = 0.0
    for p in root_dir.rglob(MANIFEST_FILENAME):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime >= latest_mtime:
            latest = p
            latest_mtime = mtime
    if not latest:
        raise FileNotFoundError(f"manifest not found in {root_dir}")
    return latest


def load_manifest(path: Path) -> tuple[List[dict], str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        obj = json.loads(text) if text.strip() else {}
    except Exception:
        obj = {}
    items = obj.get("items") if isinstance(obj, dict) else None
    items = items if isinstance(items, list) else []
    date_str = str(obj.get("date") or "")
    return items, date_str


def pick_first_md(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".md")]
        if not names:
            raise RuntimeError(f"no .md in zip: {zip_path}")
        names.sort(key=lambda s: (s.count("/"), len(s)))
        name = names[0]
        raw = zf.read(name)
    return raw.decode("utf-8", errors="replace")


def pick_preferred_json(zip_path: Path):
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".json")]
        if not names:
            raise RuntimeError(f"no .json in zip: {zip_path}")
        prefer = [n for n in names if n.lower().endswith("content_list.json")] or [n for n in names if n.lower().endswith("model.json")]
        cand = prefer or names
        cand.sort(key=lambda s: (s.count("/"), len(s)))
        name = cand[0]
        text = zf.read(name).decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        return text


class MinerUClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "*/*"})

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        return request_json_with_rate_limit_retry(
            self.session,
            "POST",
            url,
            payload=payload,
            max_attempts=int(os.environ.get("MINERU_API_MAX_ATTEMPTS", "6")),
            on_retry=lambda attempt, total, delay: print(
                f"[WARN] MinerU API 429，{delay:.0f}s 后重试 ({attempt}/{total})",
                flush=True,
            ),
        )

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        return request_json_with_rate_limit_retry(
            self.session,
            "GET",
            url,
            max_attempts=int(os.environ.get("MINERU_API_MAX_ATTEMPTS", "6")),
            on_retry=lambda attempt, total, delay: print(
                f"[WARN] MinerU API 429，{delay:.0f}s 后重试 ({attempt}/{total})",
                flush=True,
            ),
        )

    def apply_upload_urls(self, files: List[dict], model_version: str, extra: dict) -> dict:
        payload = {"files": files, "model_version": model_version}
        payload.update(extra or {})
        return self._post("/api/v4/file-urls/batch", payload)

    def get_batch_results(self, batch_id: str) -> dict:
        return self._get(f"/api/v4/extract-results/batch/{batch_id}")


def backoff_sleep(attempt: int, base: float = 1.0, cap: float = 10.0) -> None:
    time.sleep(min(cap, base * (2 ** (attempt - 1))))


def upload_to_presigned_url(file_path: Path, put_url: str, max_retries: int = 6) -> None:
    last: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with file_path.open("rb") as f:
                r = requests.put(put_url, data=f, timeout=(30, 900))
            r.raise_for_status()
            return
        except Exception as e:
            last = e
            backoff_sleep(attempt)
    raise RuntimeError(f"upload failed: {file_path.name}. last={last!r}")


def wait_batch_done(
    client: MinerUClient,
    batch_id: str,
    expected_total: int,
    timeout_sec: int = 900,
    poll_sec: int = 3,
    stall_timeout_sec: int = 180,
) -> List[dict]:
    """等待 MinerU 批次完成，含停滞检测。

    当 done+failed 计数在 stall_timeout_sec 内无进展，或达到 timeout_sec 绝对上限时，
    打印警告并返回当前结果，而非抛出异常，让调用方决定如何处理部分成功。
    """
    deadline = time.time() + timeout_sec
    last_progress = 0
    last_progress_time = time.time()
    last_items: List[dict] = []

    while time.time() < deadline:
        resp = client.get_batch_results(batch_id)
        data = resp.get("data") or {}
        items = data.get("extract_result") or []
        if not isinstance(items, list):
            items = []
        last_items = [it for it in items if isinstance(it, dict)]

        states: dict[str, int] = {}
        done_or_failed = 0
        for it in items:
            st = str(it.get("state") or "unknown").lower()
            states[st] = states.get(st, 0) + 1
            if st in ("done", "failed"):
                done_or_failed += 1
        print(f"\r[parse] {done_or_failed}/{expected_total} {states}", end="", flush=True)

        if expected_total > 0 and done_or_failed >= expected_total:
            print()
            return last_items

        # 记录进度变化时间，用于停滞检测
        if done_or_failed > last_progress:
            last_progress = done_or_failed
            last_progress_time = time.time()

        # 停滞检测：已有部分完成且长时间无新进展，优雅返回
        stalled_for = time.time() - last_progress_time
        if done_or_failed > 0 and stalled_for >= stall_timeout_sec:
            print()
            print(
                f"[WARN] MinerU batch 进度停滞 {stalled_for:.0f}s，"
                f"done+failed={done_or_failed}/{expected_total} {states}，"
                f"放弃等待剩余任务，继续后续步骤",
                flush=True,
            )
            return last_items

        time.sleep(poll_sec)

    # 绝对超时：返回已有结果而非抛异常
    print()
    done_or_failed_final = sum(1 for it in last_items if str(it.get("state") or "").lower() in ("done", "failed"))
    print(
        f"[WARN] MinerU batch 达到超时上限 {timeout_sec}s，"
        f"done+failed={done_or_failed_final}/{expected_total}，"
        f"放弃等待剩余任务，继续后续步骤",
        flush=True,
    )
    return last_items


def download_zip(zip_url: str, token: str, dest: Path, max_retries: int = 6) -> None:
    last: Exception | None = None
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(1, max_retries + 1):
        try:
            with requests.get(zip_url, headers=headers, stream=True, timeout=(30, 900)) as r:
                r.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            f.write(chunk)
            return
        except Exception as e:
            last = e
            backoff_sleep(attempt)
    raise RuntimeError(f"download zip failed. last={last!r}")


def write_pymupdf_fallback(
    pdfs: List[Path],
    out_root: Path,
    statuses: dict[str, str],
    logger: logging.Logger,
) -> list[str]:
    """Write plain-text Markdown when the external MinerU API cannot start.

    Preview PDFs only feed institution/abstract extraction, so preserving
    readable text is more important than preserving layout.  Failed or empty
    local extracts remain explicit in the manifest and are never counted as
    successful output.
    """
    try:
        import fitz  # type: ignore
    except ImportError:
        logger.warning("PyMuPDF fallback unavailable: fitz is not installed")
        return []

    written: list[str] = []
    for pdf_path in pdfs:
        md_path = out_root / f"{pdf_path.stem}.md"
        if md_path.is_file():
            continue
        doc = None
        try:
            doc = fitz.open(str(pdf_path))
            parts: list[str] = []
            for page in doc:
                page_text = page.get_text().strip()
                if page_text:
                    parts.append(page_text)
            text = "\n\n".join(parts).strip()
            if not text:
                statuses[pdf_path.stem] = "fallback_empty"
                continue
            md_path.write_text(text, encoding="utf-8")
            statuses[pdf_path.stem] = "fallback_pymupdf"
            written.append(pdf_path.stem)
        except Exception as exc:
            statuses[pdf_path.stem] = "fallback_failed"
            logger.warning(
                "PyMuPDF fallback failed for %s: %s",
                pdf_path.name,
                type(exc).__name__,
            )
        finally:
            if doc is not None:
                doc.close()
    return written


def run():
    logger = setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--date", default="")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--outdir", default=PREVIEW_MINERU_DIR)
    ap.add_argument("--base-url", default=os.environ.get("MINERU_BASE_URL", "https://mineru.net"))
    ap.add_argument("--model-version", default=os.environ.get("MINERU_MODEL_VERSION", "vlm"))
    ap.add_argument("--timeout-sec", type=int, default=900)
    ap.add_argument("--stall-timeout-sec", type=int, default=180)
    ap.add_argument("--poll-sec", type=int, default=3)
    ap.add_argument("--upload-retries", type=int, default=6)
    ap.add_argument("--min-success-ratio", type=float, default=0.0,
                    help="写入 manifest 后，若成功率低于此值则以 exit(1) 失败（默认 0.0 = 只要有 1 篇成功就继续）")
    args = ap.parse_args()

    token = (minerU_Token or "").strip()
    if not token:
        logger.warning("MinerU token is not configured; using local PyMuPDF fallback")

    root = Path(PDF_PREVIEW_DIR)
    manifest_items: List[dict] = []
    manifest_path: Path | None
    if args.manifest:
        manifest_path = Path(args.manifest)
    else:
        try:
            manifest_path = find_latest_manifest(root)
        except FileNotFoundError:
            manifest_path = None
    if manifest_path is not None and manifest_path.exists():
        manifest_items, manifest_date = load_manifest(manifest_path)
        date_str = manifest_date or manifest_path.parent.name
        pdfs = []
        for it in manifest_items:
            status = str(it.get("status") or "").lower()
            pdf_path = str(it.get("preview_pdf") or it.get("source_pdf") or "")
            if not pdf_path:
                continue
            if status and status not in ("created", "skipped"):
                continue
            p = Path(pdf_path)
            if p.exists():
                pdfs.append(p)
    else:
        if args.date:
            in_dir = root / args.date
            if not in_dir.is_dir():
                raise SystemExit(f"preview pdf dir not found: {in_dir}")
            date_str = args.date
        else:
            cand = []
            if root.exists():
                for d in root.iterdir():
                    if d.is_dir():
                        name = d.name
                        if len(name) == 10 and name[4] == "-" and name[7] == "-":
                            cand.append(d)
            if cand:
                cand.sort(key=lambda p: p.name)
                in_dir = cand[-1]
                date_str = in_dir.name
            else:
                in_dir = root
                date_str = today_str()
        pdfs = sorted(in_dir.glob("*.pdf"))
    if args.limit is not None:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        # Create an empty sentinel manifest so the idempotency check passes on
        # subsequent runs and downstream steps see "0 items" instead of nothing.
        out_root = ensure_dir(Path(args.outdir) / date_str)
        empty_manifest = out_root / MANIFEST_FILENAME
        empty_manifest.write_text(
            json.dumps({"date": date_str, "total": 0, "items": []}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"No preview PDFs found; wrote empty manifest to {empty_manifest}", flush=True)
        return

    print("============开始预览 PDF 的 MinerU 解析==============", flush=True)
    out_root = ensure_dir(Path(args.outdir) / date_str)
    tmp_zip_dir = ensure_dir(out_root / "_tmp_zip")

    pdfs_to_upload = [p for p in pdfs if not (out_root / f"{p.stem}.md").exists()]
    if not pdfs_to_upload:
        logger.info("All previews already converted, skip upload and parse")
        logger.info("Out dir: %s", str(out_root))
        manifest_path = out_root / MANIFEST_FILENAME
        manifest_payload = {
            "date": date_str,
            "total": len(pdfs),
            "items": [
                {
                    "arxiv_id": p.stem,
                    "preview_pdf": str(p),
                    "md_path": str(out_root / f"{p.stem}.md"),
                    "status": "skipped",
                }
                for p in pdfs
            ],
        }
        manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    BATCH_SIZE = 50
    client = MinerUClient(args.base_url, token)
    total = len(pdfs_to_upload)
    chunks = [pdfs_to_upload[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    logger.info("Total PDFs to upload: %d, split into %d batch(es) of up to %d", total, len(chunks), BATCH_SIZE)

    batch_journal_path = out_root / "_batch_state.json"
    batch_journal = load_batch_journal(batch_journal_path, date_str)
    statuses: dict[str, str] = {
        p.stem: "skipped" if (out_root / f"{p.stem}.md").exists() else "pending"
        for p in pdfs
    }
    wrote = 0
    uploaded_total = 0
    mineru_available = bool(token)
    for chunk_idx, chunk in enumerate(chunks):
        if not mineru_available:
            fallback_written = write_pymupdf_fallback(
                chunk, out_root, statuses, logger
            )
            wrote += len(fallback_written)
            continue

        chunk_ids = [p.stem for p in chunk]
        resumable = find_resumable_batch(batch_journal, chunk_ids)
        if resumable:
            batch_id = str(resumable["batch_id"])
            logger.info("[batch %d/%d] Resuming MinerU batch_id=%s", chunk_idx + 1, len(chunks), batch_id)
        else:
            logger.info("[batch %d/%d] Applying upload URLs for %d file(s)", chunk_idx + 1, len(chunks), len(chunk))
            files_payload = [{"name": p.name, "data_id": p.stem} for p in chunk]
            try:
                response = client.apply_upload_urls(
                    files_payload,
                    model_version=args.model_version,
                    extra={"return_images": True},
                )
                if response.get("code") != 0:
                    raise RuntimeError("MinerU rejected upload URL request")
                applied = response.get("data") or {}
                urls = applied.get("file_urls") or []
                batch_id = applied.get("batch_id") or ""
                if not batch_id or not urls or len(urls) != len(chunk):
                    raise RuntimeError("MinerU returned incomplete upload URL data")
            except Exception as exc:
                mineru_available = False
                logger.warning(
                    "MinerU upload URL request failed (%s); "
                    "falling back to local PyMuPDF for remaining previews",
                    type(exc).__name__,
                )
                fallback_written = write_pymupdf_fallback(
                    chunk, out_root, statuses, logger
                )
                wrote += len(fallback_written)
                continue
            update_batch_journal(
                batch_journal,
                batch_journal_path,
                batch_id=batch_id,
                file_ids=chunk_ids,
                status="applied",
            )

            try:
                for i, p in enumerate(chunk):
                    upload_to_presigned_url(p, urls[i], max_retries=args.upload_retries)
                    uploaded_total += 1
                    print(f"\r[upload] {uploaded_total}/{total}", end="", flush=True)
                print()
            except Exception as exc:
                mineru_available = False
                logger.warning(
                    "MinerU upload failed (%s); falling back to local PyMuPDF "
                    "for remaining previews",
                    type(exc).__name__,
                )
                fallback_written = write_pymupdf_fallback(
                    chunk, out_root, statuses, logger
                )
                wrote += len(fallback_written)
                update_batch_journal(
                    batch_journal,
                    batch_journal_path,
                    batch_id=batch_id,
                    file_ids=chunk_ids,
                    status="fallback",
                    written_ids=fallback_written,
                )
                continue
            update_batch_journal(
                batch_journal,
                batch_journal_path,
                batch_id=batch_id,
                file_ids=chunk_ids,
                status="uploaded",
            )
            print(f"[batch {chunk_idx + 1}/{len(chunks)}] 上传完成，开始等待 MinerU 解析", flush=True)

        try:
            chunk_results = wait_batch_done(
                client, batch_id, expected_total=len(chunk),
                timeout_sec=args.timeout_sec, poll_sec=args.poll_sec,
                stall_timeout_sec=args.stall_timeout_sec,
            )
        except Exception as exc:
            mineru_available = False
            logger.warning(
                "MinerU result wait failed (%s); falling back to local "
                "PyMuPDF for remaining previews",
                type(exc).__name__,
            )
            fallback_written = write_pymupdf_fallback(
                chunk, out_root, statuses, logger
            )
            wrote += len(fallback_written)
            update_batch_journal(
                batch_journal,
                batch_journal_path,
                batch_id=batch_id,
                file_ids=chunk_ids,
                status="fallback",
                written_ids=fallback_written,
            )
            continue
        by_name = {str(it.get("file_name") or ""): it for it in chunk_results}
        by_dataid = {str(it.get("data_id") or ""): it for it in chunk_results}
        batch_written: list[str] = []
        for p in chunk:
            it = by_dataid.get(p.stem) or by_name.get(p.name)
            if not it:
                print(f"[skip] no result item for {p.name}")
                statuses[p.stem] = "missing_result"
                continue
            state = str(it.get("state") or "").lower()
            if state != "done":
                print(f"[skip] {p.name} state={state}")
                statuses[p.stem] = f"state_{state}"
                continue
            zip_url = it.get("full_zip_url")
            if not zip_url:
                print(f"[skip] {p.name} has no full_zip_url")
                statuses[p.stem] = "no_zip_url"
                continue
            zip_path = tmp_zip_dir / f"{p.stem}.zip"
            try:
                download_zip(zip_url, token, zip_path)
                md_text = pick_first_md(zip_path)
                (out_root / f"{p.stem}.md").write_text(md_text, encoding="utf-8")
                wrote += 1
                batch_written.append(p.stem)
                statuses[p.stem] = "done"
                print(f"\r[write] {wrote}/{total}", end="", flush=True)
            except Exception as exc:
                statuses[p.stem] = "mineru_result_failed"
                logger.warning(
                    "MinerU result download failed for %s (%s); local fallback pending",
                    p.name,
                    type(exc).__name__,
                )
            finally:
                try:
                    zip_path.unlink()
                except OSError:
                    pass
        fallback_pdfs = [p for p in chunk if p.stem not in batch_written]
        fallback_written = write_pymupdf_fallback(
            fallback_pdfs, out_root, statuses, logger
        )
        wrote += len(fallback_written)
        batch_written.extend(fallback_written)
        update_batch_journal(
            batch_journal,
            batch_journal_path,
            batch_id=batch_id,
            file_ids=chunk_ids,
            status="completed" if len(batch_written) == len(chunk) else "partial",
            written_ids=batch_written,
        )
    print()
    try:
        tmp_zip_dir.rmdir()
    except Exception:
        pass
    logger.info("Done. wrote=%d, total=%d", wrote, total)
    logger.info("Out dir: %s", str(out_root))
    manifest_items = []
    for p in pdfs:
        manifest_items.append(
            {
                "arxiv_id": p.stem,
                "preview_pdf": str(p),
                "md_path": str(out_root / f"{p.stem}.md"),
                "status": statuses.get(p.stem, "skipped" if (out_root / f"{p.stem}.md").exists() else "unknown"),
            }
        )
    manifest_path = out_root / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps({"date": date_str, "total": len(pdfs), "items": manifest_items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("============结束预览 PDF 的 MinerU 解析==============", flush=True)

    # 成功率检查：只有 0 篇成功（或低于 --min-success-ratio）时才以非零退出
    total_uploaded = len(pdfs_to_upload)
    success_ratio = wrote / total_uploaded if total_uploaded > 0 else 1.0
    if wrote == 0:
        print(
            f"[ERROR] 0 篇论文成功写入（共 {total_uploaded} 篇），流水线中止",
            flush=True,
        )
        sys.exit(1)
    if success_ratio < args.min_success_ratio:
        print(
            f"[ERROR] 成功率 {success_ratio:.1%} 低于阈值 {args.min_success_ratio:.1%}"
            f"（{wrote}/{total_uploaded}），流水线中止",
            flush=True,
        )
        sys.exit(1)
    if wrote < total_uploaded:
        print(
            f"[WARN] 部分论文未能成功解析：{wrote}/{total_uploaded} 篇成功，"
            f"失败/超时/unknown 的论文将在下游步骤中自动跳过",
            flush=True,
        )


if __name__ == "__main__":
    run()
