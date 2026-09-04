# 제3자 코드 고지

## im-not-ai (Humanize KR v2.3.2)

- 출처: https://github.com/epoko77-ai/im-not-ai
- 라이선스: MIT License, Copyright (c) 2026 epoko77-ai
- 라이선스 전문: `aikiller/vendor/humanize_kr/LICENSE.im-not-ai`

`aikiller/vendor/humanize_kr/` 아래 네 파일을 **원본 그대로** 포함합니다.

| 파일 | 용도 |
|---|---|
| `metrics.py` | v1.6 정량 지표 (쉼표 계열, 어휘 다양성, 한자 명사화 밀도) |
| `metrics_v2.py` | v2.0 post-editese 3축(단순화·정규화·간섭) + T1~T8 번역투 신호 |
| `baseline.json` | v1.6 기준선 — **실측 데이터** |
| `baseline_v2.json` | v2.0 기준선 — **전 셀 placeholder** |

수정하지 않았습니다. 이 프로젝트의 코드는 `aikiller/vendor/humanize_kr/__init__.py`를
통해 이들을 import만 합니다.

### 기준선의 캘리브레이션 상태

`baseline.json` (v1.6)은 실측입니다. 원본 파일의 `source` 필드:

> KatFish (Park et al., 인간 470 vs LLM 1,624편 / 에세이 771·시 945·초록 378)
> + LREAD 인간 판독 실험, user-corpus-2026-08-29 (칼럼 11·위키 521)

`baseline_v2.json` (v2.0)은 **추정값**입니다. 원본 파일의 `source` 필드:

> Placeholder. Toral 2019 simplification·normalisation·interference 정의 +
> 보고서 T1~T8 ko_manifestation 추정치. 비번역 한국어 (Sejong corpus·국립국어원
> 모두의 말뭉치 등) 정밀 측정은 별도 calibration 회차에서 수행.

모든 셀에 `"_placeholder": true, "calibration_due": true`가 붙어 있습니다.
그래서 이 프로젝트의 `detect.py`는 v2 z-score를 쓰지 않고 자체 휴리스틱
임계값(L3)으로 대체하며, `scripts/calibrate.py`가 사람 코퍼스로 이 셀들을
다시 측정합니다.

## 학술 근거

- Toral, A. (2019). *Post-editese: an Exacerbated Translationese.* — 단순화·정규화·간섭 3축
- Baker, M. (1993). 번역 보편소(translation universals)
- Toury, G. (1995). 간섭의 법칙(law of interference)
- Kirchenbauer et al. (2023). *A Watermark for Large Language Models* — (참고용, 미구현)
- Hans et al. (2024). *Spotting LLMs With Binoculars* — (참고용, 미구현)
