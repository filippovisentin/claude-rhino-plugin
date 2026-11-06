# Detector fixture

`c_0075.jpg` is photo c_0075 of hznu_facade (Hangzhou facades), resized to 1280 px on the long
side. Licence CC BY 4.0. Source: hznu_facade dataset, Data in Brief 2025, doi 10.17632/k387xkyc5f.1.

`expected.json` is the draft that `tools/facade_yolo.py detect-image` returns for it with the
default models of `models.json` (parts2m fused with parts11s), conf 0.25, on the reference PC.
`scripts/setup.mjs` compares a fresh install against it (same classes and counts, boxes within 4 px).
