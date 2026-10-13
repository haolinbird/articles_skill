# AI 编程公众号 SKILL

把「找选题 → 写稿 → 配图 → 排版 → 分发」固化成一条可无人值守的流水线。

- **一次性自动跑完**：用调度器 `skills/gzh-daily-pipeline`，S0 预检 → S7 报告，支持断点续跑
- **单独跑某个环节**：7 个技能都能独立触发，每个 SKILL.md 头部有「运行契约」说明输入输出放哪

---

## 🚀 从零部署（clone 后第一次跑）

**设计目标**：本仓库自包含——所有运行必需的资源都已进 git（含 vendored 的 `ian-xiaohei-illustrations` 配图技能、Node 依赖声明 `package.json`、配置模板）。你 `git clone` 后按下面 5 步配好**本机专属项**（密钥、路径、外部工具），即可本地直接跑整条流水线，**无需再装任何 WorkBuddy 用户级技能**。

```bash
# ① 拉代码
git clone <你的仓库地址> gzh && cd gzh

# ② 装 Node 依赖（仅 markdown-it，用于 S4b 排版）
#    Python 脚本全标准库，无需任何 pip 安装
npm install

# ③ 装外部命令行工具（系统级依赖，不进仓库）
npm install -g @wechatsync/cli        # S6 分发用的 wechatsync CLI

# ④ 配密钥：从模板复制后填入真实值（pipeline.env 已被 .gitignore 排除，不会入库）
cp config/pipeline.env.example config/pipeline.env
#   用编辑器打开 config/pipeline.env，至少填两项：
#     GZH_T2I_API_KEY / GZH_T2I_BASE_URL   商汤生图 Key（S4 配图；留空则自动跳过配图）
#     WECHATSYNC_TOKEN                     wechatsync Token（S6 同步；见下方「初次拿 Token」）
#   其余默认值已在 .example 里给好，一般不用动

# ⑤ 跑流水线（调度器 S0 预检会逐项查环境，缺失项写进报告、不阻断运行）
#   具体触发方式见 WorkBuddy 里对 gzh-daily-pipeline 技能的调用；
#   也可单独跑某个环节（见下文「技能清单」）
```

**初次拿 wechatsync Token**：在 Chrome 里装好「文章同步助手」扩展（扩展 ID 见 `config/chrome-debug.launchagent.plist.example`），登录公众号 / 掘金网页版后运行 `wechatsync auth`，会把 Token 写进扩展本地存储；再把该 Token 抄进 `config/pipeline.env` 的 `WECHATSYNC_TOKEN`，之后每次同步前 `wechatsync auth` 会刷新它。

**可选：无人值守定时（macOS launchd）**：`config/` 下有两个 `*.launchagent.plist.example` 模板，把里面的 `{{PROJECT_ROOT}}` / `{{HOME}}` / `{{NODE_BIN}}` 占位符替换成你的实际路径，`launchctl bootstrap` 加载即可。它们负责 S6 唯一依赖的本机运行时——带调试端口的 Chrome + 唤醒扩展（详见「首次搭建 / 换机重建」一节）。

> ⚠️ 本仓库是**公开仓库**：`config/pipeline.env` 已在 `.gitignore` 排除，只有 `pipeline.env.example` 模板入库。**切勿把真实密钥提交进 git。**

---

## 🔧 改配置前先看这里

**只查这一张表，按你想做的事找行，然后只改那一个文件。**

| 我想…… | 唯一改这里 | 具体项 |
|---|---|---|
| 换图片生成渠道 / 模型 / Key | `config/pipeline.env` | `GZH_T2I_ENDPOINT` `GZH_T2I_API_KEY` `GZH_T2I_MODEL` `GZH_T2I_PROTOCOL` |
| 每篇正文配几张图 | `config/pipeline.env` | `GZH_IMAGES_PER_ARTICLE` |
| 文章写多长（字数门） | `config/pipeline.env` | `GZH_WORD_MIN` `GZH_WORD_MAX` |
| 一天最多发几篇 | `config/pipeline.env` | `GZH_MAX_ARTICLES_PER_DAY` |
| 图片加水印 / 改尺寸 | `config/pipeline.env` | `GZH_T2I_WATERMARK` `GZH_T2I_SIZE` |
| 彻底关掉配图 | `config/pipeline.env` | `GZH_T2I_ENABLED=false` |
| **启用 / 停用某个发布平台** | `config/platforms.json` | 对应平台的 `enabled: true/false` |
| 改某平台的同步参数、产物名 | `config/platforms.json` | 该平台的 `wechatsync` / `output_files` |
| Wechatsync Token 过期 | `config/pipeline.env` | `WECHATSYNC_TOKEN` |
| **改作者人设、口吻、开场白** | `skills/gzh-write-enhanced/resources/author_voice.md` | 全文（唯一权威副本） |
| 改选题评分权重 / 通过线 | `skills/topic-reviewer/SKILL.md` | 「评分项（满分100）」表 |
| 改配图风格（小黑 IP、配色、禁忌） | `skills/ian-xiaohei-illustrations/references/` | `style-dna.md` `xiaohei-ip.md` `prompt-template.md` |
| 改排版主题色 | 命令行参数 | `gzh_format.cjs --theme warm/tech/mono` |
| **改每日几点自动跑 / 停用定时任务** | **WorkBuddy 定时任务**（不在本仓库文件里） | 名为「每日公众号流水线（选题→草稿箱）」，当前每天 07:30 |

### 改完还要注意两件事

| 场景 | 要做什么 |
|---|---|
| 改了上面任意一项 | **不用重新打包**——打包只影响 `dist/` 分发产物，本地跑读的是源文件 |
| 要分发给别人 | 重跑 `python3 skills/gzh-daily-pipeline/scripts/package.py` |

---

## 配置为什么分三处

不是随意放的，按**「会不会被两个以上技能读到」**切：

| 层 | 位置 | 放什么 | 为什么在这里 |
|---|---|---|---|
| **L1 共享参数** | `config/pipeline.env` | 密钥、字数门、日产量、图片通道 | 脚本和多个阶段都要读，必须单点 |
| **L2 能力清单** | `config/platforms.json` | 9 个平台的启用状态与同步参数 | 机器读的，脚本能直接解析 |
| **L3 技能私有** | 各技能的 `resources/` 或正文 | 人设、评分权重、配图风格 | 只有一个技能读，跟着技能走 |

**新增配置项时按这条规则放**：会被两个以上技能读到 → 进 `config/`；只有一个技能用 → 留在该技能目录里。

> ⚠️ **本 README 一个配置值都不写**。写了它就成了第二份真相，改的时候就是两处。
> 本文件只回答「在哪改」，不回答「现在是什么」。想知道当前值，去对应的文件看。

---

## 技能清单

| 技能 | 作用 | 输入 → 产物 | 能单独跑吗 |
|---|---|---|---|
| `gzh-daily-pipeline` | **调度器**，串起全流程 | 无 → 全流程产物 + `articles/YYYYMMDD/pipeline_report.md` | 就是入口 |
| `topic-collector` | 采集 AI 热点 | 网络 → `topics/YYYY-MM-DD.md` | ✅ |
| `topic-generator` | 热点筛出 TOP10 选题 | `topics/YYYY-MM-DD.md` → 对话输出（不落盘） | ✅ |
| `topic-reviewer` | 选题打分 / 一票否决 | 选题 → 对话输出（不落盘） | ✅ |
| `gzh-write-enhanced` | 三版写作 + 四层自检 | TOP1 选题 → `articles/YYYYMMDD/abc.md` | ✅ |
| `公众号文章转多平台` | 按平台风格改写 | 终稿 md → 按 `platforms.json` 产出 | ✅ |
| `ian-xiaohei-illustrations` | 小黑手绘配图 | 正文 + shot list → `assets/YYYYMMDD-<主题>/NN-<slug>.png` | ✅ |

每个技能的 SKILL.md 头部都有**运行契约**（输入 / 产物 / 幂等 / 前置），
单独跑和流水线调用走的是同一套契约——调度器只是按顺序满足上一环的产物路径，不是两套逻辑。

## 🔌 重启之后：怎么保证 S6 同步不失败

流水线 S0–S5（选题、写稿、排版、多平台）全是纯 AI + 本地脚本，**关机重启不影响**。
只有 **S6 草稿箱同步**依赖本机运行时环境 —— 它是整条链唯一可能"机器一重启就哑火"的环节。

依赖链，任何一环断掉 S6 就失败：

| # | 依赖 | 谁负责 | 重启后自动恢复吗 |
|---|---|---|---|
| 1 | Chrome 带 `--remote-debugging-port=9222` 运行 | launchd `com.haolin.chrome-debug` | ✅ 登录后自动拉起（RunAtLoad） |
| 2 | 文章同步助手扩展的 popup 标签常开 | Chrome 启动参数自带 | ✅ 自动打开 |
| 3 | 平台已登录（登录态存在 `~/chrome-debug-profile`） | Chrome profile | ✅ 长期有效，除非 Cookie 过期 |
| 4 | `WECHATSYNC_TOKEN` 有效 | `config/pipeline.env` | ✅ 静态配置 |
| 5 | 扩展 MV3 Service Worker 处于唤醒态 | `wake_wechatsync.py` | ❌ **会休眠，每次同步前要唤醒** |

**结论：重启并登录后，绝大多数情况什么都不用做。** 但第 5 环不在开机自恢复范围内，
所以自动化任务每次都先跑唤醒脚本 —— 这也是为什么自检必须覆盖它。

### 一步体检（推荐，不用背命令）

```bash
bash skills/gzh-daily-pipeline/scripts/check_sync_ready.sh
```

只读检查，不杀进程不删文件。它会依次验证上面 5 环，
每项打 `[OK]` / `[FAIL]`，失败项直接给出对应的修复命令。

看两个地方就够了：

- 末尾 `✓ 链路全通` 且退出码 `0` → 可以直接同步
- 末尾 `✗ 链路不通` 且退出码 `1` → 按 `→` 提示逐条修，修完重跑一次脚本

> 明天第一次用建议先跑它确认一遍，别等流水线报错才发现链路是断的。

### 手动命令参考

自检脚本之外，这几条是故障时最直接的手段：

```bash
# ① 确认 Chrome 调试网关是否在 launchd 里注册（精确查单个 label）
launchctl print gui/$(id -u)/com.haolin.chrome-debug

# ② 没有则加回来（plist 文件一直在，只是停用状态）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.haolin.chrome-debug.plist

# ③ 不等重启，立刻手动拉起带调试端口的 Chrome（整段复制，末尾 URL 是关键）
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=$HOME/chrome-debug-profile \
  --no-first-run \
  chrome-extension://hchobocdmclopcbnibdnoafilagadion/src/popup/index.html &

# ④ 补回应答：重跑今日同步
bash skills/gzh-daily-pipeline/scripts/sync_drafts.sh
```

⚠️ **别点 Dock 上的 Chrome 图标拉起** —— 那样启动的实例**不带调试端口**，
看起来浏览器开着，实际 9222 没人监听，S6 必然失败。要么等自动拉起，要么用上面 ③ 的命令。

### 首次搭建 / 换机重建：调试 profile 从哪来

上面 ③ 里的 `--user-data-dir=$HOME/chrome-debug-profile` **不是 Chrome 自带的**，是从真实 profile 克隆出来的。

为什么要多这一步：Chrome 安全策略禁止对默认 profile 开远程调试端口
（会报 `DevTools remote debugging requires a non-default data directory`），
但登录态和 Wechatsync 扩展又必须保留 —— 只能复制一份到非默认目录。

两个脚本已封装好，**严格按这个顺序跑**：

```bash
# ⓪ 前提：完全退出 Chrome（否则复制出的登录态可能不一致）
pkill -f "Google Chrome"

# ① 克隆 profile：排除 18G 缓存，只保留扩展 + 登录态（约数百 MB）
bash skills/gzh-daily-pipeline/scripts/clone_chrome_profile.sh

# ② 用克隆出的 profile 启动带调试端口的 Chrome
bash skills/gzh-daily-pipeline/scripts/chrome_debug_launch.sh
```

① 只需做一次，之后 launchd 会自动用这个 profile 拉起。
**换机、清过 Chrome 数据、或所有平台登录态一起失效时**，才需要重跑 ①。

### 常见故障对照

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 报告写"同步失败"，但浏览器明明开着 | 那是不带调试端口的实例 | 退出它，用 ③ 的命令重开 |
| 自检说 9222 通、`auth` 却报 `Invalid or missing token` | Token 过期了 | 更新 `config/pipeline.env` 的 `WECHATSYNC_TOKEN` |
| `[FAIL] 扩展 target 不存在` | popup 标签被手动关掉了 | 重开第 2 节那个 `chrome-extension://` 地址，**保持常开** |
| `auth` 显示某平台未登录 | Cookie 过期或被清 | 用带调试端口的 Chrome 打开该平台网页版手动登录一次 |
| 关机 / 未登录图形会话导致当天没跑 | LaunchAgent 需登录后才加载 | 开机并登录后手动补跑流水线 |

---

## 目录速览

```text
config/           ← 配置唯一入口（改配置从这里进）
  pipeline.env          L1 共享参数（含密钥，勿外传）
  pipeline.env.example  模板（无密钥，可提交）
  platforms.json        L2 平台开关（9 个平台）
skills/           ← 7 个技能，每个可独立运行
articles/         ← 流水线产物按日归档（articles/YYYYMMDD/：终稿、排版稿、报告、封面图）
assets/           ← 配图，按 assets/YYYYMMDD-<主题>/ 归档
topics/           ← 采集到的原始热点
dist/             ← 分发产物，改源文件后重打包，不要直接改这里
.archive/         ← 历史归档（含删除文件的备份，可找回）
```

## 分发打包（dist）

`dist/` 是构建产物（已在 `.gitignore` 排除），**不要直接改这里的文件**，改完源文件重跑即可同步：

```bash
python3 skills/gzh-daily-pipeline/scripts/package.py
```

> 如果你只是用 `git clone` 下来的仓库**自己跑**流水线，**不需要打包**——脚本直接读源文件即可；`dist/` 仅用于把技能分发给没有本仓库的人。

**要分发给其他人时，必须带 `--install-root`** —— 不带的话，包内脚本里写死的本机绝对路径不会被改写，
对方 clone 下来运行会直接找不到路径：

```bash
python3 skills/gzh-daily-pipeline/scripts/package.py \
  --install-root ~/.workbuddy/skills \
  --work-dir ~/my-gzh-articles
```

| 参数 | 作用 |
|---|---|
| `--install-root` | 目标安装位，用于改写包内写死的技能包绝对路径 |
| `--work-dir` | 目标机器上的产物目录（articles / assets / topics 的根） |
| `--with-illustrations` | 一并打包可选配图技能 `ian-xiaohei-illustrations` |

SKILL.md 里已不写本机路径（统一用 `<项目根>` 占位符），Node 依赖通过仓库内 `node_modules/`（`npm install`）解决，Python 脚本全标准库，**所以文档部分无需改写**。
安全：`package.py` 绝不复制含密钥的文件（`.env`、`config/pipeline.env`），只复制 `pipeline.env.example`。

## 产物清理（articles / assets / topics 只增不减）

这三个目录每天新增，几个月后会堆到几百 MB。用清理脚本按天保留：

```bash
# 预览（默认保留最近 30 天，不改动任何文件）
python3 skills/gzh-daily-pipeline/scripts/cleanup_products.py

# 归档到 .archive/cleanup-<今天>/（可找回）
python3 skills/gzh-daily-pipeline/scripts/cleanup_products.py --apply

# 确认不需要后再真删除
python3 skills/gzh-daily-pipeline/scripts/cleanup_products.py --apply --delete
```

| 参数 | 说明 |
|---|---|
| `--days N` | 保留最近 N 天，默认 30 |
| `--apply` | 实际执行（不给就只预览） |
| `--delete` | 真删除；**必须与 `--apply` 同时给**，单独给会报错 |

脚本认不出日期的文件一律跳过，不会误伤。建议每月跑一次预览，或挂到自动化里做「归档」而非删除。

---

## 三条踩过的坑

**1. 人设只有一份，2026-10-11 之后别再找第二份。** 此前项目根有一份手写基线 `author_voice.md`，
与 `skills/gzh-write-enhanced/resources/author_voice.md` 内容重叠但更简略，形成两份真相。
逐条比对确认后者**完整覆盖**前者（零信息丢失）后，根目录那份已删除，
备份留档在 `.archive/author-voice-baseline-20261011/`。
**现在人设单点定义**：改 `skills/gzh-write-enhanced/resources/author_voice.md` 这一份即可，
写作技能、调度器、打包脚本全部读它。

**2. 本机 curl 走代理，会把「端口没服务」误判成「通」。**
本机配了 HTTP 代理时，`curl http://127.0.0.1:9222/...` 会把请求交给代理。
目标端口没服务时，代理虽返回一串 `upstream connect failed` 错误文本，**curl 退出码却仍是 0**。
后果很隐蔽：Chrome 压根没起来，检测脚本却报告"链路正常"，S6 静默失败且查不到原因。
**修法**：测本机端口一律加 `--noproxy '*'`，并且校验响应内容确实是 CDP 返回的 JSON，两者缺一不可。
（同理，`launchctl list | grep` 也可能返回空列表造成假阴性 —— 要用 `launchctl print gui/$(id -u)/<label>` 精确查。）

**3. 有 `.git` 不等于能回滚 —— 删文件前先确认它进没进过提交。**
项目日常改动常只 `git add` 不 `git commit`，**真正能安全回滚的只有已提交的版本**（当前分支
已有多次提交，但仍有改动停在暂存/工作区）。别以为有 `.git` 就敢删文件。删之前务必先确认
它是否真的进过 HEAD 提交：

```bash
git ls-tree -r HEAD --name-only | grep <文件名>   # 有输出 = 安全；无输出 = 删了就没了
```

（之前删的根 `author_voice.md` 就从未进过 HEAD，是靠手动备份到 `.archive/` 才保住的。）

另外：**先建 `.gitignore` 再 commit / push**。`config/pipeline.env` 含 Wechatsync Token 等密钥，
必须确认它已被 `.gitignore` 覆盖（用 `git check-ignore config/pipeline.env` 验证返回该路径）
再提交 —— 一旦落入版本历史，密钥就永久洗不掉（需重写历史或 force push）。
