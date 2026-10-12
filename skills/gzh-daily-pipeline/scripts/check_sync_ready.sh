#!/usr/bin/env bash
# ============================================================
# S6 同步连通性自检
#
# 什么时候跑 —— 三选一即可触发怀疑：
#   1) 电脑关过机 / 重启过，重新登录后
#   2) 隔了好几天没跑流水线
#   3) 流水线报告里 S6 显示同步失败、或「人工待办」里挂着未发布产物
#
# 用法：
#   bash skills/gzh-daily-pipeline/scripts/check_sync_ready.sh
#
# 性质：**纯只读体检**，不做任何破坏性操作（不会杀 Chrome、不会删文件）。
# 每一项失败都会打印对应的修复命令，照着复制执行即可。
# ============================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# scripts/ → skills/gzh-daily-pipeline/ → skills/ → 项目根
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PORT="9222"
EXT_ID="hchobocdmclopcbnibdnoafilagadion"
PLIST="$HOME/Library/LaunchAgents/com.haolin.chrome-debug.plist"

PASS=0
FAIL=0
ok()   { printf "  \033[32m[OK]\033[0m    %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31m[FAIL]\033[0m  %s\n" "$1"; FAIL=$((FAIL+1)); }
warn() { printf "  \033[33m[WARN]\033[0m  %s\n" "$1"; }
fix()  { printf "         → %s\n" "$1"; }

# ── 本机端口探测（务必走这两个函数，别直接用 curl）──
# ⚠️ 踩过的坑：本机配过 HTTP_PROXY（如 WorkBuddy 沙箱代理 http://127.0.0.1:50009）时，
#    curl 请求 127.0.0.1 会把请求交给代理。端口没服务时，代理返回一串错误文本
#    ("upstream connect failed: Connection refused")，而 **curl 退出码依然是 0** ——
#    于是「Chrome 根本没起来」会被误判成「链路正常」，S6 静默失败。
#    解法：--noproxy '*' 绕过代理 + 校验响应内容确实是 CDP 返回，两者缺一不可。
cdp_get() { curl -s --noproxy '*' -m 3 "$1" 2>/dev/null; }
cdp_ok()  { local r; r="$(cdp_get "$1")"; [ -n "$r" ] || return 1; case "$r" in *"$2"*) return 0;; *) return 1;; esac; }

echo ""
echo "════ S6 同步连通性自检 ════"
echo ""

# ---------- 1. launchd 是否注册（决定重启后能不能自动恢复）----------
echo "[1] Chrome 调试网关是否已注册到 launchd"
# ⚠️ 不要用 launchctl list | grep：实测 launchctl list 在部分上下文返回空列表，
#    会把「已注册」误判成「未注册」。精确查单个 label 才可靠。
if launchctl print "gui/$(id -u)/com.haolin.chrome-debug" >/dev/null 2>&1; then
  ok "com.haolin.chrome-debug 已注册 —— 登录后会自动拉起带调试端口的 Chrome"
else
  bad "com.haolin.chrome-debug 未注册 —— 重启后 Chrome 不会自动开调试端口，S6 必挂"
  fix "launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.haolin.chrome-debug.plist"
fi

# ---------- 2. Chrome 9222 是否在监听 ----------
echo ""
echo "[2] Chrome 调试端口 $PORT 是否在监听"
if cdp_ok "http://127.0.0.1:$PORT/json/version" '"Browser"'; then
  BROWSER="$(cdp_get "http://127.0.0.1:$PORT/json/version" | grep -o '"Browser": "[^"]*"' | head -1 | cut -d'"' -f4)"
  ok "$PORT 已响应，确认为真实 CDP 服务（${BROWSER:-Chrome}）"
else
  bad "$PORT 无响应 —— Chrome 没运行，或启动时没带 --remote-debugging-port"
  warn "注意：手动点 Dock 图标启动的 Chrome **不带**调试端口，必须靠下面的命令启动"
  fix "如果要等自动恢复：先注销再重新登录（RunAtLoad 会触发）"
  fix "立刻手动拉起（复制整段）："
  printf '           /Applications/Google%%20Chrome.app/Contents/MacOS/Google%%20Chrome \\\n             --remote-debugging-port=9222 \\\n             --user-data-dir=%s/chrome-debug-profile \\\n             --no-first-run \\\n             chrome-extension://%s/src/popup/index.html &\n' "$HOME" "$EXT_ID"
fi

# ---------- 3. 扩展 popup 标签是否存在 ----------
echo ""
echo "[3] 文章同步助手扩展的 popup 标签是否常开"
if cdp_ok "http://127.0.0.1:$PORT/json/version" '"Browser"'; then
  HIT="$(cdp_get "http://127.0.0.1:$PORT/json/list" | grep -c "$EXT_ID")"
  if [ "${HIT:-0}" -gt 0 ]; then
    ok "已找到 $HIT 个扩展 target（popup 标签在，wake 脚本可直接复用它注入唤醒）"
  else
    bad "扩展 target 不存在 —— MV3 Service Worker 休眠时 wake 脚本会无页面可复用"
    fix "重新打开这个地址：chrome-extension://$EXT_ID/src/popup/index.html"
    fix "建议保持该标签常开，不要顺手关掉"
  fi
else
  warn "跳过（上一步 9222 未通，先修好 Chrome）"
fi

# ---------- 4. Token 是否配置 ----------
echo ""
echo "[4] WECHATSYNC_TOKEN 是否已配置"
if [ -f "$ROOT/config/pipeline.env" ] && grep -Eq "^[[:space:]]*WECHATSYNC_TOKEN=.+" "$ROOT/config/pipeline.env"; then
  ok "config/pipeline.env 中已配置 Token"
else
  bad "Token 缺失或为空值"
  fix "在 $ROOT/config/pipeline.env 里补上 WECHATSYNC_TOKEN=..."
fi

# ---------- 5. 唤醒扩展 + 平台登录态 ----------
echo ""
echo "[5] 扩展 Service Worker 唤醒 + 平台登录态"

# 定位 wechatsync：命令行优先，找不到再扫 nvm 各版本
WS_BIN="$(command -v wechatsync 2>/dev/null || true)"
if [ -z "$WS_BIN" ]; then
  for c in "$HOME"/.nvm/versions/node/*/bin/wechatsync; do
    [ -x "$c" ] && WS_BIN="$c" && break
  done
fi

if [ -z "$WS_BIN" ]; then
  bad "找不到 wechatsync 可执行文件"
  fix "npm install -g @wechatsync/cli"
else
  ok "wechatsync 位置：${WS_BIN}"

  # 5a 唤醒：MV3 的 SW 会休眠，必须先唤醒
  PYBIN="$(command -v python3 || true)"
  if [ -z "$PYBIN" ]; then
    warn "找不到 python3，跳过唤醒步骤"
  else
    WAKE_OUT="$("$PYBIN" "$SCRIPT_DIR/wake_wechatsync.py" 2>&1)"
    WAKE_RC=$?
    if [ $WAKE_RC -eq 0 ]; then
      ok "扩展 Service Worker 唤醒成功"
    else
      bad "唤醒失败（退出码 $WAKE_RC）—— 后续 auth / sync 都会拿不到扩展响应"
      echo "$WAKE_OUT" | sed 's/^/           /' | head -8
      fix "确认第 3 步的 popup 标签还开着，然后重跑本脚本"
    fi
  fi

  # 5b 登录态复核
  echo ""
  echo "     —— 平台登录态（auth 复核）——"
  set -a
  # shellcheck disable=SC1090
  [ -f "$ROOT/config/pipeline.env" ] && . "$ROOT/config/pipeline.env"
  set +a
  # auth 输出含大量 base64，必须过滤，否则刷屏
  AUTH_OUT="$("$WS_BIN" auth --timeout 25000 2>&1 | grep -v -E "[A-Za-z0-9+/]{40,}={0,2}" | head -30)"
  if [ -z "$(printf '%s' "$AUTH_OUT" | tr -d ' \t\n')" ]; then
    bad "auth 无输出 —— 通常意味着扩展没连上"
    fix "回到第 2、3 步把 Chrome 和 popup 标签修好"
  else
    printf '%s\n' "$AUTH_OUT" | sed 's/^/     /'
    echo ""
    if printf '%s' "$AUTH_OUT" | grep -qiE "invalid|missing token"; then
      bad "Token 无效或缺失 —— 扩展连得上，但身份校验没通过"
      fix "核对 config/pipeline.env 的 WECHATSYNC_TOKEN 是否过期，过期需重新获取"
    elif printf '%s' "$AUTH_OUT" | grep -qE "✖|检查失败"; then
      bad "auth 返回失败 —— 通常是扩展没连上"
      fix "回到第 2、3 步把 Chrome 和 popup 标签修好，再重跑本脚本"
    else
      # ── 按 platforms.json 的启用清单精准比对 ──
      # ⚠️ 不能只看输出里有没有「未登录」二字：auth 会把全部 29 个平台都列出来，
      #    其中绝大多数压根没启用。按启用清单比对，才不会每天误报导致真故障被淹没。
      ENABLED_IDS="$(node -e "
        const j=require('$ROOT/config/platforms.json');
        console.log((j.platforms||[]).filter(p=>p.enabled).map(p=>p.id).join(' '));
      " 2>/dev/null)"
      if [ -z "$ENABLED_IDS" ]; then
        warn "未能从 config/platforms.json 读出启用平台清单，跳过比对"
      else
        # 抽取「已登录」区块中行首的平台 id
        LOGGED_IN="$(printf '%s\n' "$AUTH_OUT" | awk '
          /已登录/ {f=1; next}
          /未登录/ {f=0}
          f && NF>=1 {print $1}
        ')"
        MISSING=""
        for p in $ENABLED_IDS; do
          if ! printf '%s\n' "$LOGGED_IN" | grep -qx "$p"; then
            MISSING="$MISSING $p"
          fi
        done
        if [ -n "$MISSING" ]; then
          bad "以下「启用中」的平台未登录：$(echo $MISSING)"
          fix "用带调试端口的 Chrome 打开对应平台网页版手动登录一次"
          fix "登录态会存进 $HOME/chrome-debug-profile，之后长期有效"
        else
          ok "全部启用平台均已登录：$(echo $ENABLED_IDS)"
        fi
      fi
    fi
  fi
fi

# ---------- 汇总 ----------
echo ""
echo "════ 自检结束 ════"
printf "通过 %d 项，失败 %d 项\n\n" "$PASS" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
  echo "✗ 链路不通，现在跑 S6 会失败。按上面的 → 提示逐条修复后重跑本脚本。"
  echo "  修复完仍不确定，可直接试同步（会立刻暴露问题）："
  echo "    bash $SCRIPT_DIR/sync_drafts.sh"
  exit 1
else
  echo "✓ 链路全通，S6 同步可以正常执行。"
  echo "  重跑今日同步：bash $SCRIPT_DIR/sync_drafts.sh"
  exit 0
fi
