# InsightFace Model Pack (Phase 3, S11-005)

This directory holds the pre-downloaded [InsightFace](https://github.com/deepinsight/insightface)
`buffalo_l` model pack, bind-mounted read-only into the workers container
at `/models/insightface`. The models are the SCRFD-10g face detector and
the ArcFace-R100 recognizer used by `api.services.face.face_model.FaceModel`.

## What's in the pack

| File                        | Purpose                           | Approx size |
|-----------------------------|-----------------------------------|-------------|
| `buffalo_l/det_10g.onnx`    | SCRFD-10g detector + landmarks    | ~16 MB      |
| `buffalo_l/w600k_r50.onnx`  | ArcFace-R100 512-dim recognizer   | ~249 MB     |
| `buffalo_l/1k3d68.onnx`     | 3D landmark head                  | ~138 MB     |
| `buffalo_l/2d106det.onnx`   | 2D 106-point landmark head        | ~5 MB       |
| `buffalo_l/genderage.onnx`  | Gender/age head (not used by us)  | ~1.3 MB     |

Total: roughly **288 MB**. `.onnx` and `.zip` files are gitignored — the
models are downloaded on demand, never committed.

## One-time download

```bash
# 1. Populate CHECKSUMS.txt with real SHA-256 hashes from the v0.7 release
#    (the committed placeholders block the download by design).
# 2. Run the Make target from the repo root:
make download-face-models
```

The Make target invokes `scripts/face/download_models.sh`, which:

1. Refuses to run while any hash in `CHECKSUMS.txt` begins with
   `PLACEHOLDER_`.
2. Downloads `buffalo_l.zip` from the official InsightFace v0.7 release
   via `curl -fL`.
3. Verifies the zip SHA-256 against `CHECKSUMS.txt`.
4. Unzips into `buffalo_l/` alongside this README.
5. Verifies each expected `.onnx` SHA-256 against `CHECKSUMS.txt`.
6. On any failure: deletes the partial download, exits non-zero,
   prints a specific reason.

## Re-verification

To verify an existing install without re-downloading:

```bash
bash scripts/face/download_models.sh --verify-only
```

## License notes (ART-24)

- **InsightFace code**: MIT License. Checked by `make sbom` + G-12
  license audit.
- **Model weights**: the buffalo_l weights are distributed by the
  InsightFace project under their own terms. The InsightFace README
  calls out non-commercial research use for some sub-components; review
  the [upstream LICENSE](https://github.com/deepinsight/insightface/blob/master/LICENSE)
  before any commercial deployment. This is a `REVIEW` item in the
  supply-chain audit.

## When to re-download

- Upstream releases a newer pack with better weights → update the URL
  in `scripts/face/download_models.sh`, update all hashes in
  `CHECKSUMS.txt`, commit both.
- You delete the pack to free disk space → just re-run
  `make download-face-models`.
- `detect_and_embed` starts returning corrupt embeddings → run the
  `--verify-only` check first.
