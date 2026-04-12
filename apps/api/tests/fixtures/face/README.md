# Face Test Fixtures (S11-005)

This directory holds test images for the FaceModel integration test
tier. The image files themselves are **NOT committed** — place them
manually before running the `requires_insightface_models` suite.

## Expected files

| Filename           | Description                                               |
|--------------------|-----------------------------------------------------------|
| `face_test_001.jpg` | A single, clearly-lit frontal face (any adult, public domain or CC0). ~200KB, 512×512+ resolution is plenty. Used by `tests/test_face_model.py::test_real_model_detects_face`. |

## Where to get one

- **Wikimedia Commons** — many public-domain portraits. Filter by
  "portrait photograph" and "US-PD" / "CC0" license.
- **Unsplash** — all photos are free for any use under the Unsplash
  license. Pick one with a single front-facing subject.
- **Generated** — if you're allergic to real faces in your test suite,
  `thispersondoesnotexist.com` serves a fresh StyleGAN-synthesized
  face per request (not a real person).

## Why the image is not committed

1. **Licensing**: committing a face image means committing a license
   claim. We do not want to audit the CC0 chain every time someone
   clones the repo.
2. **Repo bloat**: binary test fixtures should be kept small and
   case-by-case. A single JPG isn't catastrophic, but a drift toward
   "commit every test asset" is.
3. **Test suite portability**: Tier 1 + Tier 2 tests in
   `test_face_model.py` run with fully mocked insightface and require
   no binary fixture. Only the `@pytest.mark.requires_insightface_models`
   Tier 3 test depends on this file, and that marker skips by default.

## Verification that the fixture is set up correctly

```bash
cd apps/api
poetry run pytest tests/test_face_model.py -m requires_insightface_models -v
```

If the fixture is missing or insightface isn't installed, the test
skips with a one-line explanation. If both are present, the test
loads the real SCRFD-10g + ArcFace-R100 models and asserts at least
one face with score > 0.5 and a 512-dim embedding.
