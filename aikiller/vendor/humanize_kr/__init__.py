"""Vendored quantitative metrics from `im-not-ai` (Humanize KR v2.3.2, MIT).

Source: https://github.com/epoko77-ai/im-not-ai
Files: metrics.py, metrics_v2.py, baseline.json, baseline_v2.json — verbatim.
See LICENSE.im-not-ai and ../../../THIRD_PARTY_NOTICES.md.

NOTE on calibration status:
  - baseline.json      (v1.6) : REAL data. KatFish (Park et al.) human 470 vs
                                LLM 1,624 docs + user corpus 2026-08-29.
                                Usable for discriminative scoring today.
  - baseline_v2.json   (v2.0) : ALL cells are `_placeholder: true`. Values are
                                estimates, never measured against a Korean
                                reference corpus. Do NOT trust v2 z-scores
                                until `scripts/calibrate.py` has been run.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import metrics as v1  # noqa: E402
import metrics_v2 as v2  # noqa: E402

compute_all = v1.compute_all
compute_all_v2 = v2.compute_all_v2
split_sentences = v1._split_sentences
eojeols = v1._eojeols
strip_punct = v1._strip_punct
interference_index = v2.interference_index

BASELINE_V1_PATH = os.path.join(_HERE, "baseline.json")
BASELINE_V2_PATH = os.path.join(_HERE, "baseline_v2.json")

__all__ = [
    "v1", "v2", "compute_all", "compute_all_v2", "split_sentences",
    "eojeols", "strip_punct", "interference_index",
    "BASELINE_V1_PATH", "BASELINE_V2_PATH",
]
