# RunPod OCR Runbook — Scanned CBA PDFs

Plain-English step-by-step for OCR'ing the ~4,200 scanned CBA PDFs in
`C:\Users\jakew\Downloads\OPDR CBAs` using a rented NVIDIA GPU on RunPod,
under a **$50 total budget**. Output is one markdown file per PDF with
article headings preserved so `extract_articles.py` can consume it.

---

## Cast of scripts

| Script | Where it runs | What it does |
|---|---|---|
| `build_scan_manifest.py` | Your laptop | Makes `cba_scan_manifest.csv` (page count + scanned flag per PDF). **~60 min, one-time.** |
| `shard_manifest.py` | Your laptop | Splits manifest into N balanced shards so multiple pods finish at the same time. |
| `runpod_ocr_batch.py` | The RunPod pod | The workhorse. Reads a shard CSV, OCRs each scanned PDF, writes markdown + metadata. Resume-safe. |

All three live in `scripts/cba/`.

---

## Budget math (single-pod plan)

Advertised Docling throughput on GPU is ~0.46 s/page. Using 0.6 s/page to stay honest:

| Scanned pages | GPU-hours | A4000 ($0.20/hr) | RTX 3090 ($0.35/hr) | RTX 4090 ($0.50/hr) |
|---|---|---|---|---|
| 100,000 | 16.7 | **$3** | $6 | $8 |
| 200,000 | 33.3 | **$7** | $12 | $17 |
| 500,000 | 83.3 | **$17** | $29 | $42 |
| 750,000 | 125 | $25 | $44 | (over) |

**Conclusion:** Even the worst case fits inside $50 on A4000. Pick A4000 for
the cheapest path, 4090 if you want it done in a day.

---

## Step 0 — Wait for the manifest to finish

```
py scripts/cba/build_scan_manifest.py
```

Runs on your laptop, no GPU needed, ~60 min. It reads every PDF's text
density and writes `data/cba_scan_manifest.csv`. Interrupt with Ctrl+C any
time; re-running resumes where it left off.

When it finishes, print the summary:
```
py scripts/cba/build_scan_manifest.py --summary-only
```

This gives you the real scanned-page total and cost projection. If the
projection is under $50 at A4000 rates, proceed.

---

## Step 1 — Shard the manifest

Pick how many pods you'll run in parallel. For a first try, start with 1.
(If one pod would take longer than you want to wait, bump to 4 later.)

```
py scripts/cba/shard_manifest.py --shards 1
```

Writes `data/cba_shards/shard_00_of_01.csv`. For 4 pods:
```
py scripts/cba/shard_manifest.py --shards 4
```

---

## Step 2 — Create a RunPod account

1. <https://runpod.io>, sign up with email or Google (~2 min).
2. Add $20 of credit. You'll use much less; RunPod doesn't refund unused
   balance but it doesn't expire either.
3. Pick **Secure Cloud** (never Community Cloud for long jobs — Community
   pods can be preempted and you lose progress on restart).

---

## Step 3 — Deploy a pod

1. Click **Deploy** (top nav).
2. GPU: **RTX A4000 16GB** for cheapest, or **RTX 4090 24GB** for speed.
3. Template: pick one with PyTorch + CUDA preinstalled, e.g.
   `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`.
4. Container disk: 50 GB. Volume disk: 30 GB (this persists if you stop
   the pod).
5. Click **Deploy On-Demand** — pod boots in ~60 seconds.
6. Once running, click **Connect** → **Start Web Terminal**. That gives
   you a browser-based shell. You can also use **Connect → SSH** if you
   prefer your local terminal.

---

## Step 4 — Set up the pod (one-time, ~5 min)

In the pod's web terminal:

```bash
# System deps
apt update && apt install -y default-jre

# Python deps
pip install --upgrade pip
pip install opendataloader-pdf[hybrid] docling pdfplumber

# Sanity check
python -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
python -c "import opendataloader_pdf; print('opendataloader-pdf OK')"
```

Expected: `CUDA: True NVIDIA RTX A4000` (or similar).

---

## Step 5 — Upload files to the pod

You need to get three things onto the pod:
1. The shard CSV (small, KBs)
2. The `runpod_ocr_batch.py` script
3. The PDFs themselves (**~15 GB**)

### Option A — SCP from your laptop (single-pod, simplest)

In RunPod's pod page, note the SSH connection info:
`ssh root@<pod_ip> -p <pod_port> -i ~/.ssh/id_ed25519`

From your laptop (Git Bash or PowerShell):
```bash
# Script + shard
scp -P <pod_port> scripts/cba/runpod_ocr_batch.py root@<pod_ip>:/workspace/
scp -P <pod_port> data/cba_shards/shard_00_of_01.csv root@<pod_ip>:/workspace/

# PDFs (15 GB -- will take 60-180 min on residential upload)
scp -P <pod_port> -r "/c/Users/jakew/Downloads/OPDR CBAs" root@<pod_ip>:/workspace/pdfs
```

### Option B — Network Volume (parallel pods)

If you want 4 pods running in parallel, upload PDFs **once** to a
RunPod Network Volume and attach it to every pod. Saves ~45 GB of
redundant upload.

1. In RunPod UI: **Storage → Network Volumes → New Volume**. 30 GB.
2. When deploying each pod, attach the volume at `/workspace`.
3. SCP PDFs once into `/workspace/pdfs` on the first pod.
4. Every subsequent pod sees them at `/workspace/pdfs` instantly.

---

## Step 6 — Run a benchmark (required!)

**Always benchmark before committing to the full run.** This confirms
the per-page time matches expectations and the output quality is usable.

On the pod:
```bash
cd /workspace

python runpod_ocr_batch.py \
    --shard shard_00_of_01.csv \
    --input-dir pdfs \
    --output-dir output \
    --benchmark-only
```

Expected output: ~20 PDFs processed, pages/sec rate printed. A4000 should
hit **1.5-3 pg/s**, 4090 should hit **3-5 pg/s**. If it's below 0.5 pg/s
something is wrong — stop and investigate before burning credits.

Inspect one output markdown file:
```bash
cat output/<some_cba_stem>/<some_cba_stem>.md | head -80
```

Look for: ARTICLE headings, readable English (not OCR gibberish), table
rows. If quality is garbage on more than a couple samples, stop — the
OCR is producing junk and running the full batch is a waste.

---

## Step 7 — Launch the full run in tmux

A 15-30 hour job needs to survive you closing the browser:

```bash
tmux new -s ocr
cd /workspace

python runpod_ocr_batch.py \
    --shard shard_00_of_01.csv \
    --input-dir pdfs \
    --output-dir output \
    --max-seconds 36000    # 10-hour safety cap; remove for unbounded
```

Press **Ctrl+B then D** to detach (pod keeps running). Reattach with
`tmux attach -t ocr`.

### Budget guardrails

Use `--max-files 500` or `--max-seconds 7200` (2 hr) for the first real
run if you want a cost ceiling. Then evaluate a sample of outputs before
committing to the rest.

---

## Step 8 — Monitor from your laptop

Every ~10 hours, open the web terminal and check:

```bash
wc -l /workspace/output/done.log   # how many finished
wc -l /workspace/output/errors.log # how many failed
tail /workspace/output/done.log
```

Or just reattach: `tmux attach -t ocr`.

### Billing check

RunPod dashboard shows live spend. Set a mental stop-loss:

- A4000 at $0.20/hr × 100 hours = $20. Stop if you cross $40.
- 4090 at $0.50/hr × 30 hours = $15. Stop if you cross $40.

---

## Step 9 — Download results

Once `done.log` has all the files you care about:

```bash
# From your laptop
scp -P <pod_port> -r root@<pod_ip>:/workspace/output "C:/Users/jakew/.local/bin/Labor Data Project_real/data/cba_ocr_runpod"
```

The `output/` dir is markdown + JSON, **no PDFs** — should be a few
hundred MB, not 15 GB. Fast.

---

## Step 10 — Stop the pod

**CRITICAL:** Pods bill every second they're running. When done:

1. RunPod UI → Pods → **Stop** (preserves disk at ~$0.01/GB/day — pennies).
2. Or **Terminate** (deletes everything). If you used a Network Volume,
   data there persists independently.

Pods do NOT auto-stop. You must click it yourself.

---

## Step 11 — Load markdown into the DB

This is a local step, **not yet scripted.** Rough plan:

1. Extend `01_extract_text.py::insert_document()` to accept
   `extraction_method="docling"`.
2. For each folder in `data/cba_ocr_runpod/`:
   - Read the `.md` file
   - Look up (or insert) the `cba_documents` row by filename/hash
   - Set `full_text` = the markdown, `extraction_method` = `docling`,
     `ocr_status` = `completed`, `structure_quality` = derived from
     `meta.json`'s `word_quality`
3. Re-run `extract_articles.py --all` to re-parse articles from the new
   markdown full_text.

Save as a separate task — decide after we see the real OCR quality on a
sample.

---

## Troubleshooting

### "CUDA: False" on the pod
You picked the wrong template. Redeploy with one that has `cuda` in the
name. Don't run OCR without CUDA — CPU fallback is 300x slower.

### Docling hangs on a specific PDF
Ctrl+C in tmux, note the filename, skip it by adding it to `done.log`
manually, restart. Won't reprocess.

### Quality is low on a subset of scans
Docling has a `force_ocr` mode and resolution control. Add `--hybrid-mode full`
(already set in the script) or consider preprocessing the PDF with a
higher-DPI rasterization. Don't solve this problem at batch scale — fix
the script first, then re-run the failing shard.

### Pod disconnected / billing still running
Sometimes the SSH/web-terminal disconnects but the pod keeps running
(and billing). tmux solves this. If you did NOT start in tmux and the
SSH died, your job died with it. Check `done.log` to see how far it got,
then restart.

---

## Post-run checklist

- [ ] All `done.log` entries accounted for (`wc -l` matches shard count)
- [ ] `errors.log` reviewed; failed files logged in a vault Open Problem
      if recurring pattern
- [ ] Spend visible in RunPod dashboard, under budget
- [ ] Pod **stopped or terminated** (double-check the status light)
- [ ] Results SCP'd to `data/cba_ocr_runpod/`
- [ ] Network Volume deleted if used (unless you're keeping it for re-runs)
- [ ] Work Log entry written in the vault with: files OCR'd, total spend,
      wall time, quality proxy average, anomalies

---

# Addendum — 4-Pod Parallel Plan (the "fastest under budget" variant)

This is the path for getting all 2,860 scanned CBAs OCR'd in **~7 hours
of wall time for ~$6**, by running 4 RTX A4000 pods in parallel against
a single shared upload of the PDFs.

## Numbers from the real manifest

- 2,860 scanned PDFs, 169,160 pages, 8.26 GB
- Sharded 4-way: 715 files / 42,290 pages / ~2 GB per shard (perfectly balanced)
- Benchmark shard: 20 files / 1,556 pages / 108 MB

## Two extra scripts in the cast

| Script | Where | What |
|---|---|---|
| `make_benchmark_shard.py` | Your laptop | Picks a stratified-by-page-count 20-PDF sample. Output: `data/cba_shards/benchmark_shard.csv`. |
| `stage_for_upload.py` | Your laptop | Two modes: `copy` (physically stage files for SCP — used for the benchmark) and `list` (write `rsync --files-from=` text files — used for the full shards). |

Already run for you:
```
data/cba_shards/
  benchmark_shard.csv          20 files
  shard_00_of_04.csv           715 files
  shard_01_of_04.csv           715 files
  shard_02_of_04.csv           715 files
  shard_03_of_04.csv           715 files

data/cba_upload_staging/
  benchmark_shard/             20 files copied here, ready to SCP
  shard_00_of_04.upload.txt    rsync file list, 2.20 GB
  shard_01_of_04.upload.txt    rsync file list, 2.02 GB
  shard_02_of_04.upload.txt    rsync file list, 2.09 GB
  shard_03_of_04.upload.txt    rsync file list, 1.95 GB
```

---

## Phase 1 — Benchmark on one A4000 (~$0.10, ~20 min)

The benchmark proves: (a) per-page time on real GPU, (b) OCR quality on
representative scans. **Do not skip this.**

### 1.1 Spin up one pod
- RunPod → Deploy → **RTX A4000 16GB**, Secure Cloud
- Template: `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`
- Container disk 50 GB, no Network Volume yet
- Click **Deploy On-Demand**
- Once running: Connect → SSH info shown (note POD_IP and POD_PORT)

### 1.2 From your laptop — upload the 108 MB benchmark + scripts
```bash
cd "/c/Users/jakew/.local/bin/Labor Data Project_real"

# scripts + manifest shard
scp -P POD_PORT scripts/cba/runpod_ocr_batch.py root@POD_IP:/workspace/
scp -P POD_PORT data/cba_shards/benchmark_shard.csv root@POD_IP:/workspace/

# the 20 PDFs already staged
scp -P POD_PORT -r data/cba_upload_staging/benchmark_shard root@POD_IP:/workspace/pdfs
```

### 1.3 On the pod — install + run
```bash
apt update && apt install -y default-jre
pip install opendataloader-pdf[hybrid] docling pdfplumber

cd /workspace
python runpod_ocr_batch.py \
    --shard benchmark_shard.csv \
    --input-dir pdfs \
    --output-dir output \
    --benchmark-only
```

Expected: ~15-20 min wall, prints `X.X pg/s` at the end. **Inspect 3-4
output files for OCR quality before proceeding.**

```bash
ls output/
cat output/<some-stem>/<some-stem>.md | head -100
```

If quality looks fine and rate is **at least 1.5 pg/s**: keep this pod
running, move to Phase 2. If quality is bad: stop here, debug, do not
launch the parallel run.

---

## Phase 2 — Set up the Network Volume (one-time, ~15 min)

The Network Volume is the trick that makes parallel pods cheap. Upload
the 8.26 GB of scanned PDFs **once**; all 4 pods read from the same
volume at datacenter speeds.

### 2.1 Create the volume
- RunPod → **Storage → Network Volumes → New Volume**
- Size: **30 GB** (leaves room for outputs)
- Region: **the same region as your pods** (critical — cross-region won't attach)
- Cost: ~$2.10/month, prorated to ~$0.07 for 24 hours

### 2.2 Attach to your benchmark pod
- Pod settings → Edit → attach volume at `/workspace`
- Pod restarts; the original `/workspace/pdfs` (just the 20 benchmark PDFs)
  is gone, replaced by the empty volume

### 2.3 Upload all 4 shards into the volume
From your laptop, this is one rsync per shard. They can run sequentially
in one terminal, or in 4 parallel terminals (residential upload usually
saturates with 1-2 streams):

```bash
SRC="/c/Users/jakew/Downloads/OPDR CBAs"
DEST="/workspace/pdfs"
LISTS="data/cba_upload_staging"

for i in 00 01 02 03; do
  rsync -avP --files-from="$LISTS/shard_${i}_of_04.upload.txt" \
    "$SRC/" root@POD_IP:$DEST/ -e 'ssh -p POD_PORT'
done
```

For 8.26 GB on residential upload: **45-180 min** depending on speed.
Run it overnight if needed.

After it's done, on the pod:
```bash
ls /workspace/pdfs | wc -l    # should be 2860
du -sh /workspace/pdfs        # should be ~8 GB
```

### 2.4 Push the scripts and shard CSVs to the volume
```bash
scp -P POD_PORT scripts/cba/runpod_ocr_batch.py root@POD_IP:/workspace/
scp -P POD_PORT data/cba_shards/shard_*.csv root@POD_IP:/workspace/
```

These now live on the volume and will be visible to every other pod
that mounts it.

---

## Phase 3 — Launch 3 more pods (~10 min)

You already have pod #0 (the benchmark pod). Spin up 3 more.

For each of pods 1, 2, 3:
1. Deploy → A4000, Secure Cloud, same template
2. **Attach the Network Volume at `/workspace`**
3. Once running, open the web terminal:
   ```bash
   apt update && apt install -y default-jre
   pip install opendataloader-pdf[hybrid] docling pdfplumber
   ```
4. (Skip the SCP — everything's already on the volume.)

---

## Phase 4 — Run all 4 pods in parallel (~7 hours)

In each pod's web terminal:

**Pod 0:**
```bash
tmux new -s ocr
cd /workspace
python runpod_ocr_batch.py \
    --shard shard_00_of_04.csv \
    --input-dir pdfs \
    --output-dir output_00
# Ctrl+B, D to detach
```

**Pod 1:** same but `shard_01_of_04.csv` and `output_01/`.
**Pod 2:** same but `shard_02_of_04.csv` and `output_02/`.
**Pod 3:** same but `shard_03_of_04.csv` and `output_03/`.

Each pod processes its own shard into its own output dir on the shared
volume, so no collisions. The `done.log` and `errors.log` are per-pod.

### Live monitoring (from any pod)
```bash
for d in output_*/; do
  printf "%-12s done=%-5s err=%-3s\n" "$d" \
    "$(wc -l < "$d/done.log" 2>/dev/null || echo 0)" \
    "$(wc -l < "$d/errors.log" 2>/dev/null || echo 0)"
done
```

### Cost ceiling guardrail
Add `--max-seconds 36000` (10 hours) to each command if you want a hard
stop. Saves you from a runaway pod. With 4 pods at $0.20/hr × 10 hr =
$8 ceiling.

---

## Phase 5 — Consolidate + download (~10 min)

When all 4 pods report done, on **one** pod (which mounts the volume):

```bash
cd /workspace
mkdir -p output_all
cp -r output_0?/* output_all/
ls output_all | wc -l   # should be ~2860 (minus error count)
tar czf output_all.tgz output_all/
ls -lh output_all.tgz   # probably 200-500 MB compressed
```

From your laptop:
```bash
scp -P POD_PORT root@POD_IP:/workspace/output_all.tgz \
  "/c/Users/jakew/.local/bin/Labor Data Project_real/data/cba_ocr_runpod.tgz"
```

Then unpack:
```bash
cd "/c/Users/jakew/.local/bin/Labor Data Project_real/data"
tar xzf cba_ocr_runpod.tgz
mv output_all cba_ocr_runpod
```

---

## Phase 6 — Tear it all down

**Critical, this is where money disappears if you forget.**

1. **Stop all 4 pods** (RunPod UI → Pods → each one → Stop)
   - Stopped pods don't bill compute. Disk is pennies/day.
2. **Delete the Network Volume** (RunPod UI → Storage → Network Volumes → Delete)
   - Or keep it if you want to re-run quickly later. $2/month.
3. Verify your spend in **Billing**. Should be $5-10 for everything.

---

## Total expected cost summary (parallel plan)

| Item | Cost |
|---|---|
| Phase 1 — Benchmark pod, 1 hr A4000 | $0.20 |
| Phase 4 — 4× A4000 × ~7 hrs | ~$5.60 |
| Network Volume, 1 day prorated | ~$0.07 |
| **Total** | **~$6** |

Well under the $50 cap. The realistic worst case (slow OCR, retries,
forgot-to-stop) is maybe $15.

