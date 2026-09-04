"""정량 지표 — 쉼표 계열(L1)과 리듬(L3).

표준 라이브러리만 쓴다. 형태소 분석기를 붙이지 않고 정규식과 어절 단위
근사로 처리한다. 정밀 분석은 patterns.py 의 패턴 레지스트리가 맡는다.

여기 있는 지표의 **정의**는 한국어 문체 계량 연구에서 쓰는 표준적인 것이다
(문장당 쉼표 수, 쉼표로 나뉜 절의 어절 길이 등). 기준선 수치는
baselines.py 에 출처와 함께 따로 두었다.
"""

from __future__ import annotations

import re
from typing import Any

# 문장 경계. 한국어는 세미콜론을 문장 구분에 거의 쓰지 않으므로 제외한다.
_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+")

# 어절 = 공백으로 나뉜 토큰
_WHITESPACE = re.compile(r"\s+")

_PUNCT = re.compile(r"[.,!?;:()\[\]{}\"'`~、。“”‘’\-]+")

# 연결어미. 뒤에 쉼표가 붙는지 보는 데 쓴다.
_CONNECTIVES = ("고", "며", "지만", "면서", "아서", "어서")

# 어절 끝에 온 연결어미만 센다. '고기'의 '고'를 세면 안 되므로 경계를 요구한다.
_CONNECTIVE_AT_BOUNDARY = re.compile(
    r"(?:%s)(?=[\s,.!?、。]|$)" % "|".join(_CONNECTIVES)
)
_CONNECTIVE_THEN_COMMA = re.compile(r"(?:%s)\s*," % "|".join(_CONNECTIVES))

# 종결어미 추출용 — 문장 끝 구두점 앞의 한글 1~3음절
_ENDING = re.compile(r"([가-힣]{1,3})[\s]*[.!?。]?\s*$")

# 서술체 종결. 셋 다 문어체 평서형이다.
_DECLARATIVE = ("한다", "된다", "이다", "된다", "난다", "진다")


# ---------------------------------------------------------------------------
# 토큰화
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    """문장 리스트. 줄바꿈도 문장 경계로 본다.

    한국어 글은 마침표 없이 줄만 바꾸는 경우가 흔해서(제목·목록·시)
    개행을 무시하면 한 문장이 비정상적으로 길어진다.
    """
    text = text.strip()
    if not text:
        return []
    out: list[str] = []
    for chunk in _SENTENCE_END.split(text):
        for line in chunk.split("\n"):
            line = line.strip()
            if line:
                out.append(line)
    return out


def eojeols(text: str) -> list[str]:
    return [t for t in _WHITESPACE.split(text.strip()) if t]


def strip_punct(token: str) -> str:
    return _PUNCT.sub("", token)


def last_eojeol(sentence: str) -> str:
    toks = eojeols(sentence)
    return strip_punct(toks[-1]) if toks else ""


# ---------------------------------------------------------------------------
# L1 — 쉼표 계열
#
# 한국어는 연결어미(-고, -며, -지만)로 절을 잇기 때문에 영어만큼 쉼표가
# 필요하지 않다. 영어를 옮겨 쓰는 문체일수록 쉼표가 많아진다.
# ---------------------------------------------------------------------------

def comma_inclusion_rate(text: str) -> float:
    """쉼표가 하나라도 들어간 문장의 비율 (0~1)."""
    sents = split_sentences(text)
    if not sents:
        return 0.0
    return sum(1 for s in sents if "," in s) / len(sents)


def comma_usage_rate(text: str) -> float:
    """문장당 평균 쉼표 개수."""
    sents = split_sentences(text)
    if not sents:
        return 0.0
    return sum(s.count(",") for s in sents) / len(sents)


def ending_comma_rate(text: str) -> float:
    """연결어미 뒤에 쉼표를 찍은 비율 (0~1).

    분모는 어절 경계에 온 연결어미 전체, 분자는 그중 쉼표가 뒤따르는 것.
    '~하고, ~한다'는 영어 쉼표 습관의 직접적인 흔적이다.
    """
    if not text.strip():
        return 0.0
    total = len(_CONNECTIVE_AT_BOUNDARY.findall(text))
    if not total:
        return 0.0
    return len(_CONNECTIVE_THEN_COMMA.findall(text)) / total


def comma_segment_length(text: str) -> float:
    """쉼표로 나뉜 구간의 평균 어절 수.

    쉼표가 없는 문장은 문장 전체를 한 구간으로 센다. 값이 크면 한 문장에
    긴 부속절을 이어 붙이는 영어식 구조라는 뜻이다.
    """
    lengths: list[int] = []
    for s in split_sentences(text):
        if "," not in s:
            lengths.append(len(eojeols(s)))
            continue
        for seg in s.split(","):
            seg = seg.strip()
            if seg:
                lengths.append(len(eojeols(seg)))
    if not lengths:
        return 0.0
    return sum(lengths) / len(lengths)


# ---------------------------------------------------------------------------
# L3 — 리듬
# ---------------------------------------------------------------------------

def ending_diversity(text: str) -> float:
    """종결어미의 다양성 = 서로 다른 어미 수 / 문장 수 (0~1).

    낮으면 '~이다. ~이다. ~이다.'처럼 같은 어미가 반복된다는 뜻이다.
    사람은 무의식적으로 변주하는 반면 AI 출력은 단조로운 경향이 있다.
    """
    keys: list[str] = []
    for s in split_sentences(text):
        m = _ENDING.search(s)
        if m:
            keys.append(m.group(1))
    if not keys:
        return 0.0
    return len(set(keys)) / len(keys)


def declarative_ratio(text: str) -> float:
    """문어체 평서형(~한다/~된다/~이다)으로 끝나는 문장의 비율 (0~1).

    0.75를 넘으면 문체가 평평하다는 신호다. 반대로 아주 낮으면 구어체이거나
    여러 문체가 섞였다는 뜻이라 그 자체로는 AI 신호가 아니다.
    """
    sents = split_sentences(text)
    if not sents:
        return 0.0
    hits = 0
    for s in sents:
        tail = last_eojeol(s)
        if tail and any(tail.endswith(d) for d in _DECLARATIVE):
            hits += 1
    return hits / len(sents)


def sentence_lengths(text: str) -> list[int]:
    """문장별 글자 수. 변동계수·장문 비율 계산에 쓴다."""
    return [len(s) for s in split_sentences(text) if s.strip()]


# ---------------------------------------------------------------------------
# 한 번에
# ---------------------------------------------------------------------------

L1_METRICS = (
    "comma_inclusion_rate",
    "comma_usage_rate",
    "ending_comma_rate",
    "comma_segment_length",
)

L3_METRICS = ("ending_diversity", "declarative_ratio")

# 백분율로 보고하는 지표 (기준선 단위와 맞추기 위함)
PERCENT_METRICS = frozenset({"comma_inclusion_rate", "ending_comma_rate"})


def compute(text: str) -> dict[str, Any]:
    """L1 + L3 원값과 문장 길이를 한 번에 낸다."""
    return {
        "comma_inclusion_rate": comma_inclusion_rate(text),
        "comma_usage_rate": comma_usage_rate(text),
        "ending_comma_rate": ending_comma_rate(text),
        "comma_segment_length": comma_segment_length(text),
        "ending_diversity": ending_diversity(text),
        "declarative_ratio": declarative_ratio(text),
        "n_sentences": len(split_sentences(text)),
        "sentence_lengths": sentence_lengths(text),
    }
