# Facade model weights: internal use only

The plugin's code is MIT (see `LICENSE`). The trained facade weights listed in `models.json`
(`parts2m`, `parts11s`), published as assets of this private repository's GitHub releases, are
**for internal use within the studio only**: do not redistribute or sell them.

Why:

- They were trained with Ultralytics YOLO, which is licensed under AGPL-3.0; models trained with it
  fall under that licence unless an Ultralytics Enterprise licence is held.
- Part of the training data is licensed for research or non-commercial use only, among them
  LabelMeFacade, eTRIMS and ADE20K. Other sources (CMP, hznu_facade, Oxford, MonuMAI, Open Images)
  are CC BY / CC BY-SA. `python tools/train_data.py sources` lists every dataset and its licence.

Distributing the plugin outside the studio, or commercially, needs weights retrained only on data
whose licence allows it, and a decision on the Ultralytics licence.
