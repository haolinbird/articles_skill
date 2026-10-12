---
name: gzh-daily-pipeline
description: 调度公众号每日内容流水线（选题→写作→配图→排版→多平台→草稿箱同步），产出可直接发布的草稿与执行报告。无人值守模式支持自动选题、失败降级、断点续跑。触发场景：跑今日流水线、今日文章流水线、每日流水线、gzh-daily-pipeline，或要求一次性完成选题到草稿箱的全流程时。
---

# GZH Daily Pipeline - 公众号每日流水线总调度

> **定位**：调度器，不是执行器。只做编排，把多个外部 skill 串成一条流水线，不重复实现它们的逻辑。本 skill 只负责：定义产物交接契约、设置质量门、失败降级策略、断点续跑机制。
> **设计目标**：每天早上无人值守跑完，产出「可以直接点发布」的草稿箱内容 + 一份执行报告。

## 运行契约（一次性跑全流程 / 从某阶段续跑都走这一套）

- **输入**：无（自动选题）。也支持从任意阶段续跑 —— S0-2 会检查产物清单，从第一个缺失的阶段开始
- **产物**：见「二、产物清单」；执行报告写在 `articles/YYYYMMDD_pipeline_report.md`
- **幂等**：**S0-2 产物预检**保证不重复劳动，已存在的阶段直接跳过。
  拆篇场景下带 `_p1_` / `_p2_` 的项必须两篇都在才算该阶段完成
- **前置**：见「S0-1 环境预检」表逐项检查（日期 / markdown-it / wechatsync / Token / 配图 API / 配图技能），
  缺项只记入报告「人工待办」，**不阻断流水线**
  （调用子技能与单独运行子技能用的是**同一套契约**，见各子技能 SKILL.md 头部「运行契约」）

### 配置在哪改（只改一处，不要到处找）

| 想改什么 | 改哪里 |
|---|---|
| 启用 / 停用平台、平台同步参数 | `config/platforms.json`（项目根）的 `enabled` |
| 配图 API、字数门、日产量、Token | `config/pipeline.env`（项目根） |
| **作者人设**（必配）、受众口径 | `../gzh-write-enhanced/resources/author_voice.md` |
| **配图人物**（必配）、品牌标语 | `../gzh-write-enhanced/resources/author_visual_assets.md` |

---

## ⚙️ 使用前配置

### 1. 环境变量

全部集中在 `config/pipeline.env`（项目根），模板见 `config/pipeline.env.example`。
**脚本会自动向上查找并加载它**（`scripts/load_config.cjs`），**不需要手动 source**。

**真正必填的两项**：

| 变量 | 用途 | 缺了会怎样 |
|---|---|---|
| `GZH_T2I_API_KEY` | 正文配图（S4-1）的 API Key | S4 不产图，终稿降级为无图（不阻塞流水线） |
| `WECHATSYNC_TOKEN` | 分发令牌 | S6 无法同步（见 S6 第 1 步） |

其余项均有默认值或按需启用，说明见模板内注释；S4-0 开篇图用的是另一组变量，见 S4-0 章节。

### 路径基准（dev 写死 / 分发按需改写）

源码内两个绝对路径写死为本机目录（dev 阶段无需动）：

```
SKILL_DIR = /Users/haolin/WorkBuddy/AI编程公众号SKILL/skills/gzh-daily-pipeline
WORK_DIR  = /Users/haolin/WorkBuddy/AI编程公众号SKILL/articles
```

**两类引用的写法**：

- **Read 类**（`Read` 其他 SKILL.md）：相对路径 `../<skill>/SKILL.md`，`../` 即同级 `skills/`
- **Shell 类**（S6 阶段跑 `node scripts/*.cjs`）：cwd 切到 WORK_DIR 时相对路径会解析失败，必须用绝对路径

**分发到其他机器/目录时**：跑 `python3 scripts/package.py --install-root <新路径> --work-dir <新路径>`，
脚本会用锚点替换（`scripts/package.py:88` `rewrite_abs()`）改写上面两个绝对路径。**不要手工改 SKILL.md**。

### 依赖技能（同级 `skills/` 目录，可替换）

**本包不再内嵌任何环节 skill。** 所有环节都引用外层同级的 `skills/` 目录（即 `../<skill>`）：
每个环节既是可被流水线调用的组件，也是可独立触发、独立替换的完整技能。

| 阶段 | 依赖技能 | 必需 | 替代方案 |
|------|----------|------|----------|
| S0 预检 | （自包含：环境检查 + 加载 config/pipeline.env） | — | — |
| S1 选题 | `../topic-collector` + `../topic-generator` + `../topic-reviewer` | 必需 | 任何能产出「选题+评分+原文链接」的采集流程 |
| S2 写作 | `../gzh-write-enhanced` | 必需 | 任何写作 skill，产物含 A/B/C 三版 |
| S3 合并 | `../gzh-write-enhanced`（同 S2） | 必需 | 任何写作 skill，产物含 A+C 合并终稿 + 四层自检（硬性规则 / 风格一致性 / 内容质量 / 活人感） |
| S4 配图 | `ian-xiaohei-illustrations`（16:9 手绘风格） | **可选** | 任何配图 skill，产物为图片文件 |
| S4b 排版 | （自包含 `node scripts/gzh_format.cjs`） | 必需 | — |
| S5 多平台 | `../公众号文章转多平台` | 必需 | 按各平台风格自行改写（9 平台规则全在；**启用哪些由 `config/platforms.json` 决定**，见该 skill 〇节指针） |
| S6 分发 | （自包含，跑 npm 全局 `wechatsync`） | 必需 | 任何能同步到各平台草稿箱的工具 |
| S7 报告 | （自包含，按 SKILL.md 模板生成 `YYYYMMDD_pipeline_report.md`） | 必需 | — |

> **分发需打包**：直接复制本包会因找不到同级技能而失效，需运行
> `python3 scripts/package.py`（含 `ian-xiaohei-illustrations` 加 `--with-illustrations`），
> 它会把 5 个必需依赖 + 1 个可选依赖复制进包内 `skills/`，并把 `../<skill>/` 改写为 `./skills/<skill>/`，
> 产出自包含的 `dist/gzh-daily-pipeline/`。
> 日常开发只改外层 `skills/` 下的源文件，**不要改 dist 里的副本**（下次打包会被覆盖）。

---

## 一、总览

```
S0 预检（断点续跑判断）
 └─ S1 选题（采集 → 生成 → 审核，自动选 TOP1）
     └─ S2 写作（A/B/C 三版并行）
         └─ S3 合并（A+C 合并终稿 + 自检复检 + 备选标题）
             └─ S4 配图（每篇 {GZH_IMAGES_PER_ARTICLE} 张，⚙️ 值在 `config/pipeline.env`；开篇人设图可选，默认跳过）
                 └─ S4b 排版美化（终稿 → 公众号内联样式富文本）
                     └─ S5 多平台（多平台版本转换）
                         └─ S6 分发（Wechatsync 同步各平台草稿箱）
                             └─ S7 报告（执行报告：产物清单 + 同步结果 + 人工待办）
```

**方向说明（与「从公众号链接改写」的旧模式不同）**：本流水线是**先把终稿和配图写好（缺省就是公众号版），再转换成各平台版本**。S5 输入是本地终稿 + S4 生成的配图，**跳过「下载公众号图片」步骤**。

**产物命名**：一律 `YYYYMMDD_` 前缀（当天日期），YYYYMMDD 用当天真实日期（用 `date` 命令取，不要自己算）。

## 二、产物清单（交接契约）

| 阶段 | 产物文件 | 产生条件 |
|------|----------|----------|
| S1 | `YYYYMMDD_topics.md`（TOP3 备选 + 选定 TOP1 及理由） | 选题完成 |
| S2 | `YYYYMMDD_abc.md`（A/B/C 三版全文） | 三版写完 |
| S3 | `YYYYMMDD_final.md`（A+C 合并终稿，含备选标题） | 合并 + 复检通过 |
| S4 | `assets/YYYYMMDD-<主题>/NN-<slug>.jpg`（正文配图每篇 {GZH_IMAGES_PER_ARTICLE} 张，按篇分配）+ 各篇 md 已插入图片引用 | 配图完成并插回 |
| S4-0 | `YYYYMMDD_开篇图.png`（**可选**，插在固定问候语后） | 图片 API 已配置时才生成，否则跳过 |
| S4b | `YYYYMMDD_pN_final_gzh.md`（内联样式富文本，公众号专用） | 排版转换完成 |
| S5 | 各启用平台按 `config/platforms.json` 的 `output_files` 产出（如 `YYYYMMDD_pN_稀土掘金.md` + `_发布版.md`）<br>公众号产物见 S4b（不在本步重复产出）；**启用哪些平台以 json 的 `enabled` 为准，本节不列清单** | 多平台转换完 |
| S6 | Wechatsync 同步草稿箱：取 json 中 `enabled: true` **且** `wechatsync.supported: true` 的平台逐条同步 | 同步执行完 |
| S7 | `YYYYMMDD_pipeline_report.md` | 永远产出 |

**断点续跑规则**：S0 预检时逐项检查上表产物，已存在的阶段直接跳过（视为完成），从第一个缺失产物的阶段开始跑。这样失败重跑、手动补跑都不重复劳动。


## 三、全局设定（每个阶段都必须遵守）

### 受众定位

- **目标读者**：Read `../gzh-write-enhanced/resources/author_voice.md` 的「## 受众」段。
- 选题主线围绕该读者的真实痛点（能学到、能用到、能产生共鸣）；所有阶段（选题、写作、润色、配图）按此受众执行。

### 选题聚焦领域

Read `../gzh-write-enhanced/resources/author_voice.md` 的「## 文章赛道」段（赛道 + 优先 + 排除项）。

### 作者人设（写作与配图全程保持）

写作侧：Read `../gzh-write-enhanced/resources/author_voice.md` 的「## 我是谁 / 风格 DNA / 开篇与结语范式」段。
配图侧：Read `../gzh-write-enhanced/resources/author_visual_assets.md`。

> ⚠️ 本节**不复述**风格要求（如「大白话」「温暖正向」之类）。人设的完整定义在上述文件里，
> 在这里再写一遍就是第二份口径，改人设时必然漏改——**执行时以读到的文件为准**。

### 无人值守铁律

1. **全程禁止向用户提问**（AskUserQuestion 一律不用）。每个决策点按本 skill 的降级规则自动处理。
2. 每个阶段结束立即把产物写盘（落盘才算完成），再进入下一阶段。
3. 某阶段彻底失败：记录到报告的「失败项」，跳过该阶段继续后续阶段（如 S4 失败则终稿不带图继续 S5），**不许整条流水线中断**。
4. 时间数字、案例数据必须真实可查，禁止编造；引用热点必须带原文 URL。
5. 效率对比类数据（如「X 小时 → Y 分钟」）是幻觉高发区：**无实测数据就不写这类对比**，
   改用定性描述（「明显更快」「省了大半天」），不得估算或凑整。

## 四、各阶段执行手册

### S0 预检（必须执行，决定从哪一步开始）

#### S0-1 环境预检（逐项检查，缺失项记入报告「人工待办」，不阻断流水线）

| # | 检查项 | 怎么查 | 缺失时的后果 |
|---|--------|--------|--------------|
| 1 | 日期 | `date +%Y%m%d` | — |
| 2 | 排版依赖 | `ls /Users/haolin/.workbuddy/binaries/node/workspace/node_modules/markdown-it` 有输出 | S4b 排版脚本直接报错跑不起来 |
| 3 | Wechatsync | `which wechatsync` 有输出，且 `config/pipeline.env` 里 `WECHATSYNC_TOKEN` 非空 | S6 无法分发 |
| 4 | 图片 API（可选） | `config/pipeline.env` 里 `GZH_IMAGE_API_KEY` 与 `GZH_IMAGE_BASE_URL` 均非空 | S4-0 开篇人设图自动跳过（**当前为空，默认跳过**） |
| 5 | 配图技能 | `~/.workbuddy/skills/ian-xiaohei-illustrations` 存在（符号链接也算） | S4 正文配图降级，终稿不带图继续 |
| 6 | Chrome 扩展 | 只能到 S6 才验证；此处仅记录「S6 需先唤醒扩展」，见 S6 FAQ | S6 首次同步大概率超时 |

检查结果写成一张表放进 S7 报告，便于回溯「某次失败是因为哪个环境项缺了」。

#### S0-1b 读入运行配置（后续所有阶段共用，只读这一次）

**开跑前先从 `config/pipeline.env`（项目根）读入以下值**，后面各阶段一律使用**这里读入的实际值**：

| 变量 | 用途 | 用在哪 |
|---|---|---|
| `GZH_WORD_MIN` / `GZH_WORD_MAX` | 单篇字数下限 / 上限 | S2 篇幅、S3 字数门与拆篇判定 |
| `GZH_IMAGES_PER_ARTICLE` | 每篇正文配图张数 | S4-1 |
| `GZH_MAX_ARTICLES_PER_DAY` | 每日产出篇数硬上限 | S3 拆篇上限 |

> ⚠️ 本文件所有 `{GZH_XXX}` 均为**占位符，不是默认值**，执行时用上表读入的实际数字替换。
> 脚本侧同理（`load_config.cjs` 自动加载同一文件），两边同指向 `config/` —— 这就是改配置只需改一处的原因。

#### S0-2 产物预检（断点续跑）

按「产物清单」逐项检查 `/Users/haolin/WorkBuddy/AI编程公众号SKILL/articles` 下文件是否已存在：

- **已存在的阶段直接跳过**，视为完成，不重复劳动；
- 从**第一个缺失产物的阶段**开始跑。

拆篇场景注意：若终稿字数超标要拆上下篇（见 S3），产物清单里带 `_p1_` / `_p2_` 的项
必须**两篇都存在**才算该阶段完成，只有一篇则从该阶段补跑缺失的那篇。

#### S0-3 决策

- 全部产物已存在 → 只跑 S7 生成报告；
- 部分存在 → 从缺失处续跑；
- 全不存在 → 从 S1 开始全新跑。

报告里必须注明本次是「全新跑」还是「续跑到第 X 阶段」。

### S1 选题（自动，无人工确认）

1. **Read** `../topic-collector/SKILL.md`，按其执行热点采集：先跑 `../topic-collector/scripts/fetch_sources.py`（默认自然日窗口，直取国内外 9 个 feed），WebSearch 仅作补充。聚焦 `author_voice.md` 「## 文章赛道」段定义的领域。
2. **Read** `../topic-generator/SKILL.md`，从热点中生成 TOP10 选题（事件描述、核心角度、3 个备选标题、写作方式、预估热度）。
3. **Read** `../topic-reviewer/SKILL.md`，逐个审核评分。
   **评分维度、权重与通过线一律以该文件的「评分项」表为准**——本节刻意不复制清单：
   复制一份就会与实际执行的评分表脱节（2026-10-09 修复：此处曾写「读者适配」这个并不存在的维度，
   且漏掉「受众匹配」）。
4. **自动决策**：取评分最高的选题为 TOP1 直接进入写作；把 TOP3（含各自评分、理由、原文链接）写入 `YYYYMMDD_topics.md`。
5. **落盘口径（易错）**：`topic-collector` 把**原始热点**写到工作区根 `topics/YYYY-MM-DD.md`（40+ 条素材）；本步的 `YYYYMMDD_topics.md` 是 **TOP3 选题方案**，写在 WORK_DIR。**两者不是同一个文件**，不要用前者顶替后者，也不要改 collector 的落盘路径。
6. **降级规则**：若所有选题 < 70 分（如当天无热点），从 `author_voice.md`「## 文章赛道」段里挑一个常青选题，并在 topics 文件里标注「常青备胎选题」。
7. 选题一旦确定，正文标题从该选题的 3 个备选标题里选最有冲突感的一个。

### S2 写作（三版并行）

1. **Read** `../gzh-write-enhanced/SKILL.md` 及其 `resources/` 下的 A/B/C 三个模板（人设类配置已下沉到 `resources/author_voice.md`，模板内 prompt 按其明确描述取值）。
2. 以 `YYYYMMDD_topics.md` 的 TOP1 选题为输入，分别产出 **A 版（反直觉洞察）/ B 版（观点分析）/ C 版（实操教程）**。
   篇幅按 S0-1b 读入的 `{GZH_WORD_MAX}` 写，**不要主动写超**——写超会在 S3 触发拆篇，
   而拆篇是超标时的异常处理，不是常规流程。
3. 三版通用六条硬规则（建议）：**结果前置**（先给结果/案例/数据再讲方法）、
   **金句锚点**（每篇 ≥1 句可截图传播的金句）、**诚实坦白**（每篇承认 1-2 个不足或局限）、
   **口语化转场词**（自然穿插 2–4 处，宁少勿假，≥6 处机械堆叠判 AI 味）、**往期导流**（结尾放 2-3 篇往期文章）、**软转化结尾**（不硬推不卖课）。
4. 全部产物写入 `YYYYMMDD_abc.md`。
5. 质量门：三版各自过一遍去 AI 味硬性检查（禁用词、标点），不过先自动修复再落盘。
6. **口吻门（强制）**：写作前先确认人设归属——`../gzh-write-enhanced/resources/author_voice.md`
   **已配置，且优先级最高**，覆盖 `xiaohu_style_dna.md` / `xiaohu_narrative_voice.md` 两份第三方人设。
   三版叙事口吻必须与 `author_voice.md` 一致（结构可分工、口吻不串味），交稿前过口吻自检。
   ⚠️ 若该文件缺失而回退到小虎人设，**必须在产物头部标注「本次采用第三方小虎口吻，非本人口吻」**，
   否则会静默产出面向中小企业老板的文章。

7. **真人语料校准（自动）**：写作技能会在动笔前自动扫描项目根 `wechat_exports/`（`scripts/voice_sample_index.py`）。
   若目录有你本人历史文章，按当前选题相关度推荐 1–3 篇，AI 先全文读取校准自然语感再写；
   目录为空则打印 `NO_SAMPLES` 自动跳过，退回 `author_voice.md` 单基准（不报错）。
   此步由 `gzh-write-enhanced` 内部处理，调度器无需额外操作，但 S7 报告应如实标注是否启用语料校准。

### S3 合并终稿

1. 将 **A 版**和 **C 版**合并为一篇终稿（保留 A 的洞见冲击 + C 的干货密度，自然过渡不是拼接）。
2. 合并稿再过一遍完整自检（建议四层：硬性规则→风格一致性→内容质量→活人感）。
3. 生成 40 个备选标题（8 类风格 × 5），放文件最开头。
4. 加粗 ≤ 全文 5%；口语化转场词自然穿插（2–4 处即可，不硬凑，≥6 处机械堆叠判 AI 味）；全文保持 `author_voice.md` 定义的写作口吻。
5. **⭐ 字数门 + 自动拆篇**（跳过会产出超规范近一倍的稿子，必须执行）：

   - **统计口径**：纯正文 = 剔除代码块、再剔除 `![](...)` 图片引用行后的字符数。
     顺序不能反，也**不能只剔代码块**——6 条图片路径会被算进字数，虚高约 600 字。
   - 单篇字数区间 = S0-1b 读入的 `{GZH_WORD_MIN}`–`{GZH_WORD_MAX}`（⚙️ 唯一定义在 `config/pipeline.env`）。
   - **≤ `{GZH_WORD_MAX}`** → 单篇发布，不拆。
   - **> `{GZH_WORD_MAX}`** → **拆上下两篇**，不要硬删核心段落（砍干货或洞见都不划算）：
     - 上篇（07:30 推送）= 概念 / 判断 / 类比 / 降温段 + 今天能动手的一件事
     - 下篇（15:00 推送）= 能直接抄的操作步骤 / 命令 / 模板 / 判据
     - 产物 `YYYYMMDD_p1_concept.md`、`YYYYMMDD_p2_practice.md`，**各篇都要落在 `{GZH_WORD_MIN}`–`{GZH_WORD_MAX}` 区间内**
     - 两篇各写承接句（上篇末尾预告下篇、下篇开头回指上篇），各有独立来源表
     - 配图按篇重新分配，上下篇不得串用（见 S4-1 第 4 条）
   - **🚨 每日产出硬上限 = `{GZH_MAX_ARTICLES_PER_DAY}` 篇**（⚙️ `config/pipeline.env`）。
     拆篇**只能拆成上下两篇**，禁止拆出第三篇。若拆完某篇仍超 `{GZH_WORD_MAX}`，
     **压缩表述**（合并同类论证、删冗余修饰与重复举例），
     ——不得删除数据、判据、来源表等核心内容，也不得为此新增一篇。
   - 拆完两篇**各跑一次四层自检**（禁用词 / 标点 / 加粗 / 口语化），单篇也要达标（口语化自然穿插，不机械堆叠）。
   - 原 `YYYYMMDD_final.md` 保留为合并态存档，头部标注「已拆分，勿直接发布」。
   - **后续所有阶段（S4b / S5 / S6）都按篇跑**，文件名带 `_p1_` / `_p2_`。

6. 落盘 `YYYYMMDD_final.md`（若拆篇则另落 `_p1_concept.md` / `_p2_practice.md`）。

### S4 配图（正文配图为主，开篇人设图可选）

> **产物目录（2026-10-07 修正）**：配图**不放** WORK_DIR，统一放项目根
> `assets/YYYYMMDD-<主题>/`，命名 `NN-<slug>.jpg`（NN 为两位序号）。
> md 在 `articles/` 下，引用写作 `../assets/YYYYMMDD-<主题>/NN-<slug>.jpg`。
> 旧口径 `YYYYMMDD_图N.png`（放在 articles 下）已作废，勿再使用。

#### S4-0 开篇人设图（⚠️ 可选，当前默认跳过）

**前置条件**：`config/pipeline.env` 的 `GZH_IMAGE_API_KEY` + `GZH_IMAGE_BASE_URL`。
**两项当前均为空 → 脚本 `exit 2` → 自动跳过，终稿不插图，不阻塞流水线**
（S0-1 第 4 项在开跑前就会报出来，不用等跑到 S4 才发现）。
按模板填好密钥后本环节才会真正执行；脚本另读两个可选 env：`GZH_OPENER_PERSONA` / `GZH_OPENER_SLOGAN`。

1. **取参**：从 `YYYYMMDD_topics.md` 选定选题里取核心观点名词（2~10 字）作 `{KW}`；
   **Read** `../gzh-write-enhanced/resources/author_visual_assets.md`，取「## 配图人物」的 `OPENER_PERSONA`
   与「## 品牌标语」的 `OPENER_SLOGAN`（**禁止写字面占位符**）。
2. **生成**（提示词模板已固化在脚本内；双引号包裹的文字 gpt-image 系列会保证出现在图里）：

```bash
# API 配置读 config/pipeline.env，也可用 --api-key/--base-url 覆盖
node /Users/haolin/WorkBuddy/AI编程公众号SKILL/skills/gzh-daily-pipeline/scripts/gzh_opener.cjs \
  --keyword "{KW}" --persona "<OPENER_PERSONA>" --slogan "<OPENER_SLOGAN>" \
  --out /Users/haolin/WorkBuddy/AI编程公众号SKILL/articles/YYYYMMDD_开篇图.png
```

模板原文：`"{KW}"，插画风格，可爱的{OPENER_PERSONA}在笔记本电脑前，绿色养眼背景，关键词文字放大作为背景显示，画面下方中间是小字"{OPENER_SLOGAN}"，文字不要太靠近上下的边缘，横版构图`

3. **插入终稿**：插在开篇问候段（见 `author_voice.md`「## 开篇与结语范式 → 开篇问候」）的下一行；该段不存在则插第一段之后。
4. **降级**：退出码 2 → 跳过并记一条「人工待办」，**不要用正文配图工具顶替**（两者风格不同，混用会让开篇图与后文割裂）。
5. **自检**：关键词大字无错字、口号小字在下方、人物形象符合视觉资产文件。错字重试 1 次，仍错改用备用通道。

#### S4-1 正文配图（核心环节，不可省）

1. 配图 skill 默认推荐 ian-xiaohei-illustrations（16:9 手绘风，第三方，WorkBuddy skillhub 搜索「小黑插画配图」安装；或替换为你自己的配图 skill）。安装后 **Read** 其 SKILL.md 及 references。
2. 通读终稿，挑认知锚点（核心判断 / 前后对比 / 分流闭环 / 常见坑 / 落地顺序等），**先出 shot list 再逐张生成**。
   **每篇固定 `{GZH_IMAGES_PER_ARTICLE}` 张**（⚙️ 唯一定义在 `config/pipeline.env`；
   拆篇时按篇计算：总张数 = 篇数 × 该值）。
   挑锚点时只保留**最值得配图的前 2 个**，宁精不滥——图多了读者滑得快，反而稀释正文。
3. 风格要求由配图 skill 自带；通用约束：16:9 横版、每张只讲一个核心结构、禁止 PPT 风和左上角标题。
   ⚠️ **prompt 末尾固定追加**：「画面右下角必须保持纯白空白，不要画任何东西」——
   智谱通道的水印遮盖依赖右下角留白，画面元素伸进该区域会被遮盖矩形切断。
4. **拆篇场景按篇独立出 shot list**，上下篇配图**不得串用**（上篇 01/02/03/04/06，下篇 05/07 那类分配写进 shot list 里）。
5. 逐张生成，保存为 `assets/YYYYMMDD-<主题>/NN-<slug>.png`。
5b. **生成后立即遮水印**（智谱通道必做；脚本自动读 `GZH_COVER_WATERMARK` 开关，
   百炼等无水印通道开关为 false 时原样跳过，所以**无条件执行也安全**）：
   ```bash
   python3 <带 Pillow 的解释器> ../scripts/cover_watermark.py assets/YYYYMMDD-<主题>/*.png
   ```
   遮盖区域固定在右下角（按比例适配分辨率）。需解释器已安装 Pillow。
6. **⭐ 必须压缩后再用**（2026-10-07 实测，跳过此步会导致 S6 图片全部上传失败）：
   1536×1024 的 PNG 单张 1.5–1.9 MB，同步时**5 张全部失败**；压到 1080 宽 JPEG（150–250 KB）后 **100% 成功**。
   ```bash
   cd assets/YYYYMMDD-<主题>
   mkdir -p _original && cp *.png _original/          # 原图留档，别只放 /tmp
   for f in *.png; do
     sips -s format jpeg -s formatOptions 88 --resampleWidth 1080 "$f" --out "${f%.png}.jpg"
   done
   ```
   然后**批量把各 md 里的 `.png` 引用改成 `.jpg`**（2026-10-07 一次改了 43 处），改完跑一次引用校验：
   所有 `../assets/...` 路径必须存在，缺失即打回。
7. 按配图 skill 的自检规则检查，不合格的重生成（单张最多重试 2 次，仍不合格就换构图角度再来 1 次，再不行标记失败继续走）。
   ⚠️ 智谱 CogView-4 中文错字率高（2026-10-10 实测约半数写错，中英混合词最差）——
   自检时**逐字核对**画面里的中文，发现错字/漏字直接重试；重试 2 次仍错，可把
   「手写风格」改成「清晰印刷体汉字」再试一次（印刷体准确率明显高于手写体）。
8. 把图插入对应段落位置（`![](../assets/YYYYMMDD-<主题>/NN-<slug>.jpg)`），更新落盘。

### S4b 排版美化（公众号专用，不能省）

1. 运行排版转换脚本（公众号编辑器只认内联样式，素 Markdown 直接同步会丢排版）：

```bash
export NODE_PATH=/Users/haolin/.workbuddy/binaries/node/workspace/node_modules
node /Users/haolin/WorkBuddy/AI编程公众号SKILL/skills/gzh-daily-pipeline/scripts/gzh_format.cjs \
  /Users/haolin/WorkBuddy/AI编程公众号SKILL/articles/YYYYMMDD_pN_concept.md \
  --theme warm --title "文章标题" \
  --out /Users/haolin/WorkBuddy/AI编程公众号SKILL/articles/YYYYMMDD_pN_final_gzh.md
```

2. **先抽干净正文再排版**（直接喂终稿会把「40 个备选标题」「本篇自检」「待人工确认」一起排进去，这些不能发）。
   ⚠️ **必须用脚本抽，不要手工截**——手工按「h1 到本篇自检之前」截取会把开头那段 40 个备选标题整段带进去
   （2026-10-12 实测踩过）。脚本已内置防呆：先剥离代码块再定位标题，代码块里 `# target.py` 这类注释行不会误判。
   ```bash
   python3 /Users/haolin/WorkBuddy/AI编程公众号SKILL/skills/gzh-daily-pipeline/scripts/extract_clean.py \
     /Users/haolin/WorkBuddy/AI编程公众号SKILL/articles/YYYYMMDD_pN_final.md --expect-images <S4 张数>
   ```
   输出 `YYYYMMDD_pN_clean.md`；脚本自带自检（标题区/自检区残留、来源表缺失、图片数不符均 exit 1），
   **exit 非 0 就先修再排版**，不要绕过。终稿拆了上下篇就各跑一次（`_p1_` / `_p2_`，输出 `YYYYMMDD_p1_final_gzh.md`、`YYYYMMDD_p2_final_gzh.md`）。
3. 标题从备选标题里取 TOP1 传给 `--title`（同步命令也用它）。
4. 主题三选一：`warm`（默认，暖橙）/ `tech`（科技蓝）/ `mono`（极简黑白）。主题色可在脚本 `THEMES` 对象里改。
5. 脚本自动处理：剥离第一个 h1（标题单独填发布框）、金句引用块转金句卡、图注转居中灰字、图片行回填为 HTML `<img src="本地路径">` 标签（**不能回填 markdown `![]()` 语法**——公众号渲染器把排版版整体当 HTML 处理，markdown 图片语法会原样显示成网址文字；HTML img 的本地路径同样能被 Wechatsync 识别上传并替换为其 CDN 地址）。
6. 自检输出文件：`<section>` 包裹完整、图都在且全部是 `<img src=` 形式（张数与 S4 分配一致；出现 `![](` 即打回重排版）、无占位符残留（`{{GZH_IMG_`）。发现问题先看脚本报错，再降级为直接同步素 md 版（排版降级，不阻塞流水线）。

### S5 多平台转换

> **启用平台由 `config/platforms.json`（项目根）决定，本节刻意不含平台清单。**

1. **先 Read** `/Users/haolin/WorkBuddy/AI编程公众号SKILL/config/platforms.json` 得到 `enabled: true` 的平台列表，
   再 **Read** `../公众号文章转多平台/SKILL.md`，**只执行这些启用的平台**
   （各平台规则段落见 json 的 `rules_section` 字段）。
   未启用平台：不产出对应 md、不生成小红书图、不跑 `md_to_plain.py`。
   产出文件名、同步入参一律以 json 的 `output_files` / `wechatsync.sync_input` 为准，不要照抄本文件。
2. **输入**：本地终稿 + S4 生成的配图。**跳过「WebFetch 公众号 URL + 下载原文图片」步骤**（图片已由 S4 预生成，按原文位置插入，不堆文末）。
   - **若终稿已拆为上下两篇**（字数超标时的默认做法），按篇独立转换，文件加 `_p1_` / `_p2_` 前缀；
     未拆篇则去掉 `_pN` 段。每个启用平台按 json 的 `output_files` 逐篇产出。
     **公众号由 S4b 排版产出 `final_gzh.md`，S5 不重复产出**（json 里 `produces_md_here: false`）。
   - 配图按篇分配，不得串篇混用（以 S4 实际分配为准）。
3. 核心约束：只换风格不删减内容、严禁杜撰、图片张数与位置一一对应。
4. **S5b 原生 Markdown 版（对所有「非公众号」的启用平台都不能省）**：这些平台用原生 Markdown 渲染，
   **禁止喂 S4b 的内联样式版**（内联 HTML 会被部分剥离、样式残留很丑）。
   产出 `YYYYMMDD_pN_<平台>_发布版.md` = 该平台 frontmatter + 原生 Markdown 正文，
   字段见 `../公众号文章转多平台/SKILL.md` 对应平台的发布字段章节（章节名见 json 的 `rules_section`）。
5. 交付前跑一次图片引用校验：所有 md 里 `](../assets/...)` 的路径必须存在（缺失即打回）。

### S6 分发（Wechatsync 同步草稿箱）

1. **环境预检**：
   - **包名是 `@wechatsync/cli`，不是 `wechatsync`**（后者在 npm 已 404）：`npm install -g @wechatsync/cli`，命令 `wechatsync`。
   - **本机已装 v1.0.0**（不是 v1.1.0）：预检 `which wechatsync` 有输出即可，无需重装。
     版本号以 `wechatsync --version` 实测为准，别照抄文档——此前文档误记为 v1.1.0 已更正（2026-10-12）。
   - 扩展 ID（唤醒时要用到）：`hchobocdmclopcbnibdnoafilagadion`（中文名「文章同步助手」）。
   - **需要 Token**（旧版走 WebSocket 免 Token，新版已改）：在 Chrome 扩展设置里启用 MCP 连接拿到 Token。
     Token 存放在**项目根的 `config/pipeline.env`**（含密钥，切勿提交）。CLI 只读环境变量、不支持配置文件，
     因此**每个新 shell 执行同步前必须先加载**：
     ```bash
     set -a; source /Users/haolin/WorkBuddy/AI编程公众号SKILL/config/pipeline.env; set +a
     ```
     > 不要依赖 `~/.zshrc` 里的 export——实测在非交互 shell 中不会自动加载，会导致 `Invalid or missing token`。
   - 前置条件：**Chrome 正在运行 + Wechatsync 扩展已启用 + 目标平台已登录**。
   - 预检命令：`wechatsync auth`（检查各平台登录状态）；Chrome 未运行或 Token 缺失时同步步骤跳过、报告记人工待办。
   - 可用 `--dry-run` 验证命令拼装不实际同步。
2. **cwd 必须是 `/Users/haolin/WorkBuddy/AI编程公众号SKILL/articles`**（图片相对路径解析依赖）。
3. **扩展唤醒（必做，漏了必然超时）**：CLI 在 `localhost:9527` 起 WebSocket 服务，**被动等 Chrome 扩展连入**。
   Chrome MV3 的 service worker 会休眠，休眠期间 CLI 空等到超时，并**误报「需要安装 Chrome 扩展」**（不是真没装）。
   唤醒方式（macOS `open` 打不开 `chrome-extension://`，报 -10820/-10814；AppleScript 常缺自动化权限 -10004）：
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     "chrome-extension://hchobocdmclopcbnibdnoafilagadion/src/popup/index.html" &
   sleep 5
   ```
   验证：日志出现 `✔ Chrome Extension 已连接`，或 `lsof -i :9527` 看到 ESTABLISHED。
4. **图片压缩已在 S4-1 第 6 步完成**（压到 1080 宽 JPEG），此处**只校验、不重复压缩**：
   确认各 md 里 `../assets/YYYYMMDD-<主题>/NN-<slug>.jpg` 引用的文件真实存在，缺失即打回 S4 补压。
   ⚠️ 未压缩的 PNG（1.5 MB+）同步时**100% 上传失败**——若发现 md 里还有 `.png` 引用，
   说明 S4-1 的压缩步骤被跳过了，回到 S4-1 第 6 步处理，不要在这里临时补救。
5. **同步前刷新平台 token**：公众号后台 csrf token 易失效，直接 sync 会报 `错误码 200040`（invalid csrf token）。
   固定套路：**先开后台首页 → 跑一次 auth → 再 sync**（下面以公众号为例，**其他平台把首页与参数替换成
   json 里该平台的 `wechatsync.home_url` 与 `wechatsync.param`**）：
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN" &
   wechatsync --timeout 90000  auth weixin
   wechatsync --timeout 150000 sync "<文件绝对路径>" -p weixin -t "<标题>" \
     --cover "../assets/YYYYMMDD-xxx/07-xxx.jpg"
   ```
   公众号建议带 `--cover`（json 里 `wechatsync.cover: true` 的都要带）；非公众号平台**只喂原生 Markdown 版，不可喂内联样式版**。
6. **日志必须过滤 base64**：图片上传失败时错误信息会把整图 base64 打出来（单条几百 KB），直接读会爆上下文：
   ```bash
   sed -E 's/(data:image\/[a-z]+;base64,)[A-Za-z0-9+\/={}]+/\1<BASE64省略>/g' /tmp/sync.log
   ```
7. **按 `config/platforms.json` 现场生成执行清单**（本节不硬编码平台行）：

   取 `enabled: true` **且** `wechatsync.supported: true` 的平台，按 json 里各平台的
   `wechatsync.param` / `wechatsync.sync_input` / `wechatsync.home_url` / `strategy` / `special`
   逐条执行，顺序取 json 中 `platforms` 数组的先后。
   `wechatsync.supported: false` 的平台（小红书 / 知识星球 / 口播文案）**不进 S6**，列为人工待办。

   **执行时的通用坑（与启用哪些平台无关，每次必读）**：

   - 公众号降级链：失败重试 1 次 → 降级喂素 `YYYYMMDD_pN_concept.md` 再试 1 次 → 仍失败列人工待办
     （重试前先做扩展唤醒，见下方 FAQ）；公众号建议带 `--cover`。
   - 非公众号平台**一律禁止喂** `final_gzh.md` 内联样式版（HTML 会被剥离、代码块和表格易坏）。
   - 每个平台同步前都按第 5 步刷新 token：先开该平台的 `wechatsync.home_url` 首页 → `auth <id>` → `sync`。
   - 单平台失败只重试 1 次，仍失败就记录跳过，不阻塞其他平台。

> ⚠️ 未启用的平台**即使已登录也不执行同步**，产物也不生成。
> **启用 / 停用只改 json 的 `enabled`，本节无需再改。**

- 登录状态是**运行时数据，不写死在文档里**：**每次跑 S6 前先执行 `wechatsync auth` 复核**，
  不要照抄任何历史结论。本文件刻意**不记录**「某日已登录哪些平台」——这类信息会过期，
  且容易与 `config/platforms.json` 的启用状态混淆（已登录 ≠ 已启用，两回事）。

> 注 1：平台代码（`-p` 参数）取 `config/platforms.json` 的 `wechatsync.param`，
> 以 `wechatsync platforms` 实际输出为准，不同版本可能略有差异。
> 注 2：⚠️ 区分两种「OK」：`auth` 显示已登录 ≠ 同步能成功。公众号 auth 能过，
> 但同步时仍可能报 `200040`（csrf 失效），必须按第 5 步刷新。

8. 每个平台同步结果（成功/失败/跳过 + 草稿链接或报错摘要）记入同步结果表，供 S7 使用。

### S7 执行报告

写 `YYYYMMDD_pipeline_report.md`，模板：

```markdown
# 今日流水线执行报告 YYYYMMDD

## 一句话结论
终稿《XXX》已同步 N 个平台草稿箱，M 项待人工处理。

## 选题
- 选定：《XXX》（评分 XX/100）
- 备选：② XXX（XX分）③ XXX（XX分）
- 选题来源：<热点URL 或 常青备胎>

## 产物清单
- 终稿：YYYYMMDD_final.md（字数 XXXX，配图 N 张 = {GZH_IMAGES_PER_ARTICLE} × 篇数）
- 多平台：平台文件清单（列出实际产出）

## 去 AI 味校准
- 真人语料：`wechat_exports/` → 启用 N 篇 / 未启用（目录为空，退回 author_voice.md 单基准）
- 校准方式：<动笔前 Read 了哪几篇历史文章做语感对齐，或「未启用」>

## 同步结果
| 平台 | 结果 | 备注 |
|------|------|------|
| 公众号 | ✅/❌ | 草稿链接 |
| ... | | |

> 表格按 `config/platforms.json` 里本次实际同步的平台逐行填（`enabled: true` 且 `wechatsync.supported: true`），
> 不要照抄上面的示例行。

## 人工待办（预计 X 分钟）
1. 打开各平台草稿箱过目 → 点发布
2. （如有）失败平台重试

## 失败项与降级记录
（无则写「无」）
```

---

## 五、常见问题

**Q：手动触发时说「选题我来定」，给一个题目让我写？**
A：进入半自动模式：跳过 S1，用户给的题目直接当 TOP1 写入 topics 文件，S2 起照常。其余流程不变。

**Q：只想跑到某一步？**
A：按产物清单断点续跑天然支持，比如只补配图，就删掉/不放图文件后触发，S0 会定位到 S4。

**Q：想调整公众号排版风格？**
A：三套主题在 `scripts/gzh_format.cjs` 的 `THEMES` 对象里，改颜色值即可（primary=强调色，accent=金句卡底色）。想加新主题就照现有结构加一组。改完用 `scripts/test_sample.md` 自测：`node gzh_format.cjs test_sample.md --theme warm`。

**Q：公众号草稿箱里排版没生效（变素文本）？**
A：说明 Wechatsync 的渲染器吞了内联样式 HTML 块。降级顺序：① 素 md 同步保底先入库；② 在公众号编辑器里选一个官方样式模板套用；③ 长期方案是用 playwright RPA 直接往公众号后台贴富文本。

**Q：开篇图 API 报错？**
A：检查 `config/pipeline.env` 的 `GZH_IMAGE_BASE_URL` / `GZH_IMAGE_API_KEY` 是否有效（任何 OpenAI images 兼容端点均可，推荐 gpt-image 系列，中文文字渲染可靠）。

**Q：同步报连接/扩展相关错误？**
A：CLI 依赖 Chrome 运行 + Wechatsync 扩展在线（WebSocket 连接）。
**⚠️ 旧结论「无需 Token」已作废** —— `@wechatsync/cli` 必须提供 `WECHATSYNC_TOKEN`
（本机 v1.0.0 实测即需要，属该 CLI 的现行要求，与具体版本号无关）
（存在 `config/pipeline.env`），每个新 shell 要先 `set -a; source <项目根>/config/pipeline.env; set +a`。
排查顺序：先确认 Token 已加载 → `wechatsync auth` 预检 → Chrome 没开或扩展休眠就先唤醒
（见下一条），仍失败再列人工待办，不阻塞报告产出。

**Q：Chrome 明明开着，扩展却一直连不上（报 Extension 未连接 / 登录态超时）？**
A：这是浏览器扩展（MV3）的常见毛病——后台 service worker 休眠后不会自己醒来重连本地桥接。**先请用户点一下浏览器右上角的扩展图标（让弹窗弹出即可）唤醒它，然后重试同步**；唤醒后仍失败才排查平台登录态是否过期。实测唤醒后一次就能推成功，不要一上来就判登录态失效。

---

## 六、免责声明

- 本工具产出内容前请自行核实事实与数据，**发布行为及内容合规性由使用者自行负责**。
- 自动同步到各平台请遵守对应平台的服务协议与发布规则，控制发布频率，勿用于垃圾内容分发。
- 图片生成 API、各平台账号由使用者自备。
