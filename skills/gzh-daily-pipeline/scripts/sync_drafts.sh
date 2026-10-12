#!/usr/bin/env bash
#
# sync_drafts.sh — 无人值守同步文章草稿到公众号 + 掘金
#
# 流程: 1) CDP 唤醒 Wechatsync 扩展 SW(发 MCP_WATCH_START, 免去手动开弹窗)
#       2) wechatsync auth 复核连接
#       3) wechatsync sync 推公众号 + 掘金草稿箱
#
# 前置: Chrome 已带 --remote-debugging-port=9222 启动
#       config/pipeline.env 已配置 WECHATSYNC_TOKEN
#
# 用法:
#   sync_drafts.sh [<公众号md> <掘金md> <标题>]
#   不传参数时, 默认使用今天的日期文件与空标题(wechatsync 会取正文首标题)
#
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ART="$ROOT/articles"
PY="$ROOT/skills/gzh-daily-pipeline/scripts/wake_wechatsync.py"
PYBIN=/Users/haolin/.workbuddy/binaries/python/envs/default/bin/python
DATE="$(date +%Y%m%d)"

GZH="${1:-$ART/${DATE}_final_gzh.md}"
JUEJIN="${2:-$ART/${DATE}_稀土掘金_发布版.md}"
# 标题：优先用传入参数（两平台同用）；否则各取各的——
# 掘金从 YAML frontmatter 取，公众号从首行 HTML 注释「标题: 」取（两平台标题常不同，不能共用）。
TITLE="${3:-}"
if [ -n "$TITLE" ]; then
  GZH_TITLE="$TITLE"; JUEJIN_TITLE="$TITLE"
else
  JUEJIN_TITLE=""
  GZH_TITLE=""
  if [ -f "$JUEJIN" ]; then
    JUEJIN_TITLE="$(grep -m1 '^title:' "$JUEJIN" | sed -E "s/^title:[[:space:]]*['\"]?([^'\"]*)['\"]?/\1/")"
  fi
  if [ -f "$GZH" ]; then
    GZH_TITLE="$(grep -m1 '标题:' "$GZH" | sed -E 's/.*标题:[[:space:]]*([^|]+).*/\1/' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  fi
fi

# 加载 token(非交互 shell 不读 .zshrc, 必须显式 source)
set -a
source "$ROOT/config/pipeline.env"
set +a

filter() { grep -v -E "[A-Za-z0-9+/]{40,}={0,2}"; }

echo "=== [1/3] 唤醒 Wechatsync Service Worker ==="
if ! "$PYBIN" "$PY"; then
  echo "唤醒失败: 请确认 Chrome 已带 --remote-debugging-port=9222 启动" >&2
  exit 1
fi

echo "=== [2/3] auth 复核 ==="
wechatsync auth --timeout 20000 2>&1 | filter | head -25

echo "=== [3/3] 同步草稿 ==="
# 公众号必须带封面（config/platforms.json weixin.wechatsync.cover=true，漏带则草稿无封面图、
# 发表按钮灰、提示「内容不完整」无法发表）。封面比例须为 16:9 / 1:1 / 2.35:1 之一，且应为小黑风格；
# 开篇图(_开篇图.jpg)是绿色人设图、3:2 比例会被微信 200040 拒绝，绝不可作封面。
# 封面图(_封面图.jpg)由 S4 生成，为 16:9 小黑风合规封面。
COVER="$ART/${DATE}_封面图.jpg"
COVER_ARGS=""
if [ -f "$COVER" ]; then
  COVER_ARGS="--cover $COVER"
  echo "封面: $COVER"
else
  echo "⚠️ 未找到封面图 $COVER，公众号草稿将无封面、无法发表（请用 S4 生成 16:9 小黑封面图）"
fi
if [ -n "$GZH_TITLE" ]; then
  wechatsync sync "$GZH"    -p weixin -t "$GZH_TITLE" $COVER_ARGS 2>&1 | filter | head -25
else
  wechatsync sync "$GZH"    -p weixin $COVER_ARGS 2>&1 | filter | head -25
fi
if [ -n "$JUEJIN_TITLE" ]; then
  wechatsync sync "$JUEJIN" -p juejin -t "$JUEJIN_TITLE" 2>&1 | filter | head -25
else
  wechatsync sync "$JUEJIN" -p juejin 2>&1 | filter | head -25
fi

echo "=== 同步完成 ==="
