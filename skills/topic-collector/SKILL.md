---
name: topic-collector
description: AI编程应用热点采集工具。从X、Hacker News、Reddit、Product Hunt、官方博客等采集前一天00:00至今的AI编程相关热点。当用户说"开始今日选题"、"采集热点"、"看看今天有什么新闻"、"今日AI热点"、"collect AI coding news"时触发。聚焦「用AI提升编程效率」与「用AI编程为业务提效」，不采集底层大模型研发内容。
---

# Topic Collector - AI热点采集

## 运行契约（单独跑 / 被调度器调用都走这一套）

- **输入**：无文件输入。从网络采集，跑 `scripts/fetch_sources.py`（默认取前一天 00:00 至今，**自然日窗口**，不是滑动 24 小时）
- **产物**：`topics/YYYY-MM-DD.md`（工作区根 `topics/` 下，**命名带横杠**），原始热点 40+ 条
- **幂等**：重跑覆盖同日文件（同一天多次跑，以最后一次为准）
- **前置**：Python 3 可运行；**无需任何 API Key**

> ⚠️ 易错：本技能产物是**原始热点**，与调度器 S1 落盘的 `articles/YYYYMMDD_topics.md`
> （TOP3 选题方案）**不是同一个文件**——目录和命名都不同，不要互相顶替，也不要改 collector 的落盘路径。

## 采集流程

1. **确定时间窗口**：**按自然日**，起点固定为前一天 00:00:00（UTC+8），终点为当前时刻。
   不使用"最近 24 小时"滑动窗口——滑动窗口会让同一天不同时刻运行的结果不一致，
   早些时候抓到的条目在窗口后移后凭空消失（详见「时间窗口口径」）
2. **运行抓取脚本**：`python3 scripts/fetch_sources.py`，默认即为前一天 00:00 至今，覆盖国内外全部 feed
3. **WebSearch 补充**（可选）：仅补脚本未覆盖的源，带 `freshness: "d2"` 以覆盖跨天窗口
4. **过滤低质源**：命中任一低质信号的条目直接丢弃
5. **分类整理**：按来源类型分类，统一成约定的字段结构
6. **达标检查**：对照「收录门槛」自检，未达标则补搜
7. **落盘**：写入 `topics/YYYY-MM-DD.md` 并在对话中报告路径与覆盖情况

时间口径与搜索序列见「采集执行步骤」，字段定义见「数据契约与落盘」。

## 数据源分类

### 一、AI编程实践者（工具玩法、工作流、提效案例）

**定位约束**：只采集「用AI提升编程效率」和「用AI编程为业务提效」两类内容。
不采集底层大模型训练、模型架构、推理引擎、AI安全等与编程应用无关的议题。

**X 重点账号**：

*工具厂商与产品方*
- @bcherny - Boris Cherny，Claude Code 负责人（Anthropic）
- @thsottiaux - Thibault Sottiaux，OpenAI Codex 工程负责人
- @rauchg - Guillermo Rauch，Vercel CEO，AI-native 技术栈
- @AnthropicAI / @OpenAI - 官方发布

*编程实践者与工程方法*
- @karpathy - Andrej Karpathy，Vibe Coding 概念提出者
- @addyosmani - Addy Osmani，Loop Engineering、AI编码工作流
- @mitsuhiko - Armin Ronacher，Flask作者，agentic coding 长文
- @simonw - Simon Willison，LLM工具实践与实测记录
- @thorstenball - Thorsten Ball，Amp/Sourcegraph，coding agent 原理
- @steipete - Peter Steinberger，OpenClaw作者，agent harness 设计
- @swyx - Shawn Wang，AI Engineer / Latent Space
- @theo - Theo Browne，AI工具与 TypeScript 技术栈

*业务提效视角*
- @levelsio - Pieter Levels，AI独立开发与商业化
- @emollick - Ethan Mollick，AI用于真实工作场景
- @HamelHusain - Hamel Husain，AI产品评测与 evals

**账号可靠性规则（重要）**
- 搜不到某账号近期内容就跳过，不要用相似名字猜测或补全
- 账号只是入口提示，不是信息来源保证；一切以检索到的实际内容为准
- 清单会失效：某账号长期无更新则直接跳过，不要反复尝试

**搜索关键词**：
```
"Claude Code" workflow OR tips OR "best practices"
"Cursor" OR "Codex" OR "Copilot" developer workflow
vibe coding OR "AI coding" productivity
AI agent harness OR "agentic coding" workflow
Claude MCP server OR "Claude Skill" tutorial
```

### 二、创业公司/产品发布

**Product Hunt**：
- 搜索：AI、Developer Tools、Productivity分类
- 当日上榜产品
- 提取：产品名 + 描述 + upvotes + 产品页链接

**Hacker News**：
- Show HN中的AI项目
- Launch HN中的AI创业公司
- 提取：标题 + 讨论链接 + 评论数

### 三、研究动态（仅在与编程应用直接相关时采集）

**收录标准**：只在直接影响编程工作流时采集，例如新模型显著提升代码能力、
新的 agent 架构可被工程复现。纯模型能力评测、训练方法、架构论文一律不采集。

**关注来源**：
- arXiv 中被工程社区广泛讨论的 coding agent 相关论文
- Anthropic / OpenAI 工程博客
- Google DeepMind、Meta AI、Microsoft Research 中与开发工具相关的部分

**搜索关键词**：
```
coding agent benchmark OR evaluation
LLM code generation improvement
AI software engineering research
```

### 四、工具与厂商官方动态

只采集与编程工作流直接相关的更新，不采集模型能力排行榜或评测对比。
以 changelog / release notes / 工程博客为准，不用 `site:` 操作符（多数检索工具不支持）。

| 厂商/工具 | 搜索关键词 |
|------|------------|
| Anthropic | Claude Code release OR changelog |
| OpenAI | Codex OR "ChatGPT" coding update |
| Cursor | Cursor editor release OR changelog |
| GitHub | Copilot update OR changelog |
| Google | "Gemini CLI" OR Jules coding agent update |
| Vercel | v0 OR "AI SDK" update |

### 五、技术社区讨论

**Reddit子版**：
- r/ClaudeAI - Claude 使用与技巧
- r/Cursor - Cursor 实战问题
- r/ChatGPTCoding - AI 辅助编程
- r/ExperiencedDevs - 从业者视角的 AI 工具讨论

**不采集的子版**：r/LocalLLaMA（本地模型部署）、r/MachineLearning（学术论文）、
r/artificial（泛 AI 新闻）——与编程应用定位不符。

**Hacker News**：
- AI 编程工具相关讨论
- Show HN 中的开发者工具项目

### 六、国内数据源（重点：AI编程在企业落地）

**获取方式**：直取 RSS/Atom feed。WebSearch 对国内站点在短窗口下命中率极低，不作为主路径。

| 源 | feed 地址 | 更新频率 | 内容定位 |
|------|-----------|----------|----------|
| 掘金 | `https://juejin.cn/rss` | 每日 20+ 条 | AI编程实践、工具教程，量大需筛 |
| InfoQ中国 | `https://www.infoq.cn/feed` | 每日 | 企业级技术落地、架构案例、大会演讲整理 |
| 开源中国 | `https://www.oschina.net/news/rss` | 每日，AI 内容偶发 | 技术资讯与开源项目 |
| 美团技术团队 | `https://tech.meituan.com/feed/` | 低频（周/月更） | 大厂 AI 落地实践，稀缺但质量高 |

**低频源处理**：美团技术这类源当日常无更新，不强制每日产出；
命中时优先级最高——大厂真实落地案例比教程稀缺得多。

**企业落地专项关键词**（标题或摘要命中任一即重点关注）：
`落地` `企业级` `生产环境` `内部平台` `中台` `研发效能` `交付效率`
`降本增效` `编码规范` `代码审查` `质量控制` `团队转型` `规模化` `试点`

**国内源筛选规则**：
- 掘金 feed 含大量与 AI 无关的前端/运维/数据库文章，必须按关键词过滤后再入库
- 排除纯框架入门教程（如"LangChain4j 新手入门"）与底层原理（如"交叉熵"）
- 标题为序号片段（如"2.skill"）的条目需打开确认后再决定是否收录，
  确认不了就标注「标题信息不足」而非丢弃
- 国内 feed 一般不含热度数据，heat 一律写 `N/A`

## 聚焦领域（优先级排序）

1. **Vibe Coding / AI编程工作流** - Cursor、Claude Code、Codex 的实战方法
2. **Claude生态** - Claude Skill、MCP Server、Subagent、Hooks
3. **AI Agent工程** - harness 设计、上下文工程、多 agent 协作
4. **工具与模型更新** - 真正影响编程工作流的能力变化
5. **业务提效案例** - 用 AI 编程交付业务的可复用路径
6. **AI新产品** - DevTools 方向的上榜产品、独立开发者作品

**明确排除**：底层大模型研发、AI知识管理/Obsidian、纯行业融资收购。
这些与公众号「AI编程应用实战」定位不符。

## 数据契约与落盘

### 统一字段（三个技能共用）

每条热点必须包含以下字段，字段名固定不变：

| 字段 | 含义 | 缺失时 |
|------|------|--------|
| title | 标题或一句话摘要 | 必填 |
| source | 来源平台或账号 | 必填 |
| url | 原文链接 | 必填，无则丢弃该条 |
| published_at | 发布时间，YYYY-MM-DD HH:MM（UTC+8） | N/A |
| heat | 热度（likes / upvotes / comments） | N/A |
| summary | 一句话要点 | 必填 |
| tags | 领域标签，取自聚焦领域 | 必填 |
| lang | 中 / 英 | 必填 |

下游 `topic-generator` 与 `topic-reviewer` 依赖这套字段。`published_at`
尤其关键——reviewer 的时效否决完全依赖它，缺失该字段的条目在选题阶段
无法判定，会被降级处理。

### 落盘

采集结果**必须**写入文件，不能只输出到对话：

- 路径：`topics/YYYY-MM-DD.md`（工作区根目录下，日期取采集当天）
- 文件首部用 YAML frontmatter 记录本轮元信息
- 采集完成后在对话中报告文件路径与覆盖情况

```markdown
---
date: 2026-10-04
collected_at: 2026-10-04 23:53
window: 2026-10-03 00:00:00 ~ 2026-10-04 23:53 CST（前一天 00:00 至今）
window_mode: day_start
total: 18
by_source:
  x: 5
  hackernews: 4
  reddit: 3
  producthunt: 2
  official: 4
---

# 今日AI编程热点 - 1004
```

若 `topics/` 目录不存在则创建。

**同一天重复采集时必须合并，不能整体覆盖**：

RSS/Atom feed 只保留最新若干条，晚些时候运行可能抓不到早些时候已抓到的条目
（实测：掘金当天 07:40 发布的条目在 01:29 再次运行时已被挤出 feed）。
若直接覆盖，这些条目就永久丢失了。合并规则：

1. 读取已存在的 `topics/YYYY-MM-DD.md`，解析出已有条目的 URL 集合
2. 新抓到的条目中与已有 URL 重复的，跳过（保留首次记录，含其原文描述）
3. 新条目追加进对应分类章节
4. 更新 frontmatter：`collected_at`、`total`、`by_source`，
   并新增 `carried_over` 记录跨次保留的条数
5. 跨次保留的条目在正文末尾加一行
   `⚠️ 跨次保留：本条在 <时刻> 那次采集中抓到，本次运行已不在 feed 中，按合并规则保留`

## 数据诚实性规则（一票否决）

WebSearch 无法可靠获取 X/Twitter、Product Hunt 的实时互动数据。因此：

- 任何无法从检索结果中直接确认的字段，一律写 `N/A`
- 禁止估算、推断或填充热度数字（likes / retweets / upvotes / comments）
- 禁止为凑满条数而生成看似合理但无出处的条目；条数不足就如实少报
- 每条必须有可点击的真实 URL；无 URL 的条目直接丢弃
- 链接存疑时用 WebFetch 打开验证，打不开就丢弃
- 不确定的时间一律写 `N/A`，不要写"近日""最近"这类模糊表述

## 输出格式

按「数据契约与落盘」中的统一字段输出。模板中的行与字段对应关系：
作者=source、发布时间=published_at、原文=url、要点=summary、热度=heat。
标签（tags）与语言（lang）以 `[标签][语言]` 形式附在要点行末尾。

```markdown
## 今日AI热点 - MMDD

---

### 🧑‍💻 AI编程实践分享

1. **[标题/内容摘要]**
   - 作者：@用户名
   - 发布时间：YYYY-MM-DD HH:MM（UTC+8）；不确定写 N/A
   - 原文：[具体URL](https://...)
   - 要点：一句话总结
   - 热度：❤️ likes | 🔁 retweets；取不到写 N/A

---

### 🚀 创业公司/新产品

1. **[产品名]** - 一句话描述
   - 发布时间：YYYY-MM-DD；不确定写 N/A
   - 链接：[Product Hunt页面](https://producthunt.com/posts/xxx)
   - 热度：⬆️ N upvotes；取不到写 N/A
   - 分类：AI / DevTools / Productivity

---

### 🔬 研究动态（限编程相关）

1. **[论文/博客标题]**
   - 来源：Anthropic / OpenAI 工程博客 / arXiv
   - 发布时间：YYYY-MM-DD；不确定写 N/A
   - 原文：[具体URL](https://...)
   - 要点：核心发现，以及它对编程工作流的实际影响

---

### 🏢 工具与模型厂商动态

1. **[更新/发布内容]**
   - 厂商：Anthropic / OpenAI / Cursor / Google
   - 发布时间：YYYY-MM-DD；不确定写 N/A
   - 原文：[官方博客链接](https://...)
   - 要点：关键变化

---

### 💬 社区热议

1. **[讨论标题]**
   - 来源：r/ClaudeAI / r/Cursor / Hacker News
   - 发布时间：YYYY-MM-DD；不确定写 N/A
   - 链接：[帖子URL](https://...)
   - 热度：⬆️ upvotes | 💬 comments；取不到写 N/A
   - 核心观点：一句话

---

### 🇨🇳 国内动态（AI编程企业落地优先）

#### 企业落地实践

1. **[标题]**
   - 来源：掘金 / InfoQ中国 / 开源中国 / 美团技术
   - 发布时间：YYYY-MM-DD HH:MM
   - 原文：[URL](https://...)
   - 要点：解决了什么问题、怎么落地、结果如何 [中]
   - 热度：N/A（国内 feed 一般无热度数据）

#### 实践与教程

1. **[标题]**
   - 来源：掘金 / InfoQ中国
   - 发布时间：YYYY-MM-DD HH:MM
   - 原文：[URL](https://...)
   - 要点：可复现的方法或踩坑结论 [中]
   - 热度：N/A
```

## 采集执行步骤

### 时间窗口口径（每次执行必读）

窗口按**自然日**切分，不是"最近 N 小时"：

- **起点**：前一天 00:00:00（UTC+8）
- **终点**：当前时刻

例如 2026-10-05 当天任意时刻运行，起点都是 2026-10-04 00:00:00。
当天跑得越晚，窗口越长（01:00 跑约 25 小时，23:50 跑约 48 小时），
但**起点始终不变**。跨过午夜后起点自动滚动到新的前一天。

**为什么不用滑动 24 小时窗口**：滑动窗口下，同一天不同时刻运行会得到不同结果——
早些时候抓到的条目会随窗口后移而消失。实测中 Product Hunt 就因此归零过一次，
看起来像接口故障，实际只是窗口滑走了。自然日口径保证同一天的结果只增不减。

禁止在查询串中写死任何月份或年份：

1. 先取当天日期：`date +"%Y-%m-%d"`
2. 调用 WebSearch 时**必须**带上 `freshness: "d2"`（窗口最长接近 48 小时，d1 会漏掉前一天的条目）
3. 查询串内**不要**出现月份、年份、"today" 等时间词，交给 freshness 参数处理
4. 若检索工具不支持 freshness，退而在查询串末尾附加前一天与当天两个日期
5. 结果中无法确认发布时间的条目，发布时间字段写 `N/A`

### 第一步：运行抓取脚本（主路径）

国内外所有 feed 的抓取已固化在脚本里。**先跑脚本，再用 WebSearch 补充**：

```bash
# 默认：前一天 00:00:00 至今（日常使用这个）
python3 scripts/fetch_sources.py --out /tmp/collected.json

# 指定起始日（回溯补采）
python3 scripts/fetch_sources.py --since 2026-10-04 --out /tmp/collected.json
```

覆盖源：Hacker News（Algolia API）、GitHub Releases（Claude Code / Codex）、
Product Hunt、掘金、InfoQ中国、开源中国、美团技术。

输出 JSON 字段：`source` / `title` / `url` / `discussion_url` / `published_at` /
`heat` / `summary` / `lang` / `keywords(core, weak, biz, relevant, excluded)`，
以及 `window`（含 `from` / `to` / `mode` / `span_hours`）。

参数：
- `--since YYYY-MM-DD` 指定起始日，取其 00:00:00；不给则默认为昨天
- `--hours N` 退化为"最近 N 小时"滑动窗口，**仅调试用**，与 `--since` 互斥
- `--raw` 输出未过滤全量，用于排查漏采
- 单源失败自动重试 2 次，仍失败只告警不中断，其余源照常输出

两个已知的接口坑（脚本已内化处理，此处仅作说明，不要"改回"旧写法）：

- GitHub `releases.atom` 会间歇性 502 / 隧道失败，脚本已加 **GitHub API 兜底**路径
- Hacker News 的 `>` 必须 URL 编码为 `%3E`；Product Hunt 的 feed 返回 200 但结构是 Atom 不是 RSS

脚本只做初筛（强信号命中任一，或弱信号命中 ≥2 个），**仍需你判断**。
Hacker News 初筛后常有 40+ 条，必须按「低质信号」与定位约束再筛一轮。

### 第二步：WebSearch 补充

| 目标 | 查询串 |
|------|--------|
| 编程工具实战 | Claude Code OR Cursor OR Codex workflow tips |
| 提效与生产率 | vibe coding OR "AI coding" developer productivity |
| 工具版本更新 | Claude Code OR Cursor OR Copilot release update |
| Agent 工作流 | agentic coding OR "AI agent" harness workflow |
| 社区讨论 | Reddit r/ClaudeAI OR r/Cursor OR r/ChatGPTCoding |
| 新产品 | Product Hunt AI developer tools |
| Hacker News | Hacker News AI coding tool discussion |

每次搜索都要带 `freshness: "d2"`（覆盖前一天至今的跨天窗口）。查询串按上表原样提交，
不要把序号或说明文字一起提交。

**已知不可达**：reddit.com 与 old.reddit.com 均在网络层被拒；X/Twitter 无公开接口。
这两类源无法覆盖时如实标注为缺口，不要伪造内容。

## 收录门槛

采集结束时按以下门槛自检。未达标就补搜；补搜仍不足则如实说明缺口，不要凑数。

| 指标 | 门槛 |
|------|------|
| 总条数 | ≥ 8 条 |
| 来源类别 | 至少覆盖 3 个不同来源。可计入的类别：X、Hacker News、GitHub Releases、Product Hunt、掘金、InfoQ中国、开源中国、美团技术 |
| 国内条目 | ≥ 3 条（公众号读者以国内为主，国内源不可整体缺失） |
| 有效链接率 | 100%，无 URL 的条目不入库 |
| 窗口内占比 | 100%。窗口即硬边界，落窗外的条目一律剔除；无法确认发布时间的写 `N/A` |
| N/A 比例 | 热度字段允许，但 `published_at` 为 N/A 的条目不超过 40% |

## 低质信号（命中任一即丢弃）

- "Top 10 AI Tools" 类 SEO 聚合列表文
- 无原始出处的二手转述（声称"据报道"却给不出链接）
- 标题党、情绪化断言但无证据支撑
- 厂商软文、付费推广、affiliate 导流内容
- 内容农场批量生成的浅层文章
- 纯快讯：只转述"某产品发布了"，无任何增量信息
- 同一事件的多篇重复报道 —— 合并为一条，保留信息最全的来源
- 发布时间与来源均无法验证的条目

## 注意事项

- **必须提取原文链接**：每条热点都要有可点击的具体URL，无URL则丢弃
- **时效硬约束**：只保留落在时间窗口内（前一天 00:00:00 至今）的内容；
  确认早于起点的条目直接剔除，无法确认时间的写 `N/A` 并排在各类别末尾
- **同日重采要合并不要覆盖**：RSS 会挤出早期条目，直接覆盖会永久丢数据，
  按「落盘」章节的合并规则按 URL 去重后追加
- 不采集纯学术论文，除非它直接改变编程工作流
- 不采集底层大模型研发内容（训练、架构、推理引擎、AI安全）
- 不采集重复/相似内容，合并同类
- 标注内容语言（中/英），在要点后用 `[中]` 或 `[英]` 标注
- 优先采集有实操价值的内容（教程、技巧、工具、可复现的工作流）
- 热度字段取不到就写 `N/A`，禁止估算或填充
- 交付前自检：各类别条数、链接是否可达、是否存在 `N/A` 过多的类别，
  并在输出末尾用一行说明本轮采集的覆盖情况与缺口
