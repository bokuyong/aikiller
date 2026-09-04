---
description: 한국어 글의 AI 문체를 검사하고 다듬는다 (검사만 하려면 --detect)
argument-hint: [파일경로 또는 붙여넣은 글] [--detect] [--level safe|moderate|aggressive]
---

`aikiller` 스킬로 아래 입력을 처리하세요.

`skills/aikiller/SKILL.md` 의 절차를 따릅니다:

1. 장르를 추정하고 `run.sh detect ... --json` 으로 검사합니다.
   보고서·논문·공문이면 `--genre report`, 칼럼·기사면 `--genre column` 을
   반드시 씁니다. 장르를 잘못 고르면 격식체 오탐이 납니다.
2. `--detect` 가 붙었거나 사용자가 검사만 원하면 **여기서 멈추고** 점수·근거·
   문장별 히트맵을 보고합니다.
3. 수정을 원하면 `run.sh humanize --level <강도> --json` 으로 규칙 다듬기를
   먼저 적용합니다. 강도 지정이 없으면 `moderate`.
4. `run.sh prompt` 가 지적한 구간(무생물 주어·문단 리듬·문두 접속사)만
   직접 손봅니다. 사실·수치·인용·경어법은 100% 보존합니다.
5. 다시 `detect` 로 검증합니다. 점수가 올랐으면 4단계를 되돌립니다.

`fusion_calibrated: false` 면 "점수는 상대 비교용"이라고 밝히고,
`confidence: insufficient` 면 점수를 말하지 않습니다.

입력:

$ARGUMENTS
