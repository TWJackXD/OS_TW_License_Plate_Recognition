#!/usr/bin/env bash
# Install permit module (+ campus / ticket UI).
# No npm required — UI is Jinja + static JS served by python run.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OVERLAY="$ROOT/permit-module/overlay"

die() { echo "ERROR: $*" >&2; exit 1; }

# Prefer opensource/ (local layout); else install into repo root (OS_TW layout).
if [[ -f "$ROOT/opensource/run.py" ]]; then
  TARGET="$ROOT/opensource"
  START_HINT="cd opensource && python run.py"
elif [[ -f "$ROOT/run.py" ]]; then
  TARGET="$ROOT"
  START_HINT="python run.py"
else
  die "找不到可安裝的核心（缺少 opensource/run.py 或 ./run.py）"
fi

[[ -d "$OVERLAY" ]] || die "找不到 overlay：$OVERLAY"
[[ -f "$TARGET/run.py" ]] || die "目標不像核心（缺少 run.py）：$TARGET"

echo "==> 複製模組與核心覆蓋檔到：$TARGET"
if command -v rsync >/dev/null 2>&1; then
  rsync -a "$OVERLAY/" "$TARGET/"
else
  (cd "$OVERLAY" && tar cf - .) | (cd "$TARGET" && tar xf -)
fi

ENV_FILE="$TARGET/.env"
EXAMPLE="$TARGET/.env.example"
ensure_env_flag() {
  local file="$1"
  if grep -qE '^[[:space:]]*ENABLE_PERMIT_MODULE=' "$file"; then
    sed -i.bak -E 's/^[[:space:]]*ENABLE_PERMIT_MODULE=.*/ENABLE_PERMIT_MODULE=1/' "$file"
    rm -f "$file.bak"
  else
    printf '\n# 可選車證／罰單模組\nENABLE_PERMIT_MODULE=1\n' >>"$file"
  fi
}

if [[ -f "$ENV_FILE" ]]; then
  ensure_env_flag "$ENV_FILE"
  echo "==> 已設定 .env：ENABLE_PERMIT_MODULE=1"
elif [[ -f "$EXAMPLE" ]]; then
  cp "$EXAMPLE" "$ENV_FILE"
  ensure_env_flag "$ENV_FILE"
  echo "==> 已從 .env.example 建立 .env（請填入 API Key）"
fi

cat <<EOF

完成。只需啟動：

  $START_HINT

  http://127.0.0.1:8010/               回報
  http://127.0.0.1:8010/admin          歷史
  http://127.0.0.1:8010/permit/lookup  車證／罰單

無需 npm。
EOF
