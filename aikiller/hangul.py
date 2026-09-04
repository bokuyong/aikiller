"""한글 형태 유틸 — 조사 자동 선택을 위한 종성 판별.

표준 라이브러리만 사용한다 (프로젝트 전역 원칙).
"""

from __future__ import annotations

_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3

# 종성 없는 한자어/외래어 예외는 다루지 않는다. 숫자·영문은 관용 발음 기준.
_DIGIT_JONGSEONG = {
    "0": True,   # 영 -> 종성 ㅇ
    "1": True,   # 일 -> ㄹ
    "3": True,   # 삼 -> ㅁ
    "6": True,   # 육 -> ㄱ
    "7": True,   # 칠 -> ㄹ
    "8": True,   # 팔 -> ㄹ
    "2": False, "4": False, "5": False, "9": False,
}


def has_jongseong(word: str) -> bool:
    """단어의 마지막 글자에 받침이 있으면 True.

    한글이 아니면 숫자 관용 발음 -> 그 외에는 받침 없음으로 간주한다.
    """
    if not word:
        return False
    ch = word[-1]
    code = ord(ch)
    if _HANGUL_START <= code <= _HANGUL_END:
        return (code - _HANGUL_START) % 28 != 0
    if ch in _DIGIT_JONGSEONG:
        return _DIGIT_JONGSEONG[ch]
    return False


def particle(word: str, with_jong: str, without_jong: str) -> str:
    """받침 유무에 따라 조사를 고른다. particle('사람', '이', '가') -> '이'."""
    return with_jong if has_jongseong(word) else without_jong


def subject_particle(word: str) -> str:
    return particle(word, "이", "가")


def object_particle(word: str) -> str:
    return particle(word, "을", "를")


def topic_particle(word: str) -> str:
    return particle(word, "은", "는")


def instrumental_particle(word: str) -> str:
    """'로' vs '으로'. 받침이 ㄹ이면 '로'."""
    if not word:
        return "로"
    ch = word[-1]
    code = ord(ch)
    if _HANGUL_START <= code <= _HANGUL_END:
        jong = (code - _HANGUL_START) % 28
        if jong == 0 or jong == 8:  # 받침 없음 또는 ㄹ
            return "로"
        return "으로"
    return "로"
