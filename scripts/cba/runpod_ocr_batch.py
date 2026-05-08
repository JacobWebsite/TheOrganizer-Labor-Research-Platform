"""Resume-safe OCR batch runner for scanned CBA PDFs, designed for RunPod.

Reads a shard CSV (one of the files produced by shard_manifest.py) and runs
each scanned PDF through opendataloader-pdf (Docling backend) on GPU. Writes
one markdown file per input PDF plus a JSON metadata file. Maintains a
done.log so Ctrl+C / pod restarts resume without redoing work.

Runs on the RunPod pod, not locally. Expects:
  - PyTorch with CUDA visible (torch.cuda.is_available() -> True)
  - Java JRE on PATH (apt install -y default-jre)
  - pip install opendataloader-pdf[hybrid] docling

Usage on the pod:
    python runpod_ocr_batch.py \\
        --shard /workspace/shard_00_of_04.csv \\
        --input-dir /workspace/pdfs \\
        --output-dir /workspace/output \\
        --benchmark-only       # process only first 20, print pages/sec, exit

Output layout (per PDF):
    output/<stem>/<stem>.md          -- markdown with article headings
    output/<stem>/meta.json          -- page count, timing, quality proxy
    output/done.log                  -- one line per successful file (append-only)
    output/errors.log                -- one line per failed file
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# ---------- hybrid server lifecycle ---------- #
def start_hybrid_server(
    port: int,
    hf_cache: str | None,
    log_path: Path,
    wait_seconds: int = 300,
) -> subprocess.Popen | None:
    """Start opendataloader-pdf-hybrid in the background and wait for /health.

    Returns the Popen handle (so the caller can terminate it) or None if the
    server was already running (we probe /health first and skip startup).
    """
    probe_url = f"http://localhost:{port}/health"

    # Skip if something is already answering on that port.
    try:
        with urllib.request.urlopen(probe_url, timeout=2) as resp:
            if 200 <= resp.status < 300:
                print(f"Hybrid server already running on :{port}")
                return None
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        pass  # not running yet, continue

    env = os.environ.copy()
    if hf_cache:
        Path(hf_cache).mkdir(parents=True, exist_ok=True)
        env["HF_HOME"] = hf_cache
        env["HUGGINGFACE_HUB_CACHE"] = hf_cache
        env["TRANSFORMERS_CACHE"] = hf_cache
        print(f"HuggingFace cache: {hf_cache}")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = log_path.open("ab")
    print(f"Starting opendataloader-pdf-hybrid --port {port}  (log: {log_path})")
    proc = subprocess.Popen(
        ["opendataloader-pdf-hybrid", "--port", str(port)],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
    )

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Hybrid server exited early (code={proc.returncode}). "
                f"See {log_path} for details."
            )
        try:
            with urllib.request.urlopen(probe_url, timeout=2) as resp:
                if 200 <= resp.status < 300:
                    elapsed = int(wait_seconds - (deadline - time.time()))
                    print(f"Hybrid server ready on :{port} after ~{elapsed}s")
                    return proc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(5)

    proc.terminate()
    raise RuntimeError(
        f"Hybrid server did not become healthy within {wait_seconds}s. "
        f"See {log_path}."
    )


# ---------- word-recognition quick quality proxy ---------- #
_COMMON = frozenset(
    "the and of to in a is that for it shall will not with be this are or by "
    "employee employer union agreement article section wages hours contract "
    "party work pay benefits vacation grievance arbitration overtime seniority "
    "company members local board labor management insurance pension".split()
)


def quality_proxy(text: str) -> float:
    words = re.findall(r"[a-zA-Z]{2,}", text.lower())
    if not words:
        return 0.0
    return sum(1 for w in words if w in _COMMON) / len(words)


# ---------- done-log helpers (resume-safe) ---------- #
def read_done(done_log: Path) -> set[str]:
    if not done_log.exists():
        return set()
    return {line.strip() for line in done_log.read_text("utf-8").splitlines() if line.strip()}


def append_done(done_log: Path, filename: str) -> None:
    with done_log.open("a", encoding="utf-8") as fh:
        fh.write(filename + "\n")


def append_error(err_log: Path, filename: str, msg: str) -> None:
    with err_log.open("a", encoding="utf-8") as fh:
        fh.write(f"{filename}\t{msg}\n")


# ---------- per-PDF worker ---------- #
def run_one(
    pdf_path: Path,
    output_root: Path,
    opendataloader_pdf,
) -> dict:
    """Process one PDF and return a result dict. Raises on hard failure."""
    stem = pdf_path.stem
    out_dir = output_root / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    opendataloader_pdf.convert(
        input_path=[str(pdf_path)],
        output_dir=str(out_dir),
        format="markdown",
        hybrid="docling-fast",
        hybrid_mode="full",
    )
    elapsed = time.time() - t0

    md_files = [f for f in out_dir.iterdir() if f.suffix.lower() == ".md"]
    if not md_files:
        raise RuntimeError("no markdown output produced")
    md_path = md_files[0]

    text = md_path.read_text("utf-8", errors="replace")
    lines = text.splitlines()
    article_hits = sum(1 for ln in lines if "ARTICLE" in ln.upper())
    table_rows = sum(1 for ln in lines if ln.lstrip().startswith("|"))
    quality = quality_proxy(text)

    meta = {
        "filename": pdf_path.name,
        "markdown_file": md_path.name,
        "seconds": round(elapsed, 2),
        "chars": len(text),
        "lines": len(lines),
        "article_hits": article_hits,
        "table_rows": table_rows,
        "word_quality": round(quality, 3),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


# ---------- main ---------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", required=True, help="Shard CSV from shard_manifest.py")
    parser.add_argument("--input-dir", required=True, help="Directory holding the PDFs")
    parser.add_argument("--output-dir", required=True, help="Where to write markdown+meta")
    parser.add_argument(
        "--benchmark-only",
        action="store_true",
        help="Process only the first 20 PDFs and print pages/sec.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Override: stop after this many PDFs (useful for cost ceilings).",
    )
    parser.add_argument(
        "--max-seconds",
        type=int,
        default=None,
        help="Override: stop after this many wall-clock seconds (cost ceiling).",
    )
    parser.add_argument(
        "--hybrid-port",
        type=int,
        default=5002,
        help="Port the opendataloader-pdf hybrid server listens on.",
    )
    parser.add_argument(
        "--hf-cache",
        default=None,
        help=(
            "Directory to use for HuggingFace model cache. Point to a shared "
            "Network Volume path (e.g. /workspace/hf_cache) to avoid "
            "re-downloading models on every pod."
        ),
    )
    parser.add_argument(
        "--skip-server",
        action="store_true",
        help="Do NOT auto-start opendataloader-pdf-hybrid. Assume it's already running.",
    )
    args = parser.parse_args()

    # ---- environment sanity ---- #
    try:
        import torch  # noqa: WPS433 -- only imported here so laptop runs still work
        has_cuda = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if has_cuda else "(none)"
    except Exception:
        has_cuda = False
        gpu_name = "(torch missing)"

    try:
        import opendataloader_pdf  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: opendataloader_pdf import failed: {exc}")
        sys.exit(2)

    print(f"CUDA available: {has_cuda}    GPU: {gpu_name}")
    if not has_cuda:
        print("WARNING: no CUDA GPU detected -- OCR will fall back to CPU (170s/page).")

    # ---- auto-start the hybrid server if not already running ---- #
    hybrid_proc: subprocess.Popen | None = None
    output_root_pre = Path(args.output_dir)
    output_root_pre.mkdir(parents=True, exist_ok=True)
    if not args.skip_server:
        hybrid_proc = start_hybrid_server(
            port=args.hybrid_port,
            hf_cache=args.hf_cache,
            log_path=output_root_pre / "hybrid_server.log",
        )

    # ---- load shard ---- #
    shard_path = Path(args.shard)
    input_dir = Path(args.input_dir)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    done_log = output_root / "done.log"
    err_log = output_root / "errors.log"
    already_done = read_done(done_log)

    with shard_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    if args.benchmark_only:
        rows = rows[:20]
        print(f"BENCHMARK mode: processing {len(rows)} PDFs only")

    if args.max_files is not None:
        rows = rows[: args.max_files]

    todo = [r for r in rows if r["filename"] not in already_done]
    skipped = len(rows) - len(todo)
    total_pages = sum(int(r["page_count"]) for r in todo)

    print(f"Shard:     {shard_path.name}   ({len(rows):,} rows)")
    print(f"Input:     {input_dir}")
    print(f"Output:    {output_root}")
    print(f"Already done: {skipped:,}")
    print(f"To process:   {len(todo):,}  ({total_pages:,} pages)")
    print("-" * 60)

    start_wall = time.time()
    pages_done = 0
    failures = 0

    for idx, row in enumerate(todo, start=1):
        if args.max_seconds and (time.time() - start_wall) >= args.max_seconds:
            print(f"\n[stop] --max-seconds reached after {idx-1} files")
            break

        pdf_path = input_dir / row["filename"]
        if not pdf_path.exists():
            msg = "pdf not found"
            append_error(err_log, row["filename"], msg)
            failures += 1
            continue

        try:
            meta = run_one(pdf_path, output_root, opendataloader_pdf)
        except Exception as exc:  # noqa: BLE001
            append_error(err_log, row["filename"], f"{type(exc).__name__}: {exc}")
            failures += 1
            continue

        append_done(done_log, row["filename"])
        pages_done += int(row["page_count"])

        wall = time.time() - start_wall
        rate_pages = pages_done / max(wall, 0.001)
        eta_min = (total_pages - pages_done) / max(rate_pages, 0.1) / 60
        print(
            f"  [{idx:4d}/{len(todo):4d}]  "
            f"{int(row['page_count']):3d}p  "
            f"{meta['seconds']:6.1f}s  "
            f"quality={meta['word_quality']:.2f}  "
            f"articles={meta['article_hits']:3d}  "
            f"{rate_pages:5.1f} pg/s  ETA {eta_min:5.1f} min   "
            f"{row['filename'][:44]}"
        )

    wall = time.time() - start_wall
    print("-" * 60)
    print(f"Done.  wall={wall/60:5.1f} min   pages={pages_done:,}   "
          f"rate={pages_done/max(wall, 0.001):.2f} pg/s   failures={failures}")
    if args.benchmark_only and pages_done:
        est_hr_per_kpages = (wall / pages_done * 1000) / 3600
        print(f"  benchmark: {est_hr_per_kpages:.2f} GPU-hr per 1,000 pages")

    # ---- stop the hybrid server we started ---- #
    if hybrid_proc is not None:
        print("Terminating hybrid server...")
        hybrid_proc.terminate()
        try:
            hybrid_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            hybrid_proc.kill()


if __name__ == "__main__":
    main()
