# Face detection ML eval fixtures (S11-009 / ART-25 §3.2)

This directory is the local calibration dataset for
`scripts/eval/eval_face_detection.py`. It is **not committed** — face
images are biometric data per ART-18 and the repo does not distribute
them. Populate it once per workstation before running the eval.

## Layout

```
apps/api/tests/fixtures/face_eval/
├── README.md                 (this file, committed)
├── .gitkeep                  (empty, keeps the directory visible)
├── <identity_001>/
│   ├── img01.jpg
│   ├── img02.jpg
│   └── ...
├── <identity_002>/
│   └── ...
└── ...
```

- Images can sit directly in this directory or in identity sub-folders.
  The eval script walks recursively and counts **every** `.jpg /
  .jpeg / .png / .webp / .tiff / .heic` file as one test case.
- Target size per ART-25 §3.2: **500 images across 50 identities**.
  Smaller slices are fine for smoke runs — pass `--limit 50` to the
  script for a fast pass.
- Frontal faces produce the cleanest baseline; mixed angles still
  work, just expect a lower detection rate.

## Sourcing a dataset

We cannot ship a dataset with the repo because:

1. **Licensing chain** — most public face datasets (LFW, CelebA,
   CASIA-WebFace) have research-only licences that forbid
   redistribution.
2. **Size** — 500 face images is ~100–200 MB of JPEGs.
3. **Biometric data classification** — ART-18 classifies face images
   as biometric data; committing any to the repo would widen the
   compliance perimeter to the git remote.

Reasonable sources for local use:

- **Wikimedia Commons portraits** — CC BY / CC0 licensed, usable for
  local evaluation. Harvest ~500 images across ~50 named subjects.
- **Synthetic faces** from a local generator (e.g. StyleGAN-3 sample
  outputs) — no licensing concerns, identity labels may be weaker.
- **Your own photos** — perfectly fine for a dev machine, and the
  closest match to real usage.

## Running the eval

```bash
# 1. Install the face pipeline deps (once)
cd apps/api && poetry lock --no-update && poetry install

# 2. Download the InsightFace model pack (once)
make download-face-models
export INSIGHTFACE_MODEL_DIR=$(pwd)/infra/docker/workers/models/insightface

# 3. Populate this directory with calibration images
cp -R ~/my-face-calibration-set/* apps/api/tests/fixtures/face_eval/

# 4. Run the eval
make eval-face
# or, directly:
poetry run python scripts/eval/eval_face_detection.py

# Smoke run over 50 images only:
poetry run python scripts/eval/eval_face_detection.py --limit 50
```

## Output

Results land in `eval_results/face_detection_baseline_YYYY-MM-DD.json`:

```json
{
  "metrics": {
    "image_count": 500,
    "detection_rate": 0.974,
    "mean_score": 0.891,
    "latency_p50_ms": 142.3,
    "latency_p95_ms": 318.7,
    "latency_mean_ms": 168.0
  },
  "targets": {
    "detection_rate": 0.95,
    "mean_score": 0.85,
    "latency_p50_ms": 200.0,
    "latency_p95_ms": 400.0
  },
  "passed": { "detection_rate": true, "mean_score": true, ... }
}
```

## Graceful skip

The eval script exits 0 (skip, not fail) if **any** of these hold:

- `insightface` is not installed
- `INSIGHTFACE_MODEL_DIR` is unset or points to a missing directory
- this fixture directory is empty

This is deliberate: CI and casual dev runs of `make eval-face` should
never fail just because a workstation hasn't been provisioned yet.
Real eval failures are a regression in detection rate, score, or
latency — only those should block a release.
