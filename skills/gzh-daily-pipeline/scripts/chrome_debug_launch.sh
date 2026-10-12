#!/usr/bin/env bash
#
# chrome_debug_launch.sh — 带调试端口启动 Chrome（供 wechatsync 同步用）
#
# 用 --user-data-dir 指向克隆出的非默认调试 profile（/Users/haolin/chrome-debug-profile），
# 并打开 --remote-debugging-port=9222，供 wake_sw_v2.py / sync_with_keepalive.py
# 通过 CDP 唤醒 wechatsync 扩展的 Service Worker 并推送草稿。
#
# 注意：wechatsync 公众号适配器本身不支持自动设置封面（上游设计限制，非配置或补丁可解），
# 草稿封面需在公众号编辑器手动点「封面 → 上传封面」。本脚本不做任何封面补丁。
#
# 用法: chrome_debug_launch.sh
set -u

PROFILE="/Users/haolin/chrome-debug-profile"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 1) 等旧实例退出(最多 20s)
for _ in $(seq 1 20); do
  pgrep -f "user-data-dir=${PROFILE}" >/dev/null 2>&1 || break
  sleep 1
done
if pgrep -f "user-data-dir=${PROFILE}" >/dev/null 2>&1; then
  pkill -f "user-data-dir=${PROFILE}" 2>/dev/null
  sleep 2
fi

# 2) 启动 Chrome
exec "$CHROME" \
  --remote-debugging-port=9222 \
  --user-data-dir="${PROFILE}" \
  --no-first-run
