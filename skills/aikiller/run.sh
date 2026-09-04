#!/usr/bin/env bash
# aikiller CLI 실행기 — 설치 방식과 무관하게 저장소를 찾아 실행한다.
#
#   전역 설치(install.sh)  -> PATH 의 aikiller
#   플러그인 설치          -> $CLAUDE_PLUGIN_ROOT
#   저장소 클론 후 스킬만  -> 이 스크립트 기준 상위 디렉터리
#
# 사용:  run.sh detect 파일.txt --json
set -euo pipefail

if command -v aikiller >/dev/null 2>&1; then
    exec aikiller "$@"
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
for root in "${CLAUDE_PLUGIN_ROOT:-}" "$here/../.." "$here/../../.."; do
    [[ -n "$root" && -f "$root/aikiller/__main__.py" ]] || continue
    export PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}"
    exec "${PYTHON:-python3}" -m aikiller "$@"
done

echo "aikiller 저장소를 찾지 못했습니다." >&2
echo "  https://github.com/bokuyong/aikiller 클론 후 ./install.sh 를 실행하세요." >&2
exit 127
