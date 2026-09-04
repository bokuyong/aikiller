#!/usr/bin/env bash
# ai킬러 개인용 설치 — 어디서나 `aikiller` 로 실행되게 한다.
#
#   ./install.sh            설치
#   ./install.sh --uninstall 제거
#
# 하는 일은 하나뿐이다: ~/.local/bin/aikiller 라는 3줄짜리 실행 스크립트를
# 만들어 이 저장소를 가리키게 한다. 파이썬 패키지를 설치하지 않으므로
# 저장소를 수정하면 즉시 반영된다.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
TARGET="${BIN_DIR}/aikiller"
PY="${PYTHON:-python3}"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$TARGET"
    echo "제거했습니다: $TARGET"
    echo "기록은 그대로 있습니다: ~/.aikiller/history.db"
    echo "기록도 지우려면:  rm -rf ~/.aikiller"
    exit 0
fi

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "python3 을 찾을 수 없습니다. PYTHON=/경로/python3 ./install.sh 로 지정하세요." >&2
    exit 1
fi

ver=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "python: $PY ($ver)"

mkdir -p "$BIN_DIR"
cat > "$TARGET" <<EOF
#!/usr/bin/env bash
# ai킬러 런처 (install.sh 가 생성)
exec "$PY" -m aikiller "\$@"
EOF
chmod +x "$TARGET"

# 저장소를 PYTHONPATH 에 넣어 어느 디렉터리에서든 import 되게 한다.
cat > "$TARGET" <<EOF
#!/usr/bin/env bash
# ai킬러 런처 (install.sh 가 생성). 저장소: $REPO
export PYTHONPATH="$REPO\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PY" -m aikiller "\$@"
EOF
chmod +x "$TARGET"

echo "설치했습니다: $TARGET"

# 선택 의존성 안내 (없어도 핵심 기능은 다 돈다)
missing=()
"$PY" -c 'import olefile' 2>/dev/null || missing+=("olefile  (.hwp 바이너리)")
"$PY" -c 'import pypdf'   2>/dev/null || missing+=("pypdf    (.pdf)")
if ((${#missing[@]})); then
    echo
    echo "선택 의존성 (없어도 hwpx·docx·txt 는 됩니다):"
    for m in "${missing[@]}"; do echo "  - $m"; done
    echo "  설치:  $PY -m pip install olefile pypdf"
fi

case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *)
        echo
        echo "⚠ ${BIN_DIR} 이 PATH 에 없습니다. 셸 설정에 아래 한 줄을 추가하세요:"
        case "$(basename "${SHELL:-bash}")" in
            zsh)  echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc" ;;
            *)    echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc" ;;
        esac
        ;;
esac

cat <<'USAGE'

이제 어디서나:

  aikiller                     웹 UI (브라우저 자동으로 열림)
  aikiller detect 파일.hwp     터미널에서 탐지
  aikiller humanize 파일.txt --level aggressive --diff
  aikiller clip                클립보드 내용 바로 검사
  aikiller history             지난 분석 기록

USAGE
