#!/usr/bin/env bash
# Install Niimbot B1 instant-print module (Web Bluetooth; no npm).
# Works from project root or INSTALL_NIIMBOT/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -d "$SCRIPT_DIR/niimbot-module/overlay" ]]; then
  ROOT="$SCRIPT_DIR"
elif [[ -d "$SCRIPT_DIR/../niimbot-module/overlay" ]]; then
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  echo "ERROR: 找不到 niimbot-module/overlay（請在專案根目錄或 INSTALL_NIIMBOT/ 執行）" >&2
  exit 1
fi

OVERLAY="$ROOT/niimbot-module/overlay"

die() { echo "ERROR: $*" >&2; exit 1; }

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

echo "==> 複製 Niimbot 模組覆蓋檔到：$TARGET"
if command -v rsync >/dev/null 2>&1; then
  rsync -a "$OVERLAY/" "$TARGET/"
else
  (cd "$OVERLAY" && tar cf - .) | (cd "$TARGET" && tar xf -)
fi

ENV_FILE="$TARGET/.env"
EXAMPLE="$TARGET/.env.example"
ensure_env_flag() {
  local file="$1"
  if grep -qE '^[[:space:]]*ENABLE_NIIMBOT_MODULE=' "$file"; then
    sed -i.bak -E 's/^[[:space:]]*ENABLE_NIIMBOT_MODULE=.*/ENABLE_NIIMBOT_MODULE=1/' "$file"
    rm -f "$file.bak"
  else
    printf '\n# 可選 Niimbot B1 即時列印（Web Bluetooth）\nENABLE_NIIMBOT_MODULE=1\n' >>"$file"
  fi
}

if [[ -f "$ENV_FILE" ]]; then
  ensure_env_flag "$ENV_FILE"
  echo "==> 已設定 .env：ENABLE_NIIMBOT_MODULE=1"
elif [[ -f "$EXAMPLE" ]]; then
  cp "$EXAMPLE" "$ENV_FILE"
  ensure_env_flag "$ENV_FILE"
  echo "==> 已從 .env.example 建立 .env（請填入 API Key）"
fi

cat <<EOF

完成。只需啟動：

  $START_HINT

  使用 Chrome／Edge（需 HTTPS 或本機 localhost）開啟回報頁，
  先按「連接印表機」配對 Niimbot B1，送出違規後會即時列印 50×80mm 罰單。

無需 npm。
EOF
