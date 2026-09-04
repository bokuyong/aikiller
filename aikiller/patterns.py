"""AI 티 패턴 레지스트리 — 탐지기와 다듬기의 단일 진실 원천(SSOT).

분류 체계는 im-not-ai의 `ai-tell-taxonomy.md` v2.0(10대 카테고리)을 따르며,
패턴 ID도 그쪽 번호를 유지한다. 원본에 없는 자체 추가는 50번대를 쓴다.

설계 원칙
---------
1. 패턴 하나가 **탐지 근거**이자 **다듬기 규칙**이다. 두 벌로 관리하지 않는다.
2. 다듬기 규칙에는 `risk` 등급이 붙는다. 사용자가 고른 강도 이하만 적용된다.
     safe       — 의미 변화 없음이 문법적으로 보장됨 (이중피동 정규화 등)
     moderate   — 거의 항상 안전하나 문맥 예외가 드물게 있음
     aggressive — 문체를 실제로 바꿈. 사용자 확인 후 적용 권장
3. `repl=None`이면 탐지 전용이다. 근거로는 쓰되 자동 수정하지 않는다.
4. `min_count`는 "N회 이상일 때만 신호"를 뜻한다. 사람도 한두 번은 쓰는
   표현을 1회 발화로 잡으면 오탐이 난다.
5. `context`는 위치·문맥 조건이다. 같은 어구라도 결말부 문두에 있을 때만
   신호가 되는 패턴(D-11)이 있다.
6. 표준 라이브러리만 쓴다.

가중치 근거
-----------
`evidence` 필드에 실측 배수를 적는다. 사람 코퍼스 **0건**으로 관측된 패턴은
오탐 위험이 없어 가중치를 높게 준다. 반대로 D-4(hype 어휘)처럼 1.3배에
불과한 항목은 처방으로만 유지하고 판별 신호로는 낮춘다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .hangul import (
    has_jongseong,
    instrumental_particle,
    object_particle,
    subject_particle,
    topic_particle,
)

CATEGORIES = {
    "A": "번역투",
    "B": "영어 인용·용어 과다",
    "C": "구조적 AI 패턴",
    "D": "AI 특유 관용구",
    "E": "리듬 균일성",
    "F": "수식·중복",
    "G": "hedging 남용",
    "H": "접속사 남발",
    "I": "형식명사·의존명사 과다",
    "J": "시각 장식 남용",
}

RISK_ORDER = {"safe": 0, "moderate": 1, "aggressive": 2}


@dataclass(frozen=True)
class Pattern:
    id: str
    category: str
    name: str
    regex: re.Pattern
    severity: int          # 1(경미) ~ 3(심각)
    weight: float          # 탐지 점수 기여도
    risk: str = "moderate"
    repl: str | Callable[[re.Match], str] | None = None
    hint: str = ""
    per_1k_cap: float = 8.0   # 1000자당 이 횟수를 넘으면 기여도 포화
    min_count: int = 1        # 문서 내 이 횟수 미만이면 신호로 세지 않는다
    context: Callable[[str, re.Match], bool] | None = None
    evidence: str = ""        # 실측 근거 (사람 vs AI 밀도 등)

    @property
    def category_name(self) -> str:
        return CATEGORIES.get(self.category, self.category)

    @property
    def rewritable(self) -> bool:
        return self.repl is not None


# ---------------------------------------------------------------------------
# 치환 헬퍼
# ---------------------------------------------------------------------------

_DOUBLE_PASSIVE = {
    "되어지지": "되지", "되어졌": "됐", "되어진": "된", "되어지": "되",
    "보여졌": "보였", "보여진": "보인", "보여지": "보이",
    "잊혀졌": "잊혔", "잊혀진": "잊힌", "잊혀지": "잊히",
    "쓰여졌": "쓰였", "쓰여진": "쓰인", "쓰여지": "쓰이",
    "불려졌": "불렸", "불려진": "불린", "불려지": "불리",
    "나뉘어졌": "나뉘었", "나뉘어진": "나뉜", "나뉘어지": "나뉘",
    "모여졌": "모였", "모여진": "모인",
    "짜여졌": "짜였", "짜여진": "짜인",
    "닫혀졌": "닫혔", "열려졌": "열렸", "갈려졌": "갈렸",
    # '-어지-' 뒤에 어미가 바로 붙는 활용형 (되어져야/보여져서 …)
    "되어져야": "되어야", "되어져서": "되어서", "되어져": "되어",
    "보여져야": "보여야", "보여져서": "보여서", "보여져": "보여",
    "쓰여져야": "쓰여야", "쓰여져": "쓰여",
    "불려져": "불려", "잊혀져": "잊혀", "나뉘어져": "나뉘어",
    "모여져": "모여", "짜여져": "짜여",
}
_DOUBLE_PASSIVE_RE = re.compile(
    "|".join(sorted(map(re.escape, _DOUBLE_PASSIVE), key=len, reverse=True))
)

_PROGRESSIVE_MAP = {
    "있다": "한다", "있습니다": "합니다", "있는": "하는",
    "있었다": "했다", "있었습니다": "했습니다", "있으며": "하며",
}

# "~를 통해" 치환에서 제외할 선행어 (사람·대명사는 '~로'가 어색하다)
_TONGHAE_BLOCK = {
    "그", "그녀", "그들", "우리", "저희", "당신", "본인", "자신",
    "사람", "친구", "동료", "선생님", "전문가", "담당자",
}

_DEUL_PARTICLE_FIX = {
    "이": "sub", "가": "sub",
    "은": "top", "는": "top",
    "을": "obj", "를": "obj",
    "과": "and", "와": "and",
}

# '~하다'로 자연스럽게 축약되는 서술성 명사만 치환한다.
# '업무를 진행했다' -> '업무했다' 같은 오적용을 막는다.
_PREDICATIVE_NOUNS = {
    "조사", "분석", "연구", "검토", "실험", "평가", "점검", "논의", "협의",
    "수정", "개선", "검증", "측정", "관찰", "인터뷰", "설문", "교육", "훈련",
    "홍보", "정비", "개발", "설계", "테스트", "회의", "발표", "심사", "감사",
    "촬영", "번역", "상담", "면담", "실습", "시험", "진단", "치료", "수술",
}


def _fix_double_passive(m: re.Match) -> str:
    return _DOUBLE_PASSIVE[m.group(0)]


def _fix_tonghae(m: re.Match) -> str:
    noun = m.group(1)
    if noun in _TONGHAE_BLOCK:
        return m.group(0)
    return noun + instrumental_particle(noun)


def _fix_gajigo(m: re.Match) -> str:
    noun = m.group(1)
    return f"{noun}{subject_particle(noun)} 있{m.group(2)}"


def _fix_progressive(m: re.Match) -> str:
    inner = re.match(r"(.*하)고\s*있(.*)", m.group(0))
    if not inner:
        return m.group(0)
    mapped = _PROGRESSIVE_MAP.get(inner.group(2))
    if mapped is None:
        return m.group(0)
    return inner.group(1) + mapped


def _fix_deul(m: re.Match) -> str:
    """'많은 사람들이' -> '많은 사람이'. '들'을 지운 뒤 조사를 종성에 맞게 재선택한다.

    '다양한 요소들이' -> '다양한 요소가' (요소는 받침이 없으므로 '이'가 아니라 '가').
    """
    head, gap, noun, part = m.group(1), m.group(2), m.group(3), m.group(4)
    kind = _DEUL_PARTICLE_FIX.get(part)
    if kind == "sub":
        part = subject_particle(noun)
    elif kind == "top":
        part = topic_particle(noun)
    elif kind == "obj":
        part = object_particle(noun)
    elif kind == "and":
        part = "과" if has_jongseong(noun) else "와"
    return f"{head}{gap}{noun}{part}"


def _fix_inhae(m: re.Match) -> str:
    return f"{m.group(1)} 때문에"


def _fix_progress_noun(m: re.Match) -> str:
    if m.group(1) not in _PREDICATIVE_NOUNS:
        return m.group(0)
    return f"{m.group(1)}{m.group(2)}"


def _fix_rago_hal_su(m: re.Match) -> str:
    """'X(이)라고 할 수 있다' -> 'X(이)다'. 경어법을 원문에 맞춰 유지한다.

    수량자가 탐욕적이면 group(1)이 '이라고'의 '이'까지 먹어서 '혁신이입니다'가
    된다. 정규식을 게으르게 두고 계사 '이'를 group(2)로 따로 받는다.
    """
    noun = m.group(1)
    if m.group(3) == "습니다":
        return f"{noun}입니다"
    return f"{noun}이다" if has_jongseong(noun) else f"{noun}다"


def _fix_dago_hal_su(m: re.Match) -> str:
    """'~다고 볼 수 있다' -> '~다'.

    '있습니다'로 끝나면 해라체로 떨어뜨리지 않기 위해 건드리지 않는다
    (E-7 청자 경어법 일관성). 그런 구간은 탐지 근거로만 남는다.
    """
    if m.group(2) == "습니다":
        return m.group(0)
    return m.group(1)


def _fix_saryodoenda(m: re.Match) -> str:
    """'사료된다/여겨진다' -> '보인다'. 합쇼체면 '보입니다'로 맞춘다.

    고정 문자열로 치환하면 '여겨집니다'가 '보인다'가 되어 경어법이 깨진다.
    """
    return "보입니다" if m.group(0).endswith("니다") else "보인다"


def _fix_passive_progressive(m: re.Match) -> str:
    """'심화되고 있다' -> '심화된다'. 피동 진행만 대상으로 한다."""
    stem, kind, tail = m.group(1), m.group(2), m.group(3)
    base = "된" if kind == "되" else "진"
    table = {
        "다": base + "다", "습니다": ("됩니다" if kind == "되" else "집니다"),
        "는": ("되는" if kind == "되" else "지는"),
        "었다": ("됐다" if kind == "되" else "졌다"),
        "었습니다": ("됐습니다" if kind == "되" else "졌습니다"),
        "으며": ("되며" if kind == "되" else "지며"),
    }
    mapped = table.get(tail)
    return stem + mapped if mapped else m.group(0)


def _fix_hedge_stack(m: re.Match) -> str:
    return f"{m.group(1)} 수 있다"


# ---------------------------------------------------------------------------
# 문맥 조건
# ---------------------------------------------------------------------------

def _in_final_30pct(text: str, m: re.Match) -> bool:
    """글의 마지막 30% 구간인가. D-11 결말부 시간지평 판정용."""
    return m.start() / max(len(text), 1) >= 0.70


def _at_sentence_start(text: str, m: re.Match) -> bool:
    """문두인가. 앞이 문장부호이거나 글의 시작이면 참."""
    i = m.start() - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    return i < 0 or text[i] in ".!?\n"


def _final_and_sentence_start(text: str, m: re.Match) -> bool:
    return _in_final_30pct(text, m) and _at_sentence_start(text, m)


# ---------------------------------------------------------------------------
# 패턴 정의
# ---------------------------------------------------------------------------

PATTERNS: list[Pattern] = [

    # ======================= A. 번역투 =======================
    Pattern(
        "A-1", "A", "'~에 대하여/대해서' 남발",
        re.compile(r"에\s*(대하여|대해서|대해)(?![가-힣])"),
        severity=1, weight=0.2, risk="moderate", repl=None, min_count=4,
        hint="반복이 잦으면 줄이세요. 다만 사람이 3배 더 쓰는 표현이라 "
             "그 자체가 AI 신호는 아닙니다.",
        evidence="⚠ 실측 역전 — 사람이 약 3배 더 씀. 판별 신호 아님",
        per_1k_cap=6.0,
    ),
    Pattern(
        "A-2", "A", "'~을 통해' 도구격 번역투",
        re.compile(r"([가-힣]{2,8})(?:을|를)\s*통해서?"),
        severity=1, weight=0.3, risk="aggressive", repl=_fix_tonghae, min_count=3,
        hint="한 문서에서 만능 연결어처럼 반복될 때만 줄이세요. 1~2회는 정상입니다.",
        evidence="⚠ 실증 기각 — 비번역 한국어(84.4)가 번역문(42.1)보다 2배 더 씀",
    ),
    Pattern(
        "A-3", "A", "'~에 있어서' 번역투",
        re.compile(r"에\s*있어서?(?![가-힣])"),
        severity=2, weight=1.0, risk="moderate", repl=None,
        hint="'~에 있어서' → '~에서'. 다만 '도서관에 있어서'처럼 존재동사일 수도 "
             "있어 자동 치환하지 않습니다. 직접 판단하세요.",
    ),
    Pattern(
        "A-4", "A", "'~라는 점에서'",
        re.compile(r"(라는|다는)\s*점에서"),
        severity=1, weight=0.7, risk="moderate", repl=None, min_count=2,
        hint="'~라는 점에서 의미가 있다' → '~라서 의미가 있다'.",
    ),
    Pattern(
        "A-5", "A", "'~와 관련하여/관련된'",
        re.compile(r"(와|과)\s*관련(하여|한|해서|된|되어)"),
        severity=1, weight=0.7, risk="moderate", repl=None, min_count=2,
        hint="'X와 관련된 문제' → 'X의 문제' 또는 'X 문제'.",
    ),
    Pattern(
        "A-6", "A", "'~에 기반하여 / ~을 바탕으로' 남발",
        re.compile(r"(에\s*기반(하여|한|해)|(을|를)\s*바탕으로|에\s*근거하여)"),
        severity=1, weight=0.8, risk="moderate", repl=None, min_count=2,
        hint="'데이터에 기반하여' → '데이터로'. based on 직역입니다.",
    ),
    Pattern(
        "A-7", "A", "'가지고 있다' (have 직역)",
        re.compile(r"([가-힣]{2,8})(?:을|를)\s*가지고\s*있(다|습니다|는|었다|으며)"),
        severity=2, weight=1.4, risk="moderate", repl=_fix_gajigo,
        hint="'X를 가지고 있다' → 'X가 있다'.",
    ),
    Pattern(
        "A-8", "A", "이중 피동",
        _DOUBLE_PASSIVE_RE,
        severity=3, weight=2.0, risk="safe", repl=_fix_double_passive,
        hint="'되어진다' → '된다'. 피동을 두 번 겹쳐 쓴 비문입니다.",
    ),
    Pattern(
        "A-9", "A", "'~에 의해' 피동 주체",
        re.compile(r"[가-힣]{2,}에\s*의(해|한|하여)"),
        severity=2, weight=1.3, risk="moderate", repl=None,
        hint="'A에 의해 B되다' → 'A가 B하다' 능동으로 뒤집으세요.",
    ),
    Pattern(
        "A-11", "A", "'~을 위해' 목적절 남발",
        re.compile(r"([가-힣]{2,10})(?:을|를)\s*위(해|하여|한)(?![가-힣])"),
        severity=1, weight=0.2, risk="moderate", repl=None, min_count=4,
        hint="반복이 잦으면 '~하려고'로 변주하세요.",
        evidence="⚠ 실측 보수화 — 사람이 1.5배 더 씀",
        per_1k_cap=6.0,
    ),
    Pattern(
        "A-12", "A", "'만들어지다 / 이루어지다'",
        re.compile(r"(만들어(진다|졌다|지고|진|져)|이루어(진다|졌다|지고|진|져))"),
        severity=1, weight=0.8, risk="moderate", repl=None, min_count=2,
        hint="be made/consist of 직역입니다. 행위자를 찾아 능동으로.",
    ),
    Pattern(
        "A-14", "A", "'그리고'로 절 연결",
        re.compile(r"(?<![가-힣]),?\s*그리고\s+[가-힣]"),
        severity=1, weight=0.6, risk="moderate", repl=None, min_count=3,
        hint="한국어는 연결어미(-고, -며)로 잇습니다. and 직역을 줄이세요.",
    ),
    Pattern(
        "A-15", "A", "무생물·추상 주어 + 만능 동사",
        re.compile(
            r"(이|본|해당|그)?\s*(연구|논문|글|보고서|기사|분석|조사|결과|현상|변화|기술|시대)"
            r"(은|는|이|가)\s*[^.!?]{0,60}?"
            r"(보여준다|시사한다|나타낸다|제시한다|강조한다|드러낸다|말해준다|던진다|요구한다)"
        ),
        severity=2, weight=1.1, risk="moderate", repl=None,
        hint="'이 연구는 ~을 보여준다' → '이 연구에서 ~가 드러났다'. 다만 한국어 "
             "논문에서는 굳은 서술이라 학술 장르에서는 정상입니다.",
        evidence="⚠ 밀도 실측 없음 — 학술 장르 오탐 주의",
        per_1k_cap=3.0,
    ),
    Pattern(
        "A-16", "A", "영어 대명사 직역 (그/그녀/그것)",
        re.compile(r"(?<![가-힣])(그는|그녀는|그들은|그것은|이것은|그의|그녀의|그것을|이것을|그들의)"),
        severity=1, weight=0.1, risk="moderate", repl=None, min_count=5,
        hint="번역문이라면 대명사를 줄이세요. 자생 한국어 산문에는 해당 없습니다.",
        evidence="⚠ 실측 역전 — 사람 2.99 vs AI 0.38 (×0.13). 사람 쪽이 8배 높음",
    ),
    Pattern(
        "A-17", "A", "복수 접미사 '-들' 남용",
        # 조사 '이' 뒤에 어미가 오면 그건 주격조사가 아니라 계사 '이-'다.
        # (들이었다 / 들이지만 / 들이며 …) 구분하지 않으면 '요소가었다'가 된다.
        re.compile(
            r"(많은|여러|다양한|수많은|각종|모든|온갖)(\s+)([가-힣]{1,6}?)들"
            r"(이(?![가-힣])|가|은|는|을|를|과|와)"
        ),
        severity=1, weight=0.5, risk="aggressive", repl=_fix_deul,
        hint="'많은 사람들이' → '많은 사람이'. 다만 유정명사의 '-들'은 오류가 아닙니다.",
        min_count=2,
        evidence="⚠ 원 분류 체계에서 hold 상태(양성 0건). aggressive 에서만 적용",
    ),
    Pattern(
        "A-19", "A", "이중 조사 ('~에서의' 등)",
        # 맨 '로의'는 뺐다 — 경로의·고속도로의·회로의·진로의가 전부 걸린다.
        re.compile(r"(에서의|에로의|으로의|에의|에게로의|으로부터의|로부터의)"),
        severity=2, weight=1.0, risk="moderate", repl=None,
        hint="'~에서의 변화' → '~에서 일어난 변화'처럼 풀어 쓰세요.",
    ),
    Pattern(
        "A-20", "A", "피동 진행 '~되고 있다 / ~지고 있다'",
        # 원 분류 체계의 신호는 **피동** 진행이다. 능동 '~하고 있다'는 명시된
        # 대조군(사람 대비 격차 없음)이라 잡으면 순수 오탐이 된다.
        re.compile(r"([가-힣]{1,8})(되|지)고\s*있(다|습니다|는|었다|었습니다|으며)"),
        severity=2, weight=1.1, risk="moderate", repl=_fix_passive_progressive,
        hint="'심화되고 있다' → '심화된다'. 피동에 진행을 겹쳐 쓴 영어 직역입니다.",
        evidence="사람 1.38 vs AI 3.44. 능동 '~하고 있다'는 ×1.28로 격차 없음(대조군)",
    ),
    Pattern(
        "A-21", "A", "범위 상승 '단순한 X를 넘어'",
        re.compile(r"(단순한?\s*[^.!?]{0,20}(을|를)\s*넘어|이제\s*[^.!?]{0,15}(은|는)\s*[^.!?]{0,15}(을|를)\s*넘어)"),
        severity=2, weight=1.2, risk="moderate", repl=None,
        hint="'단순한 도구를 넘어' 같은 범위 상승 공식은 AI 상투구입니다.",
        per_1k_cap=3.0,
    ),
    Pattern(
        "A-50", "A", "'~로 인해' 번역투",
        # 어두 경계 + 게으른 수량자. 탐욕적이면 '전쟁으로'를 '전쟁으'+'로'로
        # 쪼개 '전쟁으 때문에'라는 비문을 만든다.
        re.compile(r"(?<![가-힣])([가-힣]{1,8}?)(?:으로|로)\s*인해서?"),
        severity=1, weight=0.9, risk="moderate", repl=_fix_inhae,
        hint="'X로 인해' → 'X 때문에'.",
    ),
    Pattern(
        "A-51", "A", "'~을 진행/실시/수행하다'",
        re.compile(r"([가-힣]{2,8})(?:을|를)\s*(?:진행|실시|수행)(했|하고|하며|한|하는|하여|합니다|했습니다)"),
        severity=1, weight=0.9, risk="moderate", repl=_fix_progress_noun,
        hint="'조사를 진행했다' → '조사했다'.",
    ),

    # ======================= B. 영어 과다 =======================
    Pattern(
        "B-1", "B", "영어 괄호 병기 과다",
        re.compile(r"[가-힣]+\s*\([A-Za-z][A-Za-z\s\-]{2,}\)"),
        severity=1, weight=0.8, risk="moderate", repl=None, min_count=2,
        hint="번역 가능한 용어는 괄호 병기를 지우세요. 첫 등장 1회면 충분합니다.",
        per_1k_cap=4.0,
    ),
    Pattern(
        "B-4", "B", "'~라고 알려진 / ~로 일컬어지는'",
        re.compile(r"(라고\s*알려진|로\s*일컬어지는|라\s*불리는|로\s*불리는)"),
        severity=1, weight=0.7, risk="moderate", repl=None,
        hint="known as 직역입니다. 그냥 단언하거나 출처를 밝히세요.",
    ),

    # ======================= C. 구조 =======================
    Pattern(
        "C-1", "C", "기계적 병렬 열거 '첫째/둘째/셋째'",
        re.compile(r"(?<![가-힣])(첫째|둘째|셋째|넷째|첫 번째로|두 번째로|세 번째로)[,\s]"),
        severity=2, weight=1.1, risk="moderate", repl=None,
        hint="번호 나열을 문장 흐름으로 녹이세요.",
        per_1k_cap=4.0,
    ),
    Pattern(
        "C-2", "C", "과도한 불릿 리스트",
        re.compile(r"(?m)^\s*[-*•·]\s+\S"),
        severity=1, weight=0.5, risk="moderate", repl=None, min_count=5,
        hint="산문으로 풀어 쓸 수 있는 항목까지 불릿으로 쪼개지 마세요.",
        per_1k_cap=10.0,
    ),
    Pattern(
        "C-5", "C", "이모지 남발",
        # U+2600~27BF 범위는 뺐다 — ★☆♠♥♦♣✓♪ 같은 일반 기호가 들어 있어
        # '평점 ★★★☆☆'가 통째로 지워졌다. 결합문자(VS16·ZWJ)와 국기·키캡도 함께 처리.
        re.compile(
            r"(?:[0-9#*]\uFE0F?\u20E3"
            r"|[\U0001F1E6-\U0001F1FF]{2}"
            r"|[\U0001F300-\U0001FAFF\U0001F004]"
            r"|[✅❌❓❗✨⚠⚡⭐⭕⁉‼]"
            r"|[\uFE0F\u200D])+"
        ),
        severity=2, weight=1.0, risk="safe", repl="",
        hint="문서형 글에서 이모지는 AI 서식 습관입니다.",
    ),
    Pattern(
        "C-8", "C", "대칭 대구 'A인가, B인가'",
        re.compile(r"[^.!?\n]{0,30}인가[,?]\s*[^.!?\n]{0,30}인가"),
        severity=3, weight=2.4, risk="moderate", repl=None,
        hint="질문형 대구는 AI 시그니처입니다. 하나만 남기고 단언으로 바꾸세요.",
        per_1k_cap=3.0,
        min_count=2,
        evidence="v2.3 실측 최강 신호(약 12배). 단 사람 다용자 존재 — 2회부터 셈",
    ),
    Pattern(
        "C-8b", "C", "부정대구 'A가 아니라 B'",
        re.compile(
            r"([가-힣]{1,12})(?:이|가)\s*아니라\s*([가-힣]{1,12})"
            r"|것이\s*아니라|것은\s*아니다"
        ),
        severity=3, weight=2.4, risk="moderate", repl=None,
        hint="부정 대구를 해체해 한쪽만 단언하세요. 'A가 아니라 B다' → 'B다'.",
        per_1k_cap=4.0,
        min_count=2,   # 1회로 낮추지 말 것 — 사람 다용자가 실재한다
        evidence="AI 5.8 vs 인간 0.6 (9.2배, G²=41.7, p<0.0001). "
                 "사람 24편 0건 vs AI 24편 27건, 3모델 공통",
    ),
    Pattern(
        "C-9", "C", "숫자 괄호 인덱싱 '1) 2) 3)'",
        re.compile(r"(?<![0-9])[1-9]\)\s"),
        severity=1, weight=0.7, risk="moderate", repl=None, min_count=3,
        hint="문장 안 번호 매김을 줄이고 흐름으로 이으세요.",
    ),
    Pattern(
        "C-10", "C", "콜론 부제 헤딩 'X: Y'",
        re.compile(r"(?m)^#{1,4}\s+[^\n:]{2,30}:\s*\S"),
        severity=1, weight=0.8, risk="moderate", repl=None, min_count=2,
        hint="'제목: 부제' 공식은 AI 헤딩 습관입니다.",
    ),
    Pattern(
        "C-11a", "C", "연결어미 뒤 쉼표 (명확형)",
        # '고'는 뺐다 — 사고·광고·보고·창고·냉장고… 명사 말음절과 구별할 수
        # 없어서 나열 쉼표를 지워 버린다. 나머지 어미는 명사 말음절로 거의 안 온다.
        # 개행을 먹지 않도록 \s 대신 [ \t] 를 쓴다(문단 구조 보존).
        re.compile(r"(며|지만|면서|아서|어서)[ \t]*,[ \t]*"),
        severity=2, weight=1.2, risk="safe",
        repl=lambda m: m.group(1) + " ",
        hint="'~하며, ~한다' → '~하며 ~한다'. AI가 영어 습관대로 쉼표를 찍습니다. "
             "다만 규범상 금지는 아니라 개인 습관 편차가 큽니다.",
        per_1k_cap=12.0,
        min_count=2,
        evidence="에세이 실측 — 인간 4.10% vs AI 19.83% (4.84배)",
    ),
    Pattern(
        "C-11b", "C", "'~고,' 뒤 쉼표 (탐지 전용)",
        # 자동 치환하지 않는다. '사고, 화재, 침수' 같은 나열을 망가뜨린다.
        re.compile(r"(?<=[가-힣])고[ \t]*,[ \t]*(?=[가-힣])"),
        severity=1, weight=0.5, risk="moderate", repl=None,
        hint="연결어미 '-고' 뒤 쉼표라면 지우세요. 명사 나열이면 그대로 두세요.",
        per_1k_cap=8.0, min_count=3,
    ),
    Pattern(
        "C-50", "C", "볼드 강조 과다",
        re.compile(r"\*\*[^*\n]{1,40}\*\*"),
        severity=1, weight=0.6, risk="aggressive",
        repl=lambda m: m.group(0)[2:-2], min_count=3,
        hint="본문 중간 볼드는 AI 서식 습관입니다.",
        per_1k_cap=6.0,
    ),

    # ======================= D. AI 관용구 =======================
    Pattern(
        "D-1a", "D", "결산 lexicon ('결론적으로' 류)",
        re.compile(r"(?<![가-힣])(결론적으로|요약하면|종합하면|정리하자면|종합해\s*보면)[,\s]*"),
        severity=3, weight=1.8, risk="moderate", repl="",
        context=_at_sentence_start,   # 문중에서 지우면 '이를 세 가지다'가 된다
        hint="결론은 내용으로 보여주세요. 예고하지 마세요.",
        per_1k_cap=3.0,
        evidence="KatFish lexicon-grounded 6대 지표 5번 · 인간 판독 정확도 60→90% 핵심 항목",
    ),
    Pattern(
        "D-1b", "D", "'~라고 할 수 있다'",
        re.compile(r"(?<![가-힣])([가-힣]{2,10}?)(이)?라고\s*(?:할|볼)\s*수\s*있(다|습니다)"),
        severity=2, weight=1.4, risk="moderate", repl=_fix_rago_hal_su,
        hint="'~라고 할 수 있다' → '~다'. 불필요한 완충입니다.",
    ),
    Pattern(
        "D-1c", "D", "'~다고 할 수 있다'",
        re.compile(r"([가-힣]{1,10}다)고\s*(?:할|볼)\s*수\s*있(다|습니다)"),
        severity=2, weight=1.4, risk="moderate", repl=_fix_dago_hal_su,
        hint="'~해야 한다고 볼 수 있다' → '~해야 한다'. 완충을 걷어내세요.",
    ),
    Pattern(
        "D-1d", "D", "'~라 하겠다 / ~에 다름 아니다'",
        re.compile(r"(라\s*하겠다|라\s*할\s*것이다|에\s*다름\s*아니다)"),
        severity=2, weight=1.5, risk="moderate", repl=None,
        hint="문어체 상투 결산입니다. 단언으로 바꾸세요.",
    ),
    Pattern(
        "D-2", "D", "의의·중요성 과장",
        re.compile(
            r"(시사하는\s*바가\s*크|시사점을\s*(준다|제공한다)|의미하는\s*바가\s*크"
            r"|주목할\s*만하|눈여겨볼\s*만하|간과할\s*수\s*없|무시할\s*수\s*없"
            r"|의미가\s*적지\s*않|의미심장|방점을\s*찍|지평을\s*열)"
        ),
        severity=2, weight=1.1, risk="moderate", repl=None, min_count=2,
        hint="무엇이 왜 중요한지 직접 쓰세요.",
        evidence="⚠ 밀도 실측 없음 — 학술 산문의 관용 평가어이기도 함",
        per_1k_cap=3.0,
    ),
    Pattern(
        "D-3", "D", "열거 도입 공식",
        re.compile(
            r"(크게\s*[일이삼사오육1-9]{1,2}\s*가지로|다음과\s*같(다|습니다|이|은)"
            r"|아래와\s*같(다|습니다|이)|다음과\s*같이\s*요약)"
        ),
        severity=1, weight=0.9, risk="moderate", repl=None,
        hint="예고 없이 바로 내용을 쓰세요.",
        per_1k_cap=4.0,
    ),
    Pattern(
        "D-4", "D", "hype 어휘",
        re.compile(
            r"(?<![가-힣])(혁신적인|획기적인|전례\s*없는|압도적|막강한|폭발적|파격적"
            r"|대대적|눈부신|비약적인|괄목할)"
        ),
        severity=1, weight=0.4, risk="moderate", repl=None, min_count=3,
        hint="구체적 수치나 사례로 바꾸세요. (처방으로는 유효하나 판별 신호로는 약합니다)",
        per_1k_cap=4.0,
        evidence="⚠ 근거 약함 — 사람 0.26 vs AI 0.34 (1.3배). 과업매칭 AI 0.00",
    ),
    Pattern(
        "D-5", "D", "의인화된 추상 주어",
        re.compile(
            r"(?<![가-힣])(기술|시대|시장|데이터|알고리즘|경쟁|변화|혁신|미래)"
            r"(이|가|은|는)\s*[^.!?]{0,20}?(묻는다|던진다|말한다|외친다|증명한다|부른다|요구한다)"
        ),
        severity=2, weight=1.3, risk="moderate", repl=None,
        hint="실제 행위자로 주어를 바꾸세요 ('두 회사의 경쟁은', '엔지니어들은').",
        per_1k_cap=3.0,
    ),
    Pattern(
        "D-6", "D", "완결 공식형 결말 '~할 때입니다'",
        re.compile(r"([가-힣]{2,}할|나아갈|넘어갈)\s*(때|시점|순간)(입니다|이다|다)"),
        severity=2, weight=1.5, risk="moderate", repl=None,
        hint="구체 동사 단언으로. 한 문서에 한 번만.",
        per_1k_cap=2.0,
    ),
    Pattern(
        "D-7", "D", "변환 공식 'X에서 Y로'",
        re.compile(r"['\"'‘“][^'\"'’”\n]{2,20}['\"'’”]\s*(에서|을|를)\s*(넘어\s*)?['\"'‘“][^'\"'’”\n]{2,20}['\"'’”]\s*로"),
        severity=2, weight=1.4, risk="moderate", repl=None,
        hint="변환 공식을 직접 단언으로 푸세요. 문서당 1회 이하.",
        per_1k_cap=2.0,
    ),
    Pattern(
        "D-8a", "D", "분열문 '필요한/중요한 것은 ~이다'",
        re.compile(r"(?<![가-힣])(필요한|중요한|핵심적인|시급한)\s*(것은|건)\s*[^.!?\n]{1,40}?(이다|다|입니다)"),
        severity=3, weight=2.3, risk="moderate", repl=None,
        hint="주어-서술 직결로 펴세요. '필요한 것은 방향이다' → '방향이 필요하다'.",
        per_1k_cap=3.0,
        evidence="실측 사람 0.09 vs AI 0.92 (10배). '필요한 것은'은 사람 코퍼스 0건",
    ),
    Pattern(
        "D-8b", "D", "분열문 변종 '문제는/핵심은/관건은'",
        re.compile(r"(?<![가-힣])(문제는|핵심은|관건은|답은|더\s*심각한\s*것은|뼈아픈\s*것은)\s+[^.!?\n]{1,40}?(이다|다|입니다|는\s*점이다|데\s*있다)"),
        severity=2, weight=1.6, risk="moderate", repl=None,
        hint="같은 분열문입니다. '논쟁의 핵심은 생산성이다' → '논쟁은 생산성을 둘러싼 것이다'.",
        per_1k_cap=3.0,
        evidence="실측 사람 0.17 vs AI 1.49 (약 9배, 전 모델)",
    ),
    Pattern(
        "D-9a", "D", "인과 결산 '~로 이어진다'",
        re.compile(r"((으)?로\s*이어진다|에\s*직결된다|(으)?로\s*귀결된다)"),
        severity=3, weight=2.2, risk="moderate", repl=None,
        hint="인과의 실제 경로를 쓰거나 단문 단언으로 끊으세요. 문서당 1회 이하.",
        per_1k_cap=2.0,
        evidence="실측 사람 0.00 vs AI 0.34 — 사람 60편에서 0건",
    ),
    Pattern(
        "D-9b", "D", "논리 결산 부사 '결국'",
        re.compile(r"(?<![가-힣])결국(?![가-힣])"),
        severity=2, weight=1.3, risk="moderate", repl=None, min_count=2,
        hint="사람의 '결국'은 서사 귀결에만 씁니다. 논리 결산 마커로 반복하지 마세요.",
        per_1k_cap=4.0,
        evidence="실측 사람 0.34 vs AI 1.72~1.83 (논리 결산 용법은 사람 0건)",
    ),
    Pattern(
        "D-10", "D", "역방향 결산 '~하는 이유다'",
        re.compile(r"[가-힣]{2,}(는|은)\s*이유다[.\s]|[가-힣]{2,}\s*이유다\s*[.。]"),
        severity=3, weight=2.0, risk="moderate", repl=None,
        hint="도치를 해제해 순방향 단언으로. '그래서 ~다'. 문서당 1회 이하.",
        per_1k_cap=2.0,
        evidence="실측 사람 0.09 vs AI 0.46 · 7건 중 6건이 문단·문서 말미",
    ),
    Pattern(
        "D-11", "D", "결말부 막연한 시간지평",
        re.compile(r"(?<![가-힣])(향후|앞으로|중장기적으로|장기적으로)[는,\s]"),
        severity=3, weight=2.0, risk="moderate", repl=None,
        context=_final_and_sentence_start,
        hint="시간어를 지우거나 실제 시점·조건으로 바꾸세요. 없는 시점을 지어내지 마세요.",
        per_1k_cap=2.0,
        evidence="'문두 + 후반 30%' 조건에서 사람 0건 vs AI 12건/12편",
    ),
    Pattern(
        "D-12", "D", "내용 없는 반론 슬롯",
        re.compile(r"(?:^|(?<=[.!?]\s))[^.!?\n]{0,12}(과제도\s*남아\s*있|한계도\s*분명하|아쉬운\s*점도\s*있)[^.!?\n]{0,6}[.]"),
        severity=3, weight=2.1, risk="moderate", repl=None,
        hint="균형 문패를 지우고 실제 과제를 첫 문장에 바로 쓰세요.",
        per_1k_cap=2.0,
        evidence="독립문 조건에서 사람 0건 vs AI 8건/8편",
    ),
    Pattern(
        "D-13", "D", "에세이 성찰 부사 공식",
        re.compile(r"(?<![가-힣])(어쩌면|비로소|천천히)(?![가-힣])"),
        severity=1, weight=0.8, risk="moderate", repl=None, min_count=2,
        hint="결말 성찰 부사를 빼고 구체 서술로. 에세이·수필 장르 한정입니다.",
        per_1k_cap=3.0,
        evidence="에세이 한정 AI 9건 vs 사람 0건 (장르 밖 오탐 주의)",
    ),
    Pattern(
        "D-14a", "D", "감각 술어 평가문",
        re.compile(
            r"(?<![가-힣])(진단|경고|분석|통계|현실|숫자|결론|메시지|시선|질문)"
            r"(은|는|이|가)\s*(서늘하|아프|차갑|뜨겁|묵직하|섬뜩하)"
        ),
        severity=3, weight=2.2, risk="moderate", repl=None,
        hint="관용구·구체 서술로. '진단은 서늘하다' → '진단은 정곡을 찌른다'.",
        per_1k_cap=2.0,
        evidence="사람 코퍼스 0건 — 1회부터 교정 대상",
    ),
    Pattern(
        "D-14b", "D", "생성형 은유 (사람 0건 사전)",
        re.compile(r"(잠식|청사진|적신호|경고등|신호탄|움켜쥐|뿌리내리|짓누르)"),
        severity=2, weight=1.2, risk="moderate", repl=None, min_count=2,
        hint="명제로 직역하세요. '시장을 잠식한다' → '시장 점유율을 뺏는다'.",
        per_1k_cap=3.0,
        evidence="⚠ 사람 532편 0건이나 그 코퍼스는 칼럼11+위키521. "
                 "신문 경제면에서는 표준 상용어 — 2회부터 셈",
    ),
    Pattern(
        "D-14c", "D", "생성형 은유 (사람도 쓰는 사전)",
        re.compile(r"(청구서|과실|주춧돌|씨앗|문턱|성적표|짊어지|어깨에|양날의\s*검)"),
        severity=1, weight=0.9, risk="moderate", repl=None, min_count=3,
        hint="효과적인 은유 1개만 남기고 나머지는 평서 서술로.",
        per_1k_cap=4.0,
        evidence="사람 532편 중 12건 실사용 — 3회 이상일 때만 신호",
    ),
    Pattern(
        "D-50", "D", "'급변하는 현대사회' 서두",
        # 뒤에 조사가 붙으면(시대**의** 도래는) 지울 수 없다 — 문장이 깨진다.
        re.compile(r"(급변하는\s*)?(현대\s*사회에서|오늘날\s*우리는|4차\s*산업혁명\s*시대)(?![가-힣])[,\s]*"),
        severity=3, weight=1.9, risk="aggressive", repl="",
        context=_at_sentence_start,
        hint="AI가 가장 즐겨 쓰는 도입부입니다. 통째로 지우고 본론에서 시작하세요.",
        per_1k_cap=2.0,
    ),

    # ======================= F. 수식·중복 =======================
    Pattern(
        "F-1", "F", "정도부사 중독",
        re.compile(r"(?<![가-힣])(매우|정말|굉장히|상당히|대단히|무척|아주|참으로|극히|진짜로)\s+"),
        severity=1, weight=0.7, risk="aggressive", repl="", min_count=2,
        hint="강조 부사는 문장을 약하게 만듭니다. 동사를 강한 것으로 바꾸세요.",
        per_1k_cap=6.0,
    ),
    Pattern(
        "F-3", "F", "기능+역할 복합구",
        re.compile(r"(중요한\s*역할을\s*(한다|합니다|하고|하며)|핵심적인\s*역할|중추적\s*역할|기능을\s*수행)"),
        severity=2, weight=1.4, risk="moderate", repl=None,
        hint="어떤 역할인지 구체적으로 쓰세요.",
        per_1k_cap=3.0,
    ),
    Pattern(
        "F-5", "F", "'~적 N' 복합 추상어 체인",
        re.compile(r"[가-힣]{1,5}적(인)?\s+[가-힣]{1,5}적(인)?\s"),
        severity=2, weight=1.2, risk="moderate", repl=None,
        hint="'사회적 구조적 문제' → '사회 구조의 문제'. -적을 겹쳐 쓰지 마세요.",
        per_1k_cap=4.0,
    ),
    Pattern(
        "F-7", "F", "범용 정책동사 수렴",
        re.compile(r"(?<![가-힣])(확대|강화|개선|확보|마련|집중|유지|구축|지원)"
                   r"(해야|하고|하며|가\s*필요|가\s*요구)"),
        severity=1, weight=0.8, risk="moderate", repl=None, min_count=3,
        hint="'강화해야 한다'는 아무것도 말하지 않습니다. 무엇을 어떻게인지 쓰세요.",
        per_1k_cap=5.0,
    ),

    # ======================= G. hedging =======================
    Pattern(
        "G-1", "G", "추측·관측형 종결",
        re.compile(r"것으로\s*(보인다|나타났다|확인되었다|조사되었다|분석되었다|판단된다|예상된다|전망된다)"),
        severity=2, weight=1.1, risk="moderate", repl=None, min_count=2,
        hint="주체를 밝혀 능동으로 쓰세요.",
        per_1k_cap=4.0,
    ),
    Pattern(
        "G-2", "G", "다중 완곡 ('~할 수 있을 것으로 보인다')",
        re.compile(r"([가-힣]{2,8}(?:할|일|될|갈|올))\s*수\s*있을\s*것으로\s*(?:보인다|판단된다|예상된다|전망된다)"),
        severity=3, weight=2.0, risk="moderate", repl=_fix_hedge_stack,
        hint="완곡을 두 겹 이상 쌓지 마세요. 하나면 충분합니다.",
        per_1k_cap=3.0,
    ),
    Pattern(
        "G-2b", "G", "'사료된다/여겨진다'",
        re.compile(r"(사료된다|사료됩니다|여겨진다|여겨집니다)"),
        severity=2, weight=1.2, risk="moderate", repl=_fix_saryodoenda,
        hint="'사료된다'는 관공서체입니다. 다만 '여겨지다'는 정상 피동이라 "
             "문맥에 따라 그대로 둬도 됩니다.",
    ),
    Pattern(
        "G-3", "G", "안전 균형 lexicon",
        re.compile(r"(양쪽\s*모두|두\s*가지\s*모두|장점도\s*있지만|단점도\s*있지만|신중한\s*접근|균형\s*잡힌|균형\s*있는)"),
        severity=1, weight=0.5, risk="moderate", repl=None, min_count=4,
        hint="입장을 정하세요. 양비론 안전장치는 AI 시그니처입니다.",
        per_1k_cap=3.0,
        evidence="⚠ 근거 불충분(hold) — 사람 60편 1건 vs AI 60편 4건, 밀도 비교 불성립",
    ),

    # ======================= H. 접속사 =======================
    Pattern(
        "H-1", "H", "문두 접속사 과다",
        re.compile(r"(?m)^\s*(또한|따라서|하지만|그러나|특히|즉|그리고|한편|더불어|아울러|무엇보다|그러므로)[,\s]"),
        severity=2, weight=1.2, risk="moderate", repl=None, min_count=2,
        hint="문두 접속부사를 절반 이상 지워도 논리는 유지됩니다.",
        per_1k_cap=5.0,
    ),
    Pattern(
        "H-2", "H", "'하지만'·'그러나' 혼용 남발",
        re.compile(r"(?<![가-힣])(하지만|그러나)[,\s]"),
        severity=1, weight=0.6, risk="moderate", repl=None, min_count=4,
        hint="역접을 한 문서에서 네 번 넘게 쓰면 논지가 흔들립니다.",
        per_1k_cap=6.0,
    ),
    Pattern(
        "H-3", "H", "'이는 ~' 지시 반복",
        re.compile(r"(?:^|(?<=[.!?]\s))이는\s"),
        severity=2, weight=1.1, risk="moderate", repl=None, min_count=2,
        hint="'이는'으로 문장을 잇는 습관은 AI 특유입니다. 주어를 명시하세요.",
        per_1k_cap=4.0,
    ),
    Pattern(
        "H-4", "H", "재정의 접속사 '즉' 남발",
        re.compile(r"(?<![가-힣])즉[,\s]"),
        severity=1, weight=0.8, risk="moderate", repl=None, min_count=2,
        hint="'즉'으로 재정의를 반복하면 첫 서술이 부실하다는 뜻입니다.",
        per_1k_cap=4.0,
    ),

    # ======================= I. 형식명사 =======================
    Pattern(
        "I-1", "I", "'것이다' 종결 남발",
        re.compile(r"것이다[.\s]|것입니다[.\s]"),
        severity=1, weight=0.2, risk="moderate", repl=None, min_count=5,
        hint="'~것이다'를 걷어내면 문장이 단단해집니다.",
        per_1k_cap=6.0,
        evidence="⚠ 실측 역전 — AI 20.4 vs 인간 43.0. 논설문의 일반 종결",
    ),
    Pattern(
        "I-3", "I", "'~라는 것'",
        re.compile(r"(라는|다는)\s*(것|점|사실)(은|이|을|입니다|이다)"),
        severity=1, weight=0.8, risk="moderate", repl=None, min_count=2,
        hint="'~라는 것은' → '~은'. 형식명사를 줄이세요.",
        per_1k_cap=5.0,
    ),
    Pattern(
        "I-4", "I", "'~할 필요가 있다' 권고형",
        re.compile(r"[가-힣]{2,}할\s*필요가\s*있(다|습니다)"),
        severity=2, weight=1.3, risk="moderate", repl=None,
        hint="'검토할 필요가 있다' → '검토해야 한다' 또는 '검토하자'.",
        per_1k_cap=4.0,
    ),
    Pattern(
        "I-5", "I", "'~이 필요하다' 당위 반복",
        re.compile(r"[가-힣]{2,}(이|가)\s*필요하(다|다\.|며|고|습니다)"),
        severity=1, weight=0.9, risk="moderate", repl=None, min_count=2,
        hint="당위 서술이 쌓이면 내용이 비어 보입니다. 누가 무엇을 하는지 쓰세요.",
        per_1k_cap=5.0,
    ),
    Pattern(
        "I-7", "I", "무주체 판정 '~다는 분석이다'",
        re.compile(r"(다는|라는)\s*(분석|평가|해석|관측|지적|전망)(이다|입니다)"),
        severity=2, weight=1.4, risk="moderate", repl=None,
        hint="누가 그렇게 분석했는지 밝히세요.",
        per_1k_cap=3.0,
    ),

    # ======================= J. 시각 장식 =======================
    Pattern(
        "J-2", "J", "따옴표 과다",
        re.compile(r"['‘’][^'‘’\n]{2,20}['‘’]"),
        severity=1, weight=0.5, risk="moderate", repl=None, min_count=4,
        hint="작은따옴표 강조를 남발하지 마세요.",
        per_1k_cap=6.0,
    ),
    Pattern(
        "J-3", "J", "대시(—) 남용",
        re.compile(r"\s—\s"),
        severity=1, weight=0.6, risk="moderate", repl=None, min_count=3,
        hint="대시 삽입절을 줄이고 문장을 나누세요.",
        per_1k_cap=5.0,
    ),
    Pattern(
        "J-4", "J", "괄호 부연 과다",
        re.compile(r"\([^)\n]{6,60}\)"),
        severity=1, weight=0.5, risk="moderate", repl=None, min_count=4,
        hint="괄호 부연이 잦으면 본문 구조가 약하다는 뜻입니다.",
        per_1k_cap=6.0,
    ),
]

PATTERNS_BY_ID = {p.id: p for p in PATTERNS}


# ---------------------------------------------------------------------------
# 역방향 지표 — 사람 글의 증거
# ---------------------------------------------------------------------------
#
# 지금까지의 패턴은 전부 "AI라는 증거"만 모은다. 그래서 격식체 산문이
# 구조적으로 불리했다(학술 논문 98.6점). 반대 방향 증거를 세서 점수를 깎는다.
#
# 여기 있는 항목들은 원 분류 체계 실측에서 **AI 코퍼스 0건 또는 사람 우세**로
# 관측된 것들이다. 오탐을 줄이는 가장 값싼 장치다.

@dataclass(frozen=True)
class HumanSignal:
    id: str
    name: str
    regex: re.Pattern
    weight: float
    evidence: str = ""


HUMAN_SIGNALS: list[HumanSignal] = [
    HumanSignal(
        "HS-1", "화자 자기 개입",
        re.compile(
            r"(솔직히|사실\s*나는|내\s*생각(엔|에는)|내가\s*보기(엔|에는)"
            r"|잘\s*모르겠|모르겠지만|개인적으로는|고백하자면)"
        ),
        weight=1.4,
        evidence="사람 13건/11편 vs AI 99편 0건",
    ),
    HumanSignal(
        "HS-2", "시점 앵커",
        re.compile(
            r"(?<![가-힣])(당시|그때|그해|작년|재작년|지난해|지난달|엊그제|어제|올해\s*초)"
            r"(?![가-힣])"
        ),
        weight=1.1,
        evidence="'당시' 사람 10건/9편 vs AI 0건",
    ),
    HumanSignal(
        "HS-3", "고충·정서 어휘",
        re.compile(r"(힘들[었다어겠]|어렵더|막막|짜증|귀찮|버겁|서럽|억울)"),
        weight=1.0,
        evidence="'힘들다' 사람 5건 vs AI 0건",
    ),
    HumanSignal(
        "HS-4", "문두 '또,' (사람 전용)",
        re.compile(r"(?:^|(?<=[.!?]\s))또,\s"),
        weight=1.2,
        evidence="사람 전용 — AI는 '또한'만 씀",
    ),
    HumanSignal(
        "HS-5", "수혜 보조동사 '~해 주다'",
        re.compile(r"[가-힣]+\s*(줬|줍니다|주었|주는|준다|줘야|주면)(?![가-힣])"),
        weight=0.8,
        evidence="사람 우세",
    ),
    HumanSignal(
        "HS-6", "구어체 축약",
        re.compile(r"(?<![가-힣])(근데|그냥|되게|엄청|진짜|괜히|막상|하도|딱히)(?![가-힣])"),
        weight=0.9,
    ),
    HumanSignal(
        "HS-7", "1인칭 서술",
        re.compile(r"(?<![가-힣])(나는|내가|나도|제가|저는|우리\s*집|우리\s*애)(?![가-힣])"),
        weight=0.7,
    ),
]

HUMAN_SIGNALS_BY_ID = {h.id: h for h in HUMAN_SIGNALS}


def find_human_hits(text: str) -> dict[str, int]:
    """역방향 지표별 발생 횟수."""
    return {
        h.id: n for h in HUMAN_SIGNALS
        if (n := len(h.regex.findall(text)))
    }


# ---------------------------------------------------------------------------
# 탐지
# ---------------------------------------------------------------------------

@dataclass
class Hit:
    pattern_id: str
    category: str
    name: str
    severity: int
    start: int
    end: int
    text: str
    hint: str = ""


def find_hits(
    text: str,
    pattern_ids: list[str] | None = None,
    apply_min_count: bool = True,
) -> list[Hit]:
    """텍스트 전체에서 패턴 히트를 찾아 위치 순으로 반환한다.

    `apply_min_count=True`이면 문서 내 발생 횟수가 `min_count` 미만인 패턴은
    통째로 버린다 — 사람도 한두 번은 쓰는 표현을 1회로 잡으면 오탐이 난다.
    """
    pool = PATTERNS if pattern_ids is None else [
        PATTERNS_BY_ID[i] for i in pattern_ids if i in PATTERNS_BY_ID
    ]
    hits: list[Hit] = []
    for p in pool:
        found = []
        for m in p.regex.finditer(text):
            if p.context is not None and not p.context(text, m):
                continue
            found.append(Hit(
                pattern_id=p.id, category=p.category, name=p.name,
                severity=p.severity, start=m.start(), end=m.end(),
                text=m.group(0).strip(), hint=p.hint,
            ))
        if apply_min_count and len(found) < p.min_count:
            continue
        hits.extend(found)
    hits.sort(key=lambda h: (h.start, h.end))
    return hits


# ---------------------------------------------------------------------------
# 다듬기 적용
# ---------------------------------------------------------------------------

@dataclass
class Change:
    pattern_id: str
    name: str
    before: str
    after: str
    count: int


def apply_rewrites(text: str, max_risk: str = "moderate") -> tuple[str, list[Change]]:
    """risk 등급이 max_risk 이하인 규칙만 순차 적용한다.

    `min_count`가 걸린 규칙은 원문에서 그 횟수만큼 나올 때만 적용한다
    (탐지와 같은 기준을 쓴다). `context` 조건도 그대로 존중한다.

    반환: (수정된 텍스트, 변경 내역)
    """
    limit = RISK_ORDER.get(max_risk, 1)
    changes: list[Change] = []
    out = text
    for p in PATTERNS:
        if not p.rewritable or RISK_ORDER.get(p.risk, 1) > limit:
            continue
        if p.min_count > 1:
            n = sum(
                1 for m in p.regex.finditer(out)
                if p.context is None or p.context(out, m)
            )
            if n < p.min_count:
                continue
        samples: list[tuple[str, str]] = []

        def _sub(m: re.Match, _p=p, _s=samples, _src=out) -> str:
            if _p.context is not None and not _p.context(_src, m):
                return m.group(0)
            try:
                rep = _p.repl(m) if callable(_p.repl) else _p.repl
            except Exception:
                return m.group(0)
            if rep is None:
                return m.group(0)
            if rep != m.group(0):
                _s.append((m.group(0), rep))
            return rep

        new = p.regex.sub(_sub, out)
        if samples:
            changes.append(Change(
                pattern_id=p.id, name=p.name,
                before=samples[0][0], after=samples[0][1], count=len(samples),
            ))
            out = new
    return out, changes
