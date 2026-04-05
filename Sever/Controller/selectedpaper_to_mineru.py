import argparse
import json
import logging
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import List

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.config import minerU_Token, SELECTED_MINERU_DIR, MANIFEST_FILENAME  # noqa: E402


def setup_logging():
    logger = logging.getLogger("selectedpaper_mineru")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_latest_manifest(root_dir: Path) -> Path:
    if not root_dir.exists():
        raise FileNotFoundError(f"input root not found: {root_dir}")
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
        raise FileNotFoundError(f"no manifest found in {root_dir}")
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


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Security: check for Zip Slip (path traversal in zip entries)
        for info in zf.infolist():
            target = (dest_dir / info.filename).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise ValueError(f"Zip entry with path traversal detected: {info.filename!r}")
        zf.extractall(dest_dir)


class MinerUClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "*/*"})

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        r = self.session.post(url, json=payload, timeout=(20, 120))
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"MinerU API error: {data}")
        return data

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, timeout=(20, 120))
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"MinerU API error: {data}")
        return data

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


def wait_batch_done(client: MinerUClient, batch_id: str, expected_total: int, timeout_sec: int = 900, poll_sec: int = 3) -> List[dict]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        last = client.get_batch_results(batch_id)
        data = last.get("data") or {}
        items = data.get("extract_result") or []
        if not isinstance(items, list):
            items = []
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
            return [it for it in items if isinstance(it, dict)]
        time.sleep(poll_sec)
    raise TimeoutError("batch not finished in time")


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


def find_latest_selected_dir(root: Path) -> tuple[Path, str]:
    if not root.exists():
        raise SystemExit(f"input root not found: {root}")
    cand: List[str] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name):
            cand.append(d.name)
    if not cand:
        raise SystemExit(f"no dated subdir found in {root}")
    cand.sort()
    name = cand[-1]
    return root / name, name


def run():
    logger = setup_logging()
    ap = argparse.ArgumentParser("selectedpaper_to_mineru")
    ap.add_argument("--in-root", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "selectedpaper"))
    ap.add_argument("--date", default="")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--manifest", default="")
    ap.add_argument("--outdir", default=SELECTED_MINERU_DIR)
    ap.add_argument("--base-url", default=os.environ.get("MINERU_BASE_URL", "https://mineru.net"))
    ap.add_argument("--model-version", default=os.environ.get("MINERU_MODEL_VERSION", "vlm"))
    ap.add_argument("--timeout-sec", type=int, default=900)
    ap.add_argument("--poll-sec", type=int, default=3)
    ap.add_argument("--upload-retries", type=int, default=6)
    ap.add_argument(
        "--shared-cache",
        action="store_true",
        default=os.environ.get("PIPELINE_OUTPUT_MODE") == "db",
        help="Use full_mineru_cache (shared across users); read PDFs from raw_pdf/<date> instead of selectedpaper.",
    )
    args = ap.parse_args()

    token = (minerU_Token or "").strip()
    if not token:
        raise SystemExit("MinerU token missing in config.config.minerU_Token")

    _root_data = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    run_date = os.environ.get("RUN_DATE") or ""

    # Shared-cache mode: convert ALL downloaded PDFs once for all users
    if args.shared_cache:
        date_str = args.date or run_date or ""
        if not date_str:
            raise SystemExit("--shared-cache requires RUN_DATE env or --date argument")
        # Input: raw_pdf/<date>/*.pdf (all downloaded PDFs)
        raw_pdf_dir = Path(_root_data) / "raw_pdf" / date_str
        if not raw_pdf_dir.is_dir():
            raise SystemExit(f"raw_pdf dir not found: {raw_pdf_dir}")
        pdfs = sorted(raw_pdf_dir.glob("*.pdf"))
        if args.limit is not None:
            pdfs = pdfs[: args.limit]
        if not pdfs:
            # Even when there are 0 PDFs we must create the output directory and
            # an empty manifest so that:
            # (a) the idempotency sentinel exists for the next scheduled run, and
            # (b) downstream per-user steps (paper_summary, etc.) can detect
            #     "0 items processed today" without falling back to stale data.
            shared_cache_dir = ensure_dir(Path(_root_data) / "full_mineru_cache" / date_str)
            empty_manifest = shared_cache_dir / MANIFEST_FILENAME
            empty_manifest.write_text(
                json.dumps({"date": date_str, "total": 0, "items": []}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[selectedpaper_to_mineru] No raw PDFs found for shared cache; wrote empty manifest to {empty_manifest}", flush=True)
            return
        # Output: full_mineru_cache/<date>/
        shared_cache_dir = ensure_dir(Path(_root_data) / "full_mineru_cache" / date_str)
        print("============开始对全量 PDF 做 MinerU 解析 (shared cache)==============", flush=True)
        out_root = shared_cache_dir
        manifest_items_legacy: List[dict] = []
    else:
        in_root = Path(args.in_root)
        manifest_items_legacy: List[dict] = []
        manifest_path: Path | None
        if args.manifest:
            manifest_path = Path(args.manifest)
        else:
            try:
                manifest_path = find_latest_manifest(in_root)
            except FileNotFoundError:
                manifest_path = None
        if manifest_path is not None and manifest_path.exists():
            manifest_items_legacy, manifest_date = load_manifest(manifest_path)
            date_str = manifest_date or manifest_path.parent.name
            pdfs = []
            for it in manifest_items_legacy:
                pdf_path = str(it.get("selected_pdf") or it.get("pdf_path") or "")
                if pdf_path:
                    pdfs.append(Path(pdf_path))
        else:
            if args.date:
                in_dir = in_root / args.date
                if not in_dir.is_dir():
                    raise SystemExit(f"selectedpaper dir not found: {in_dir}")
                date_str = args.date
            else:
                in_dir, date_str = find_latest_selected_dir(in_root)
            pdfs = sorted(in_dir.glob("*.pdf"))
        if args.limit is not None:
            pdfs = pdfs[: args.limit]
        if not pdfs:
            raise SystemExit("No selected PDFs found")
        print("============开始对精选 PDF 做 MinerU 解析==============", flush=True)
        out_root = ensure_dir(Path(args.outdir) / date_str)
    pdfs_to_upload = [p for p in pdfs if not (out_root / p.stem / f"{p.stem}.md").exists()]
    if not pdfs_to_upload:
        logger.info("All selected PDFs already converted, skip upload and parse")
        logger.info("Out dir: %s", str(out_root))
        manifest_path = out_root / MANIFEST_FILENAME
        manifest_payload = {
            "date": date_str,
            "total": len(pdfs),
            "items": [
                {
                    "arxiv_id": p.stem,
                    "selected_pdf": str(p),
                    "md_path": str(out_root / p.stem / f"{p.stem}.md"),
                    "status": "skipped",
                }
                for p in pdfs
            ],
        }
        manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    BATCH_SIZE = 100
    client = MinerUClient(args.base_url, token)
    total = len(pdfs_to_upload)
    chunks = [pdfs_to_upload[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    logger.info("Total PDFs to upload: %d, split into %d batch(es) of up to %d", total, len(chunks), BATCH_SIZE)

    results: List[dict] = []
    uploaded_total = 0
    for chunk_idx, chunk in enumerate(chunks):
        logger.info("[batch %d/%d] Applying upload URLs for %d file(s)", chunk_idx + 1, len(chunks), len(chunk))
        files_payload = [{"name": p.name, "data_id": p.stem} for p in chunk]
        applied = client.apply_upload_urls(
            files_payload,
            model_version=args.model_version,
            extra={"return_images": True},
        ).get("data") or {}
        urls = applied.get("file_urls") or []
        batch_id = applied.get("batch_id") or ""
        if not batch_id or not urls or len(urls) != len(chunk):
            raise SystemExit(f"Failed to apply upload URLs (batch {chunk_idx + 1}/{len(chunks)})")

        for i, p in enumerate(chunk):
            upload_to_presigned_url(p, urls[i], max_retries=args.upload_retries)
            uploaded_total += 1
            print(f"\r[upload] {uploaded_total}/{total}", end="", flush=True)
        print()
        print(f"[batch {chunk_idx + 1}/{len(chunks)}] 上传完成，开始等待 MinerU 解析", flush=True)

        chunk_results = wait_batch_done(client, batch_id, expected_total=len(chunk), timeout_sec=args.timeout_sec, poll_sec=args.poll_sec)
        results.extend(chunk_results)
    by_name = {str(it.get("file_name") or ""): it for it in results}
    by_dataid = {str(it.get("data_id") or ""): it for it in results}

    wrote = 0
    statuses: dict[str, str] = {}
    for p in pdfs_to_upload:
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
        zip_path = out_root / f"{p.stem}.zip"
        download_zip(zip_url, token, zip_path)
        dest_dir = out_root / p.stem
        extract_zip(zip_path, dest_dir)
        md_text = pick_first_md(zip_path)
        (dest_dir / f"{p.stem}.md").write_text(md_text, encoding="utf-8")
        wrote += 1
        statuses[p.stem] = "done"
        print(f"\r[write] {wrote}/{total}", end="", flush=True)
    print()
    logger.info("Done. wrote=%d, total=%d", wrote, total)
    logger.info("Out dir: %s", str(out_root))
    manifest_payload_items = []
    for p in pdfs:
        manifest_payload_items.append(
            {
                "arxiv_id": p.stem,
                "selected_pdf": str(p),
                "md_path": str(out_root / p.stem / f"{p.stem}.md"),
                "status": statuses.get(p.stem, "skipped" if (out_root / p.stem / f"{p.stem}.md").exists() else "unknown"),
            }
        )
    manifest_path = out_root / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps({"date": date_str, "total": len(pdfs), "items": manifest_payload_items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.shared_cache:
        print("============结束全量 PDF 的 MinerU 解析 (shared cache)==============", flush=True)
    else:
        print("============结束精选 PDF 的 MinerU 解析==============", flush=True)


if __name__ == "__main__":
    run()
