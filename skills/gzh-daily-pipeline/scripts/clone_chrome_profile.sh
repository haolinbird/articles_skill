#!/usr/bin/env bash
# clone_chrome_profile.sh
# 把真实 Chrome profile 克隆到一个「非默认」目录, 用于开启远程调试端口(自动化同步草稿)。
#
# 背景: Chrome 安全策略禁止对「默认 profile」开远程调试端口 —— 即使显式传
#   --user-data-dir 指向真实默认目录, Chrome 仍会拒绝 (报
#   "DevTools remote debugging requires a non-default data directory") 且端口不开。
#   实测: 只有 user-data-dir != 默认路径时, --remote-debugging-port 才会真正监听。
#
# 做法: rsync 复制真实 profile, 但排除 18G 的 Service Worker 缓存 / 各类 Cache / 历史,
#   仅保留 扩展 + 登录态 (Cookies/Local Storage/Local Extension Settings), 约数百 MB。
#   扩展代码(含 Wechatsync)与登录态(含 Wechatsync MCP token)均在保留项内。
#
# 用法: 先完全退出 Chrome, 再 bash clone_chrome_profile.sh
set -euo pipefail

SRC="$HOME/Library/Application Support/Google/Chrome"
DST="$HOME/chrome-debug-profile"

# 前置: Chrome 必须完全退出, 否则复制出的文件可能不一致 / 锁冲突
if pgrep -f "Google Chrome" >/dev/null 2>&1; then
  echo "❌ 检测到 Chrome 正在运行, 请先完全退出(包括所有窗口), 否则复制出的登录态可能不一致。"
  echo "   终端执行:  pkill -f 'Google Chrome'"
  echo "   然后确认:  pgrep -fl 'Google Chrome'  无输出 再重跑本脚本"
  exit 1
fi

echo "==> 源: $SRC"
echo "==> 目标: $DST"
mkdir -p "$DST"

rsync -a --delete \
  --exclude='Service Worker/' \
  --exclude='Cache/' \
  --exclude='Code Cache/' \
  --exclude='GPUCache/' \
  --exclude='Session Storage/' \
  --exclude='Sessions/' \
  --exclude='History*' \
  --exclude='Top Sites' \
  --exclude='Thumbnails/' \
  --exclude='Media Cache/' \
  --exclude='.DS_Store' \
  "$SRC/" "$DST/"

echo "✅ 克隆完成"
du -sh "$DST"
echo
echo "⚠️ 首次用调试 profile 启动 Chrome 时, macOS 可能弹出 Keychain 授权(访问 'Chrome Safe Storage'),"
echo "   请点[允许]/[始终允许], 否则 Cookie 无法解密、登录态失效(需重跑本脚本或重新登录)。"
echo
echo "下一步: 启动调试 profile 并开端口 ——"
echo "  \"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome\" --remote-debugging-port=9222 --user-data-dir=\"$DST\" --no-first-run"
