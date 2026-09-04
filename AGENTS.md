# AGENTS.md — 이 저장소에서 작업하는 에이전트를 위한 지침

한국어 AI 문체 탐지 + 다듬기 도구. 탐지기와 다듬기가 **하나의 패턴 레지스트리**를
공유하는 것이 이 프로젝트의 핵심 설계다.

## 절대 규칙

1. **의존성을 추가하지 마라.** 표준 라이브러리만 쓴다. 예외는 `requirements.txt`에
   적힌 두 개(`olefile`, `pypdf`)뿐이고 둘 다 선택적이다 — 없으면 해당 파일 형식만
   안 되고 나머지는 다 돌아야 한다. numpy·pandas·scikit-learn·konlpy·mecab 금지.
   로지스틱 회귀도 `scripts/calibrate.py`에 직접 구현돼 있다.
2. **캘리브레이션 상태를 속이지 마라.** `fusion_calibrated` 플래그와 "실측/추정"
   구분은 이 도구의 신뢰도 그 자체다. 실측이 아닌 값을 실측처럼 표시하는 변경은
   기능 추가가 아니라 결함이다.
3. **오탐이 최고 비용 오류다.** 이 도구는 사람이 쓴 글을 AI로 잘못 지목할 수 있고,
   그 대상은 학생·구직자다. 정탐률을 올리려고 오탐률을 올리는 트레이드오프는
   기본적으로 거절한다. 새 패턴은 `min_count`·`context` 가드를 먼저 검토하라.
4. **다듬기는 의미를 바꾸지 않는다.** 사실·수치·고유명사·직접 인용은 100% 보존.
   없던 주장을 만들거나 있던 주장을 지우는 규칙은 넣지 않는다.
5. **작업 후 반드시 테스트를 돌린다.**

```bash
python3 -m unittest discover tests -v
```

## 구조

```
aikiller/
  patterns.py   ★ 패턴 레지스트리 (SSOT). 여기 한 줄 추가하면 탐지·다듬기·
                  리포트·LLM 프롬프트·웹 API에 동시 반영된다.
  detect.py     4계층 융합 (L1 실측지표 / L2 패턴밀도 / L3 리듬 / L4 사람증거)
  humanize.py   규칙 다듬기 + LLM 프롬프트 빌더
  hangul.py     종성 판별 · 조사 자동 선택 (은/는, 이/가, 을/를, 로/으로)
  parsers.py    hwp(바이너리) / hwpx / docx / pdf / txt
  cli.py        detect · humanize · prompt · serve · clip · history
  web.py        웹 서버 + 도구 화면(/app) + JSON API
  landing.py    랜딩 페이지(/) HTML — 여기 적힌 숫자는 전부 실측값이다.
                바꿀 때는 실제로 다시 재고 바꿔라. 마케팅 문구 금지.
  history.py    로컬 분석 기록 (SQLite, ~/.aikiller/)
  metrics.py    쉼표 계열(L1)·리듬(L3) 정량 지표
  baselines.py  사람/AI 실측 극값. 장르별로 판별력 없는 셀은 None 으로 비운다 —
                그 None 이 격식체 오탐을 막는 장치다. 함부로 채우지 마라.
scripts/
  corpus.py     코퍼스 구축 (import · wiki · generate · adversarial · stats)
  calibrate.py  융합 가중치 실측 피팅
  eval.py       TPR@FPR 평가
```

## 패턴을 추가할 때

```python
Pattern(
    "A-30", "A", "패턴 이름",
    re.compile(r"정규식"),
    severity=2,            # 1(경미) ~ 3(심각)
    weight=1.2,            # 탐지 기여도. evidence 강도에 비례해야 한다
    risk="moderate",       # safe | moderate | aggressive
    repl=None,             # 문자열 / callable / None(탐지 전용)
    hint="사람이 읽는 수정 지침",
    min_count=2,           # N회 이상일 때만 신호 — 오탐 방지의 1차 장치
    context=None,          # (text, match) -> bool. 위치·문맥 조건
    evidence="사람 0.1 vs AI 0.9",
),
```

- `risk` 등급의 의미를 지켜라. `safe`는 **문법적으로 의미 불변이 보장되는 것만**이다.
  판단이 서지 않으면 `moderate`가 아니라 `repl=None`(탐지 전용)으로 둬라.
- `weight`는 `evidence`와 모순되면 안 된다. 사람 코퍼스 0건 패턴은 무겁게,
  1.3배 수준 패턴은 가볍게. (`D-4` hype 어휘가 후자의 예다 — 근거가 약해서
  weight 0.4로 눌러 놨다. 올리지 마라.)
- 새 패턴에는 `tests/test_core.py` 회귀 테스트를 같이 넣는다. 특히 **오탐 테스트**
  (사람이 쓸 법한 문장에서 발화하지 않는지)를 꼭 넣어라.

## 다듬기 규칙을 만질 때

`apply_rewrites()`는 `PATTERNS` 리스트 **순서대로** 전체 텍스트에 순차 적용한다.
앞 규칙의 출력이 뒤 규칙의 입력이 되므로 상호작용을 확인해야 한다.

보호 구간(코드블록·인라인코드·URL·직접인용·인용블록)은 `humanize.py`가 마스킹으로
처리한다. 새 보호 대상이 필요하면 `_PROTECT_PATTERNS`에 추가한다.

한국어 조사·경어법을 건드리는 치환은 `hangul.py` 헬퍼를 써라. 직접 문자열을
붙이면 "요소이", "문제이습니다" 같은 비문이 나온다 — 실제로 났던 버그다.

## 하지 말아야 할 것

- `baselines.py` 의 `None` 셀을 근거 없이 채우기 (그 장르에서 지표가 뒤집힌다는 실측 결과다)
- `data/fusion_weights.json`을 손으로 쓰기 (`calibrate.py`만 쓴다)
- 오탐 경고·면책 문구 삭제 (README, 랜딩 "못 하는 것" 절, 웹 UI 상단 배너, `notes` 배열)
- 랜딩 페이지에 측정하지 않은 성능 수치 쓰기
- `history` 모듈을 켠 채로 남의 글을 받는 서비스로 배포하기
- accuracy를 성능 지표로 보고하기 (`TPR @ FPR=1%`를 쓴다)

## 현재 알려진 결함

`README.md`의 "지금 상태에서 믿을 수 있는 것 / 없는 것" 절이 최신이다. 요약:

- 융합 가중치 미피팅. 등급 경계(25/60)도 표본 9건에 맞춘 잠정값
- L3 임계값은 휴리스틱이다. `calibrate.py` 가 사람 코퍼스로 재측정한다
- 다듬은 뒤 L3 리듬이 오히려 악화 (규칙 다듬기의 구조적 한계)
- `evidence` 필드가 없는 패턴 다수 — 가중치가 추정치다
- `scripts/eval.py`가 in-sample이다. 가중치·임계값·평가를 같은 데이터로 하고
  홀드아웃 분할이 없다. 코퍼스가 생기면 이걸 먼저 고쳐야 한다.

## 검수 이력

2026-08 에 4개 축(정규식 정확성 · 탐지 방법론 · 보안 · 한국어 언어학)으로
검수했다. 고친 것은 `README.md`의 "검수에서 고친 것" 절에 있고, 전부
`tests/test_core.py::TestReviewRegressions` 로 고정돼 있다.

**그때 배운 것 — 같은 실수를 반복하지 마라:**

- 하드코딩된 지표 극값을 실측으로 표시하지 마라. `lexical_diversity` 가
  0.65/0.55 로 박혀 있었는데 실제 한국어는 0.79~0.94 였고, 부호까지 반대여서
  사람 글 점수를 통째로 올리고 있었다.
- 원 분류 체계의 **대조군**을 신호로 구현하지 마라. `A-20` 이 정확히
  그랬다(격차 없는 능동 진행을 잡고 진짜 신호인 피동 진행을 놓침).
- 정규식에 **어두 경계**를 빼먹지 마라. `로의`·`고,`·`으로` 전부 여기서 터졌다.
- 고정 문자열 치환은 경어법을 깬다. 항상 callable 로 분기하라.

## 다음 우선순위

1. **코퍼스 구축 → 캘리브레이션.** 나머지 전부보다 중요하다.
   `scripts/corpus.py` → `scripts/calibrate.py` → `scripts/eval.py` 순서.
2. 장르별 임계값 분리 (격식체 오탐 해결)
3. LLM 다듬기 경로 실행부 (지금은 프롬프트 생성까지만 있다)
