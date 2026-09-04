"""AI 생성 텍스트 탐지 엔진.

3개 증거 계층을 융합한다.

  L1 캘리브레이션 지표  baseline.json(v1.6)의 사람/AI 실측 평균 기반 z-score.
                        KatFish(인간 470 vs LLM 1,624편) + user corpus 실측.
                        → 이 계층만 실측 근거가 있다.
  L2 패턴 밀도          patterns.py 레지스트리 히트를 1,000자당 밀도로 환산.
  L3 리듬               문장 길이 변동성·종결어미 다양성·서술체 집중도.
                        baseline_v2.json이 placeholder라 z가 아닌 휴리스틱.

정직성 원칙
-----------
* 융합 가중치(WEIGHTS)는 **아직 실측 피팅되지 않았다**. `fusion_calibrated`
  플래그로 항상 노출한다. scripts/calibrate.py 실행 후에만 True가 된다.
* 150자 미만은 원리적으로 신호가 부족하다. 점수 대신 `insufficient`를 낸다.
* 최종 출력은 "AI가 썼다"가 아니라 "AI 문체 지표 점수 + 근거"다.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import dataclass, field, asdict
from typing import Any

from . import patterns as P
from .vendor import humanize_kr as hk

VERSION = "0.1.0"

# 최소 분량 — 이 아래로는 어떤 탐지기도 신뢰할 수 없다.
MIN_CHARS_SCORE = 150
MIN_CHARS_CONFIDENT = 400

# L1에 쓸 v1 지표. baseline.json에 human/ai **실측** 평균이 있는 것만 남긴다.
# 부호는 _z가 "양수 = AI 쪽"으로 맞춰 준다 — 단 그건 ai > human 인 지표에서만
# 성립한다.
#
# 제외한 것 (검수에서 드러난 결함):
#   lexical_diversity        극값이 0.65/0.55로 하드코딩돼 있는데 실제 한국어
#                            산문의 어절 TTR은 0.79~0.94다. 사람·AI 가릴 것 없이
#                            z가 +5를 넘어 클립 천장(+3)에 붙는 상수였다. 게다가
#                            ai(0.55) < human(0.65)이라 부호까지 반대여서, 사람
#                            글 점수를 통째로 끌어올리고 있었다.
#   hanja_nominalizer_density 극값이 6%/12%로 하드코딩("rough proxy" 주석)인데
#                            실측은 0.5~2.1%다. 항상 [-2.0, -1.3]에 머무는 상수.
CALIBRATED_METRICS = (
    "comma_inclusion_rate",
    "comma_usage_rate",
    "ending_comma_rate",
    "comma_segment_length",
)

# 융합 가중치 — 미피팅 추정값. calibrate.py가 덮어쓴다.
WEIGHTS = {
    "l1_calibrated_z": 1.15,
    "l2_pattern_density": 1.20,
    "l3_rhythm": 0.50,
    "l4_human_evidence": -1.10,   # 음수 — 사람 글의 증거는 점수를 깎는다
    "bias": -1.80,
    "_fitted": False,
}

# L1 의 음수 쪽 하한. L1 은 사실상 쉼표 하나의 현상을 네 지표로 잰 것이라,
# "쉼표가 적다"가 다른 계층의 AI 증거를 거부권처럼 눌러 버렸다(AI 칼럼 12.9점).
# 쉼표가 많으면 AI 증거로 세되, 적다고 해서 사람 증거로 크게 세지는 않는다.
L1_FLOOR = -0.5

_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fusion_weights.json")

# 관측 분포 기준(2026-08, 레지스터 9종 수동 표본):
#   사람 글 6.6~10.1 · AI 글 39.8~84.8
# 캘리브레이션 전까지의 잠정값이다. scripts/calibrate.py 가 가중치를 맞추면
# 이 경계도 다시 봐야 한다.
BANDS = ((60.0, "high"), (25.0, "medium"), (0.0, "low"))


def _load_weights() -> dict[str, Any]:
    path = os.path.abspath(_WEIGHTS_PATH)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            w = dict(WEIGHTS)
            w.update(loaded)
            return w
        except (OSError, json.JSONDecodeError):
            pass
    return dict(WEIGHTS)


def _sigmoid(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class Signal:
    """리포트에 노출되는 근거 한 줄."""
    layer: str            # "L1" | "L2" | "L3"
    key: str
    label: str
    value: float
    detail: str
    strength: float       # 0~1, 이 근거가 얼마나 세게 발화했나
    calibrated: bool


@dataclass
class SentenceScore:
    index: int
    start: int
    end: int
    text: str
    score: float
    hit_ids: list[str] = field(default_factory=list)
    hit_names: list[str] = field(default_factory=list)


@dataclass
class Report:
    version: str
    score: float
    band: str
    confidence: str
    fusion_calibrated: bool
    n_chars: int
    n_sentences: int
    genre: str
    signals: list[Signal]
    sentences: list[SentenceScore]
    layers: dict[str, float]
    metrics: dict[str, Any]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# 계층별 점수
# ---------------------------------------------------------------------------

def _layer1(base: dict[str, Any]) -> tuple[float, list[Signal]]:
    """캘리브레이션된 v1 지표의 평균 z. 양수일수록 AI 쪽."""
    zs = base.get("z_scores", {}) or {}
    metrics = base.get("metrics", {}) or {}
    vals: list[float] = []
    signals: list[Signal] = []
    for key in CALIBRATED_METRICS:
        z = zs.get(key)
        if z is None:
            continue
        zc = _clip(float(z), -3.0, 3.0)
        vals.append(zc)
        if abs(zc) >= 0.8:
            direction = "AI 쪽" if zc > 0 else "사람 쪽"
            signals.append(Signal(
                layer="L1", key=key, label=_LABELS.get(key, key),
                value=round(float(metrics.get(key, 0.0)), 4),
                detail=f"z={zc:+.2f} ({direction})",
                strength=_clip(abs(zc) / 3.0, 0.0, 1.0),
                calibrated=True,
            ))
    if not vals:
        return 0.0, signals
    return statistics.fmean(vals), signals


# 밀도 분모의 하한. 400자 문서에서 히트 1건이 2.5/1k가 되어 곧바로 cap에
# 걸리던 짧은 문서 편향을 없앤다.
MIN_DENSITY_DENOM = 800

# per_1k_cap 하한. 레지스트리의 cap 값들은 실측 없이 정한 것이라 2~3짜리가
# 34개나 되고, 그 탓에 밀도가 조금만 높아도 L2 전체가 포화했다.
MIN_PER_1K_CAP = 5.0


def _layer2(text: str, hits: list[P.Hit]) -> tuple[float, list[Signal], dict[str, int]]:
    """패턴 밀도. 1,000자당 가중 히트 수를 합산한다."""
    n_chars = max(len(text.strip()), MIN_DENSITY_DENOM)
    per_id: dict[str, int] = {}
    for h in hits:
        per_id[h.pattern_id] = per_id.get(h.pattern_id, 0) + 1

    raw = 0.0
    signals: list[Signal] = []
    for pid, count in per_id.items():
        pat = P.PATTERNS_BY_ID[pid]
        per_1k = count / n_chars * 1000
        capped = min(per_1k, max(pat.per_1k_cap, MIN_PER_1K_CAP))
        contrib = capped * pat.weight
        raw += contrib
        if contrib >= 0.5:
            signals.append(Signal(
                layer="L2", key=pid, label=f"[{pid}] {pat.name}",
                value=count,
                detail=f"{count}회 · 1,000자당 {per_1k:.1f}회 · {pat.category_name}",
                strength=_clip(contrib / 6.0, 0.0, 1.0),
                calibrated=False,
            ))
    signals.sort(key=lambda s: -s.strength)
    # 선형. 지수 포화(4*(1-exp(-raw/16)))는 raw=74에서 이미 상한의 99%라
    # 증거를 75% 지워도 값이 19%밖에 안 움직였다. 실측 raw 범위가 0~90 정도라
    # /20 이면 상단까지 변별이 살아 있고, 극단값만 6.0에서 자른다.
    return min(raw / 20.0, 6.0), signals, per_id


def _layer3(text: str, v2: dict[str, Any]) -> tuple[float, list[Signal]]:
    """리듬 균일성. baseline_v2가 placeholder라 휴리스틱 임계값을 쓴다."""
    sents = hk.split_sentences(text)
    lengths = [len(s) for s in sents if s.strip()]
    signals: list[Signal] = []
    score = 0.0

    if len(lengths) >= 4:
        mean_len = statistics.fmean(lengths)
        sd = statistics.pstdev(lengths)
        cv = sd / mean_len if mean_len else 0.0
        # 사람 글의 문장 길이 변동계수는 대체로 0.45~0.75.
        # 0.35 미만이면 기계적으로 고른 리듬.
        if cv < 0.35:
            s = _clip((0.35 - cv) / 0.25, 0.0, 1.0)
            score += s
            signals.append(Signal(
                layer="L3", key="sentence_len_cv", label="문장 길이 변동계수",
                value=round(cv, 3),
                detail=f"CV={cv:.2f} (사람 통상 0.45~0.75) · 평균 {mean_len:.0f}자",
                strength=s, calibrated=False,
            ))

    ed = v2.get("ending_diversity")
    if ed is not None and len(lengths) >= 4:
        if ed < 0.45:
            s = _clip((0.45 - ed) / 0.30, 0.0, 1.0)
            score += s
            signals.append(Signal(
                layer="L3", key="ending_diversity", label="종결어미 다양성",
                value=round(ed, 3),
                detail=f"{ed:.2f} — 같은 어미가 반복됩니다",
                strength=s, calibrated=False,
            ))

    # E-1 장문 부재. AI는 짧은 문장만 찍어내고 긴 호흡을 못 만든다.
    # (원 분류 체계는 11배 차이를 보고하나 이 저장소에 원자료가 없어 휴리스틱으로 둔다)
    # 문장이 적으면 장문이 없는 게 당연하다. 15문장 이상에서만 신호로 본다.
    if len(lengths) >= 15:
        long_ratio = sum(1 for n in lengths if n >= 100) / len(lengths)
        if long_ratio < 0.04:
            s = _clip((0.04 - long_ratio) / 0.04, 0.0, 1.0)
            score += s
            signals.append(Signal(
                layer="L3", key="long_sentence_absence", label="장문(100자+) 부재",
                value=round(long_ratio, 4),
                detail=f"장문 비율 {long_ratio:.1%} — 긴 호흡이 없습니다",
                strength=s, calibrated=False,
            ))

    ns = v2.get("normalisation_score")
    if ns is not None and len(lengths) >= 4 and ns > 0.75:
        s = _clip((ns - 0.75) / 0.25, 0.0, 1.0)
        score += s
        signals.append(Signal(
            layer="L3", key="normalisation_score", label="서술체(-한다/-된다) 집중도",
            value=round(ns, 3),
            detail=f"{ns:.0%}의 문장이 동일 서술형으로 끝납니다",
            strength=s, calibrated=False,
        ))

    return _clip(score, 0.0, 4.0), signals


def _layer_human(text: str) -> tuple[float, list[Signal]]:
    """사람 글의 증거. 점수를 깎는다.

    지금까지의 계층은 전부 "AI라는 증거"만 모았고, 그래서 격식체 산문이
    구조적으로 불리했다. 반대 방향 증거를 세는 것이 오탐 대책 중 가장 싸다.
    """
    n_chars = max(len(text.strip()), MIN_DENSITY_DENOM)
    counts = P.find_human_hits(text)
    raw = 0.0
    signals: list[Signal] = []
    for hid, count in counts.items():
        h = P.HUMAN_SIGNALS_BY_ID[hid]
        per_1k = count / n_chars * 1000
        contrib = min(per_1k, 6.0) * h.weight
        raw += contrib
        signals.append(Signal(
            layer="L4", key=hid, label=f"[{hid}] {h.name}",
            value=count,
            detail=f"{count}회 · 1,000자당 {per_1k:.1f}회 · 사람 글의 증거",
            strength=_clip(contrib / 4.0, 0.0, 1.0),
            calibrated=False,
        ))
    signals.sort(key=lambda s: -s.strength)
    return min(raw / 12.0, 3.0), signals


def _score_sentences(text: str, hits: list[P.Hit]) -> list[SentenceScore]:
    """문장 단위 점수 — 히트를 문장 경계에 매핑해 하이라이트 근거를 만든다."""
    sents = hk.split_sentences(text)
    out: list[SentenceScore] = []
    cursor = 0
    for i, s in enumerate(sents):
        idx = text.find(s, cursor)
        if idx < 0:
            idx = cursor
        start, end = idx, idx + len(s)
        cursor = end
        local = [h for h in hits if h.start >= start and h.start < end]
        weight_sum = sum(
            P.PATTERNS_BY_ID[h.pattern_id].weight * (0.6 + 0.2 * h.severity)
            for h in local
        )
        # 곡선 상수 5.0: 40자 문장에 중간 심각도 히트 1개 -> 약 45점.
        # 2.2였을 때는 히트 2개만으로 99점대에 포화해 변별력이 없었다.
        density = weight_sum / max(len(s), 1) * 100
        sc = _clip(100.0 * (1.0 - math.exp(-density / 5.0)), 0.0, 100.0)
        out.append(SentenceScore(
            index=i, start=start, end=end, text=s,
            score=round(sc, 1),
            hit_ids=[h.pattern_id for h in local],
            hit_names=[h.name for h in local],
        ))
    return out


_LABELS = {
    "comma_inclusion_rate": "쉼표 포함 문장 비율",
    "comma_usage_rate": "쉼표 사용 밀도",
    "ending_comma_rate": "연결어미 뒤 쉼표 비율",
    "comma_segment_length": "쉼표 구간 평균 길이",
    "hanja_nominalizer_density": "-적/-성/-화 명사화 밀도",
    "lexical_diversity": "어휘 다양성(TTR)",
}


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def analyze(text: str, genre: str = "essay") -> Report:
    """텍스트를 분석해 리포트를 낸다."""
    text = text.replace("\r\n", "\n")
    n_chars = len(text.strip())
    weights = _load_weights()
    notes: list[str] = []

    base = hk.compute_all_v2(text, genre=genre)
    v2 = base.get("v2_metrics", {}) or {}
    hits = P.find_hits(text)

    l1, sig1 = _layer1(base)
    l2, sig2, per_id = _layer2(text, hits)
    l3, sig3 = _layer3(text, v2)
    l4, sig4 = _layer_human(text)

    logit = (
        weights["l1_calibrated_z"] * max(l1, L1_FLOOR)
        + weights["l2_pattern_density"] * l2
        + weights["l3_rhythm"] * l3
        + weights.get("l4_human_evidence", -1.1) * l4
        + weights["bias"]
    )
    score = round(100.0 * _sigmoid(logit), 1)

    band = "low"
    for threshold, name in BANDS:
        if score >= threshold:
            band = name
            break

    if n_chars < MIN_CHARS_SCORE:
        confidence = "insufficient"
        notes.append(
            f"{n_chars}자로 판정 불가. 최소 {MIN_CHARS_SCORE}자가 필요합니다 — "
            "짧은 글은 어떤 탐지기도 신뢰할 수 없습니다."
        )
    elif n_chars < MIN_CHARS_CONFIDENT:
        confidence = "low"
        notes.append(f"{n_chars}자는 신호가 얕습니다. {MIN_CHARS_CONFIDENT}자 이상 권장.")
    else:
        confidence = "normal"

    if not weights.get("_fitted"):
        notes.append(
            "융합 가중치가 아직 실측 피팅되지 않았습니다. "
            "scripts/calibrate.py 실행 전에는 점수를 상대 비교용으로만 쓰세요."
        )
    if base.get("v2_baseline_warnings"):
        notes.append(
            f"L3 리듬 지표 {len(base['v2_baseline_warnings'])}개가 placeholder 기준선을 "
            "쓰고 있습니다(휴리스틱 임계값으로 대체 적용)."
        )

    sentences = _score_sentences(text, hits)
    signals = sorted(sig1 + sig2 + sig3 + sig4, key=lambda s: -s.strength)

    return Report(
        version=VERSION,
        score=score,
        band=band,
        confidence=confidence,
        fusion_calibrated=bool(weights.get("_fitted")),
        n_chars=n_chars,
        n_sentences=len(sentences),
        genre=genre,
        signals=signals,
        sentences=sentences,
        layers={
            "l1_calibrated_z": round(l1, 3),
            "l2_pattern_density": round(l2, 3),
            "l3_rhythm": round(l3, 3),
            "l4_human_evidence": round(l4, 3),
            "logit": round(logit, 3),
        },
        metrics={
            "v1": base.get("metrics", {}),
            "v1_z": base.get("z_scores", {}),
            "v2": v2,
            "interference_weighted_total": base.get(
                "v2_interference_index", {}).get("weighted_total"),
            "pattern_counts": per_id,
        },
        notes=notes,
    )
