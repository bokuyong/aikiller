"""기준선 — 사람 글과 AI 글의 지표 실측 평균.

이 수치가 L1 계층을 "실측"으로 만들어 주는 근거다. 나머지 계층(L2 패턴 밀도,
L3 리듬, L4 사람 증거)의 가중치는 아직 추정치이며, 코드가 그 구분을 항상
화면에 노출한다.

출처
----
쉼표 계열 4종의 사람/AI 극값은 한국어 AI 텍스트 판별 연구인 **KatFish**
(Park et al.) 의 보고 수치다 — 사람 470편 vs LLM 1,624편(에세이 771 · 시 945 ·
초록 378) 대조 실험. column·report 장르 셀은 별도 사용자 코퍼스 실측
(칼럼 11편 · 위키 521편, 2026-08) 에서 왔다.

수치는 연구가 보고한 관측값(사실)이며 여기에 우리 형식으로 옮겨 적었다.
직접 재측정하려면 `scripts/calibrate.py` 를 자기 코퍼스로 돌리면 된다.

null 셀의 의미
--------------
장르에 따라 지표가 **뒤집히거나 판별력을 잃는다**. 그런 셀은 비워 둔다.
비운 셀은 z 계산에서 제외되며, 이게 격식체 오탐을 막는 장치 중 하나다.

  report / comma_inclusion_rate  설명문 사람 실측 50.25±18.32 vs AI 극 61.03.
                                 극간 거리(5.4)가 사람 내 분산(18.3)보다 작아
                                 판별이 성립하지 않는다.
  report / ending_comma_rate     설명문 사람 32.9% > AI 극 19.83% — 역전.
  report / comma_segment_length  설명문 사람 9.22 > AI 극 8.56 — 역전.
  column / ending_comma_rate     칼럼 사람 41.0% > AI 극 19.83% — 역전.
"""

from __future__ import annotations

SOURCE = (
    "KatFish (Park et al., 사람 470편 vs LLM 1,624편) + "
    "사용자 코퍼스 실측 2026-08 (칼럼 11 · 위키 521)"
)

# 장르 -> 지표 -> (사람 평균, AI 평균).  None 이면 그 장르에서 판별력이 없다.
# 단위는 metrics.PERCENT_METRICS 에 속하면 퍼센트, 아니면 원값.
REFERENCE: dict[str, dict[str, tuple[float, float] | None]] = {
    "essay": {
        "comma_inclusion_rate": (26.31, 61.03),
        "comma_usage_rate": (1.13, 2.56),
        "ending_comma_rate": (4.10, 19.83),
        "comma_segment_length": (4.35, 8.56),
    },
    "abstract": {
        "comma_inclusion_rate": (47.48, 65.21),
        "comma_usage_rate": (1.73, 2.40),
        "ending_comma_rate": (13.27, 28.01),
        "comma_segment_length": None,
    },
    "poetry": {
        "comma_inclusion_rate": (27.01, 42.90),
        "comma_usage_rate": (2.61, 4.84),
        "ending_comma_rate": (4.68, 15.57),
        "comma_segment_length": None,
    },
    "column": {
        "comma_inclusion_rate": (37.72, 61.03),
        "comma_usage_rate": (0.52, 2.56),
        "ending_comma_rate": None,          # 사람이 AI 극을 초과 — 역전
        "comma_segment_length": (7.07, 8.56),
    },
    "report": {
        "comma_inclusion_rate": None,       # 사람 내 분산 > 극간 거리
        "comma_usage_rate": (0.81, 2.56),
        "ending_comma_rate": None,          # 역전
        "comma_segment_length": None,       # 역전
    },
}

# 실측 셀이 없는 장르는 가장 가까운 것으로 넘긴다.
GENRE_ALIAS = {"blog": "essay", "news": "column", "qa": "essay"}

DEFAULT_GENRE = "essay"


def cells(genre: str) -> dict[str, tuple[float, float] | None]:
    """장르별 기준선. 모르는 장르는 별칭 -> 기본값 순으로 넘긴다."""
    g = GENRE_ALIAS.get(genre, genre)
    return REFERENCE.get(g) or REFERENCE[DEFAULT_GENRE]


def z_score(value: float, human: float, ai: float, *, percent: bool) -> float:
    """사람 극과 AI 극 사이에서의 위치. 양수면 AI 쪽이다.

    두 극의 평균만 알고 분산은 공개되지 않았으므로, 극간 거리의 절반을
    1σ 대용으로 쓴다. 즉 z=+2 는 "AI 평균에 도달"이지 "모집단 표준편차의
    2배"가 아니다. 이 근사를 쓰는 대신 detect.py 가 값을 ±3 으로 자른다.
    """
    val = value * 100 if percent else value
    sd = abs(ai - human) / 2.0
    if sd == 0:
        return 0.0
    return (val - human) / sd
