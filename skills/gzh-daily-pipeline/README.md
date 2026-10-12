# GZH Daily Pipeline 🗞️

> 公众号每日内容流水线总调度 skill：**选题 → 写作 → 配图 → 排版 → 多平台 → 草稿箱**，一条 skill 串到底，早上起来只管点发布。

English: An orchestrator skill that runs a full daily publishing pipeline for WeChat Official Accounts (topic selection → multi-draft writing → illustration → typesetting → multi-platform adaptation → draft-box sync), designed for unattended morning runs.

## ✨ 特性

- **无人值守**：全程无人工确认点。自动选题（评分线 + 常青备胎降级）、单环节失败自动降级不中断流水线
- **断点续跑**：产物文件即交接契约（`YYYYMMDD_` 前缀），文件存在 = 阶段完成。重跑只补缺失环节
- **可插拔**：选题 / 写作 / 配图 / 多平台 4 个环节都可换成你自己的实现，只要产物符合交接契约
- **排版自动化**：公众号编辑器只认内联样式，主题 CSS 模板（warm / tech / mono）一键转换，风格每次一致
- **开篇人设图**：固定模板自动生成「人物形象 + 关键词大字 + 口号小字」的插画，双引号文字遵循规则与即梦 AI 一致
- **多平台分发**：8 个平台版本 + Wechatsync 同步草稿箱（含公众号），实测稳定性矩阵内置；知识星球支持 MCP 连接器直发（可选）
- **作者口吻统一**：`author_voice_TEMPLATE.md` 帮你提炼自己的叙事口吻，ABC 三版结构分工、口吻不串味
- **执行报告**：每天产出 `YYYYMMDD_pipeline_report.md`，同步结果 + 人工待办一目了然

## 🏗️ 架构

```
S0 预检(断点续跑)
 └─ S1 选题（热点采集 → TOP10 → 评分审核，自动选 TOP1）
     └─ S2 写作（A 反直觉 / B 观点 / C 实操，三版并行）
         └─ S3 合并（A+C 终稿 + 自检 + 备选标题）
             └─ S4 配图（每篇 2 张，⚙️ `config/pipeline.env` 的 `GZH_IMAGES_PER_ARTICLE`；开篇人设图可选，默认跳过）
                 └─ S4b 排版（Markdown → 内联样式富文本，公众号专用）
                     └─ S5 多平台（知乎/头条/百家号/掘金/CSDN/小红书/星球/口播）
                         └─ S6 分发（Wechatsync 同步草稿箱）
                             └─ S7 报告（产物清单 + 同步结果 + 人工待办）
```

## 🚀 快速开始

### 1. 安装

本地开发：把本目录放到技能目录的 `skills/` 下，并让 5 个环节 skill 与它同级（见「依赖技能」）。

分发给别人：先跑 `python3 scripts/package.py` 产出 `dist/gzh-daily-pipeline/`，再把**那个目录**复制到
对方的技能目录（如 WorkBuddy 的 `~/.workbuddy/skills/gzh-daily-pipeline/`）——它是自包含的，
不再依赖同级技能。

### 2. 填配置

打开 `SKILL.md` 的「**配置在哪改**」表，按「想改什么」找到对应文件，**只改那一处**。
必填项是两份作者人设资源文件：

- 写作侧：`../gzh-write-enhanced/resources/author_voice.md`
- 配图侧：`../gzh-write-enhanced/resources/author_visual_assets.md`

> 文档里出现的所有 `{GZH_XXX}` 都是**占位符不是默认值**，实际数值一律以 `config/` 中读入的为准。

### 3. 配 API

```bash
cp config/pipeline.env.example config/pipeline.env
# 编辑 config/pipeline.env，填入你的图片生成 API（任何 OpenAI images 兼容端点）
```

### 4. 装依赖

```bash
# 排版脚本依赖（全局或本地均可）
npm install markdown-it

# 多平台同步 CLI
npm install -g wechatsync
```

### 5. 跑流水线

对 AI 助手说：**「跑今日流水线」**。产物全部落在你配置的工作目录（默认 `articles/`，详见 `SKILL.md` 路径基准段），最后看 `YYYYMMDD_pipeline_report.md`。

### 6.（可选）挂定时

在支持定时任务的 Agent 环境里（如 WorkBuddy 自动化），每天早上定时触发同一句话，即可实现无人值守：醒来 → 看报告 → 各平台草稿箱点发布。

## 🔌 依赖技能（同级引用，可替换）

本 skill 是**调度器**，不内嵌任何环节 skill。5 个环节技能与它**同级**放在 `skills/` 目录下，
通过 `../<skill>/SKILL.md` 引用。这样每个环节技能既能被流水线调用，也能独立触发、独立替换。

| 环节 | 依赖（同级 `../`） | 产物要求 |
|------|----------|----------|
| 选题 | `topic-collector` + `topic-generator` + `topic-reviewer` | `YYYYMMDD_topics.md`（含选定选题+评分+链接） |
| 写作 | `gzh-write-enhanced`（MIT，[GitHub 原仓库](https://github.com/xiaohuAI319/gzh-write-enhanced)） | `YYYYMMDD_abc.md`（三版）+ `YYYYMMDD_final.md`（合并稿） |
| 多平台 | `公众号文章转多平台`（8 平台转换规则 + Wechatsync 同步） | 各平台 md 文件 |
| 配图 | ❗ ian-xiaohei-illustrations 为**第三方 skill**（版权原因不打包）：WorkBuddy 用户在 skillhub 搜索「小黑插画配图」安装；其他用户用任意 16:9 配图 skill 替代 | 每篇 2 张正文图（拆上下篇共 4 张）；开篇人设图默认跳过 |

只要你的实现产出同样命名的文件，直接替换即可。

### 📤 分发：打包成自包含目录

**直接复制本目录出去会断链**——同级依赖不在包里。需要分发时先跑打包脚本：

```bash
python3 scripts/package.py                      # 产出 <项目根>/dist/gzh-daily-pipeline/
python3 scripts/package.py --out /tmp/dist      # 指定输出位置
python3 scripts/package.py \
    --install-root ~/.workbuddy/skills \        # 顺便改写写死的技能包绝对路径
    --work-dir ~/my-gzh-articles                # 顺便改写写死的产物目录
python3 scripts/package.py --with-illustrations # 连配图 skill 一起打包（如已安装）
```

脚本会做三件事：复制 5 个依赖进包内 `skills/`、把 `../<skill>/` 改写为 `./skills/<skill>/`、
校验产物内引用全部可达。`config/pipeline.env`（含 Token）**不会被复制**。

> 日常开发改 `skills/` 下的源文件，不要改 `dist/`——下次打包会被覆盖。

## 📦 目录结构

```
gzh-daily-pipeline/
├── SKILL.md              # 总调度手册
├── README.md             # 本文件
├── LICENSE               # MIT
├── .gitignore
├── config/               # 打包时从项目根 config/ 复制进来
│   ├── pipeline.env.example   # 共享配置模板（真实值填 pipeline.env，含密钥不提交）
│   └── platforms.json         # 平台开关唯一数据源
├── scripts/
│   ├── load_config.cjs   # 统一配置入口：自动定位项目根，加载 L1 env + L2 platforms.json
│   ├── gzh_format.cjs    # 排版转换：Markdown → 内联样式富文本（3 套主题）
│   ├── gzh_image_api.cjs # 正文配图批量生成（S4-1）
│   ├── gzh_opener.cjs    # 开篇人设图生成（gpt-image 系列 API）
│   ├── package.py        # 分发打包：复制同级依赖与 config/ 进包内并改写引用
│   └── test_sample.md    # 排版脚本自测样例
└── assets/
    └── sample_opener.png # 开篇图示例

> 环节 skill 不在包内，与调度器同级放置（见「依赖技能」一节）。
> 打包后才会出现 `skills/` 子目录——那是产物，不是源码。
    └── sample_opener.png # 开篇图效果样例
```

## 🧪 自测

```bash
# 排版脚本（产出 test_sample_gzh.md，打开检查内联样式）
node scripts/gzh_format.cjs scripts/test_sample.md --theme warm

# 开篇图（需先配好 config/pipeline.env）
node scripts/gzh_opener.cjs --keyword "测试关键词" --out test_opener.png
```

## ❓ FAQ

**Q：公众号草稿箱里排版没生效？**
A：Wechatsync 渲染器可能吞了内联 HTML。降级：素 md 保底入库 → 公众号编辑器套官方模板 → 长期用 playwright RPA 贴富文本。

**Q：Wechatsync 报连接错误？**
A：CLI 走 WebSocket 连 Chrome 扩展，无需 Token。确认 Chrome 在运行、扩展已启用，`wechatsync auth` 预检平台登录状态。

**Q：每天几点跑合适？**
A：建议比你的发布时间提前 1~2 小时。全流程（写作 + 每篇 2 张图 × 2 篇 + 公众号/掘金两平台 + 同步）约 30-60 分钟，取决于所用模型与网络。

**Q：同步到平台会不会违反平台规则？**
A：请自行阅读并遵守各平台服务协议，控制频率。工具只代劳「粘贴到草稿箱」，发布决策权在你。

## ⚠️ 免责声明

- 产出内容的事实与数据请自行核实，**发布行为及内容合规性由使用者自行负责**
- 禁止用于垃圾内容分发、刷量等滥用场景
- 图片生成 API、各平台账号由使用者自备

## 📄 License

[MIT](LICENSE)

> 发布前把 `LICENSE` 里的 `{{YOUR_NAME}}` 替换为你的名字或团队名。
