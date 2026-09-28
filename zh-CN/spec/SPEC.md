> 中文版。英文原文：[spec/SPEC.md](../../spec/SPEC.md)

# thesis-ci 格式规范 v0.2

本规范定义“论点即代码”的文件格式。规范文本以 CC BY 4.0 许可发布；实现代码以 MIT 许可发布。
规范中的“必须 / 不得 / 应当”按 RFC 2119 理解。机器可读的定义以 `spec/schemas/*.schema.json`、`spec/checks.yml`、`spec/metrics.yml` 和 `spec/templates/lynch/*.yml` 为准；本文件与它们冲突时，以机器可读文件为准。

文中的“00 §X”指档案所遵循的系列规则（提示词 00）的条款，例如 §H4（公私分离）、§G7（先写下，后验证）。

## 1. 仓库角色

| 角色 | 标记 | 说明 |
| --- | --- | --- |
| 公开档案仓库 | `repo.yml` 中 `visibility: public` | 宪法、方法、thesis.yml、两分钟故事、预注册、预测、账本、季度更新、股东信 |
| 私有档案仓库 | `repo.yml` 中 `visibility: private` | 价值区间、L3 备忘录、升级请求、系列排名、带金额的决策日志、完整报告、提示词 |

每个档案仓库根目录必须有 `repo.yml`：

```yaml
visibility: public          # public | private
owner: kentian742-creator
spec_version: "0.2"
profiles: [core]            # 可选：运行哪些检查组（8.6）；不写则运行全部检查组
```

`thesis-ci lint <path>` 读取 `repo.yml` 决定适用哪些检查（见 `spec/checks.yml` 的 `scope` 与 `profile`）。迁移期内 `spec_version: "0.1"` 仍被接受，但 `C-SCHEMA` 报警告；档案按本规范迁移完成后改为 `"0.2"`。

## 2. 目录约定

```text
companies/<TICKER>/thesis.yml     # 公开；论点与 thesis tests
companies/<TICKER>/story.md       # 公开；两分钟持有理由
companies/<TICKER>/sources.yml    # 公开；来源标签表
companies/<TICKER>/prereg/        # 公开；预注册，每个业绩事件一组文件（2.1）
companies/<TICKER>/ledger.yml     # 公开；言行账本（可为空列表）
companies/<TICKER>/updates/       # 公开；每次更新的记录（Markdown，front matter 含 reviewed_sections）
industries/<id>/industry.yml      # 公开；行业模块与路标
industries/<id>/README.md         # 公开；行业模块摘要
industries/<id>/sources.yml
forecasts/<YYYY>.yml              # 公开；系统预测与你的覆盖
letters/<YYYY-MM>.md              # 公开；月度股东信
mistakes.md                       # 公开；错误清单（00 §G5）
constitution/rules.yml            # 公开；宪法规则与对应检查
constitution/decision-rights.yml  # 公开；三级决策权、信任等级与分流
agents/<role>.yml                 # 公开；角色定义（可见范围）
trust/levels.yml                  # 公开，可选；流水线算出的信任等级（4.2）
sources.yml                       # 可选；仓库级来源标签表
zh-CN/<路径>                      # 关键文档的中文版（8.5）

# 私有仓库
companies/<TICKER>/valuation.yml  # 价值区间、折现率、隐含回报（第 7 节）
companies/<TICKER>/sources.yml
memos/<YYYY-MM-DD>-<TICKER>-<slug>.yml        # L3 备忘录（总部起草）
escalations/<YYYY-MM-DD>-<TICKER>-<slug>.yml  # 升级请求（公司经理起草，交总部）
hq/ranking.yml                    # 系列排名（00 §V13）
decision-log/<YYYY>.yml
prompts/<编号>-<名称>.md          # 提示词；front matter 声明各部分的角色与输入（8.3）
```

文件名到 schema 的映射（第一条匹配的生效）：

| 文件 | schema |
| --- | --- |
| `repo.yml` | `repo.schema.json` |
| `companies/*/thesis.yml` | `thesis.schema.json` |
| `companies/*/sources.yml`、`industries/*/sources.yml`、`sources.yml` | `sources.schema.json` |
| `companies/*/story.md` 的 front matter | `story.schema.json` |
| `companies/*/prereg/*.settlement.yml` | `prereg-settlement.schema.json` |
| `companies/*/prereg/*.yml`（`<期间>.yml` 与 `<期间>-owner.yml`） | `prereg.schema.json` |
| `companies/*/ledger.yml` | `ledger.schema.json` |
| `companies/*/valuation.yml` | `valuation.schema.json`（仅私有仓库） |
| `industries/*/industry.yml` | `industry.schema.json` |
| `forecasts/*.yml` | `forecast.schema.json` |
| `constitution/decision-rights.yml` | `decision-rights.schema.json` |
| `constitution/rules.yml` | `constitution-rules.schema.json` |
| `agents/*.yml` | `agent.schema.json` |
| `memos/*.yml` | `memo.schema.json`（仅私有仓库） |
| `escalations/*.yml` | `escalation.schema.json`（仅私有仓库） |
| `decision-log/*.yml` | `decision-log.schema.json`（仅私有仓库） |

其余 YAML（`trust/levels.yml`、`hq/ranking.yml`、`updates/*.yml` 等）只检查语法和重复键，内容由对应的检查读取。

### 2.1 预注册三件套

每个业绩事件（期间 `FY<年>Q<季>`，按公司财年）在 `companies/<TICKER>/prereg/` 下最多有四个文件：

| 文件 | 谁写 | 内容 | 何时不可变 |
| --- | --- | --- | --- |
| `<期间>.yml` | 系统（15A，`author: system`） | 文件头与 1–8 条预期 | 截止时间之后 |
| `<期间>-owner.yml` | 所有者（`author: owner`） | 新加的条目（`added_by: owner`）与对系统条目概率的改写 `overrides` | 截止时间之后 |
| `<期间>.yml.ots`（及 `<期间>-owner.yml.ots`） | 流水线 | OpenTimestamps 时间戳证明 | — |
| `<期间>.settlement.yml` | 流水线（15B 与 GitHub） | 合并时间、接收时间、登记号、结算结果 | 随结算补写 |

条目文件（`prereg.schema.json`）：

```yaml
company: MSFT
event:
  period: FY2027Q1             # 文件名里的期间，必须一致
  expected_release: 2026-10-28
  form: 8-K                    # 8-K | 6-K | 10-Q | 10-K | 20-F
  placeholder: false           # 发布日是否为占位
deadline: "2026-10-27T23:59:59-04:00"   # 带时区偏移的 ISO 8601；发布日前一天结束（美国东部时间）
author: system                 # system | owner，与文件名一致
horizon: mixed                 # 可选：quarter | 18m | mixed
items:
  - id: MSFT-FY2027Q1-1        # <TICKER>-<期间>-<序号>
    statement: 本季营收同比增速不低于上季
    probability: 0.6           # 0.05–0.95
    criterion: 以 10-Q 利润表为准……
    data_source: 10-Q 利润表
    horizon: quarter           # quarter | 18m
    resolves_by: 2026-11-30
    domain: enterprise_software
    added_by: system           # 系统文件里只能是 system
    pillar: P1                 # 可选
    falsifies_thesis: true     # 可选
    reference: 参照类别、频率与出处   # 可选
```

- 系统文件至少 1 条、至多 8 条，不得有 `overrides`。所有者文件的条目写 `added_by: owner`，可以只有 `overrides: [{id, probability, note?}]`（此时 `items: []`），但不能两者都空；它的 `deadline` 与系统文件相同。
- 条目文件里不写 `merged_at`、`ots_proof`、`acceptance_datetime`、`accession` 或结算结果：这些在截止时间之后才知道，写进结算文件，条目文件因此可以在截止前打上时间戳并保持不变。
- 结算文件（`prereg-settlement.schema.json`）：`company`、`period`，可选 `acceptance_datetime`、`accession`、`merged_at`（条目文件合并进默认分支的时间，取自 GitHub）、`ots_proof`，以及 `results: [{id, outcome, values?, calculation?, evidence?, source?, reasoning?, settled_at?, hq_ruling?}]`，`outcome` 为 `happened`、`not_happened` 或 `undetermined`。
- `C-PREREG-TIMING` 检查截止时间落在发布日之前、`merged_at` 早于截止时间、截止时间早于 `acceptance_datetime`；`C-PREREG-IMMUTABLE` 检查截止时间过后条目文件旁有 `<文件>.ots`；装有 `ots` 客户端时，先在本地比对文件的 sha256 与证明记录的哈希（`ots info`，不联网），不一致或证明读不出来即为错误；一致之后再用 `ots verify` 核验时间证明，没有比特币节点、证明仍待确认或连不上日历服务器时只报警告。

## 3. 来源标签

### 3.1 语法

Markdown 中，来源标签写成 `[src:TAG]` 或 `[src:TAG#LOCATOR]`：

- `TAG` 匹配 `^[A-Z0-9][A-Za-z0-9._-]*$`，必须在适用的 `sources.yml` 中登记。
- `LOCATOR` 是标签内的位置，不含空白和 `]`，例如 `p3`、`Item7`、`MD&A`、`note-12`。

正则：`\[src:([A-Z0-9][A-Za-z0-9._-]*)(?:#([^\]\s]+))?\]`

YAML 中，事实写成对象，`source` 字段取同样的 `TAG` 或 `TAG#LOCATOR` 字符串：

```yaml
value: 52
unit: "%"
period: FY2026
as_of: 2026-06-30
source: MSFT-10K-FY2026#Item8
```

`settlement_source`、`acknowledged_source` 同样是来源字段。

### 3.2 标签解析顺序

1. 同目录的 `sources.yml`（公司或行业）；
2. 仓库根目录的 `sources.yml`。

找不到即为错误。

### 3.3 命名约定（应当，同 00 §E1）

| 类型 | 格式 | 例 |
| --- | --- | --- |
| 自有报告 | `<TICKER>-RPT<n>-<YYYY-MM-DD>` | `MSFT-RPT1-2026-09-17`、`MSFT-RPT2-2026-09-30` |
| 定期报告 | `<TICKER>-<FORM>-<PERIOD>` | `MSFT-10K-FY2026`、`AXP-10Q-FY2026Q2`、`PDD-20F-FY2025` |
| 临时报告 | `<TICKER>-<FORM>-<YYYY-MM-DD>` | `MSFT-8K-2026-09-02` |
| 电话会纪要 | `<TICKER>-CALL-<PERIOD>` | `AXP-CALL-FY2026Q2` |
| 新闻 | `<TICKER>-NEWS-<YYYY-MM-DD>-<媒体>` | `APP-NEWS-2026-03-12-WSJ` |
| 评价页面 | `<TICKER>-REV-<平台>-<YYYY-MM-DD>` | `PDD-REV-TRUSTPILOT-2026-09-01` |
| 其他网页 | `<TICKER>-WEB-<YYYY-MM-DD>-<n>` | `SPGI-WEB-2026-08-30-1` |
| 档案本身 | `<TICKER>-DOSSIER-<版本日期>`（位置写 `#s<部分>`） | `MSFT-DOSSIER-2026-09-24#s3` |
| 股东信 | `<TICKER>-LTR-<YYYY>` | `BRK-LTR-2024` |
| 行业报告 | `IND-<ID>-<YYYY-MM>` | `IND-PAYMENTS-2026-09` |

`FORM` 去掉连字符：`10K`、`10Q`、`8K`、`6K`、`20F`、`DEF14A`。定期报告的 `PERIOD` 按公司自己的财年写（`FY2026`、`FY2027Q1`），与预注册的期间写法一致；临时报告的日期取 EDGAR 的 filing date（美国东部时间 17:30 之后接收的顺延到下一个工作日），不取新闻稿落款日。同一天同一表格有两份都要登记时，按登记号先后给后者加 `-2`、`-3`（如 `PDD-6K-2025-12-19-2`），并在 `note` 里写明登记号。自有报告带编号和完整日期，同一个月的两份报告不会撞名；旧写法 `<TICKER>-RPT-<YYYY-MM>` 仍能解析，但应当在预注册打时间戳之前迁移，免得旧标签被冻结进时间戳。

### 3.4 什么是“需要出处的数字”

在 Markdown 正文中（不含 front matter、代码块、行内代码、链接 URL），下列任一匹配即视为事实数字：

- 美元符号后接数字：`\$\s?\d`
- 数字后接单位：`\d[\d,.]*\s?(%|％|亿|万|千万|百万|美元|元|倍|×|pp|个百分点|bp|bps|基点|美分|¢|bn|million|billion)`

纯年份、日期、季度（`2026`、`FY2027`、`2026-09-24`、`Q2`、`2026 年`）、章节号和列表序号不算。
**规则：** 含事实数字的每个句子（以 `。！？；` 或换行分隔）必须至少含一个 `[src:...]` 标签。事先写下的门槛与预测（测试的 `fail_if`、`warn_if`、`rule`，预注册条目，账本中系统与所有者一侧的预测）不是事实，不需要标签；句中引用的基准数照常标。

**英文文本（thesis-ci 0.3.0）。** 上述规则按英文的句子边界用于英文文本：句子在后接空白的 `.`、`!`、`?` 或 `;` 处结束（中间可以隔着右引号或右括号，也可以隔着紧跟在标点后面的来源标签，这时标签属于前一句）。数字中的小数点（`3.5%`）、常见缩写（`U.S.`、`Inc.`、`Corp.`、`Ltd.`、`e.g.`、`i.e.`、`vs.`、`No. 1`、姓名首字母和月份缩写）后的句点以及来源标签内的句点都不是句末。英文段落内的换行不结束句子，因为英文常按固定宽度折行；空行、标题、列表项、表格行和引用块则结束句子。含中文、日文或韩文字符的行仍按上文切分：在 `。！？；` 和每个换行处。正则所列单位的其他写法同样算，不分大小写：`percent`、`per cent`、`pct`、`percentage points`、`pp`、`ppt`、`basis points`、`bp`、`bps`、`cents`、`thousand`、`million`、`mn`、`mln`、`billion`、`bn`、`bln`、`trillion`、`tn`、`25x` 这样的倍数、货币名称（`dollars`、`euros`、`yuan` 等）、写在数字前面或后面的货币代码（`USD 5`、`5 USD`、`RMB 5`）以及其他货币符号（`€`、`£`、`¥`、`₹`）。英文日期（`September 30, 2026`、`30 June 2026`）、期间（`FY26`、`3Q26`、`1H26`）和章节号（`Item 7A`、`Section 3.4`、`Note 12`）不算事实数字。

### 3.5 sources.yml 条目

见 `sources.schema.json`。`kind` 取 `filing`、`report`、`industry_report`、`transcript`、`press_release`、`letter`、`presentation`、`proxy`、`news`、`review`、`web`、`other`。`kind: filing` 的条目应当有 `accession`（EDGAR 登记号）；缺失时为警告，不是错误。

标题用英文。其他语言的来源（例如所有者的中文报告）在 `title` 写英文译名并注明“(in Chinese)”，可以在可选的 `title_original` 里照录原文标题；这是档案中 `zh-CN/` 以外唯一可以出现中日韩文字的字段（8.5）。

## 4. thesis.yml

见 `thesis.schema.json`（`schema_version: "0.2"`）。要点：

- `status`：`holding`（持仓）、`candidate`（候选）、`archive`。
- `category`：林奇六类之一：`slow_grower`、`stalwart`、`fast_grower`、`cyclical`、`turnaround`、`asset_play`。类别决定默认监控模板（`spec/templates/lynch/<category>.yml`），类别变化即换模板。
- `domain`：校准分组，见 schema 枚举。
- `depends_on`：行业模块路径列表，形如 `industries/payments-card-networks`；可以为空。
- `trust_level`：公司经理的信任等级 0–3，由流水线维护（4.2）。
- `reviewed`：档案各部分的最近复核日期，供时效测试使用。必填的十二个键对应档案的十二个部分：`business`、`economics`、`moat`、`capital_allocation`、`management`、`culture`、`runway`、`valuation`、`bear_case`、`monitoring`、`thesis`、`breakers`；两份附加清单 `munger`（芒格矩阵，档案的附加清单一）、`unknowns`（未知登记）可选。键与 00 §F5 的 `archive_patch.section` 相同（`ratings` 除外）。
- `ratings`：只含 `business`、`management`（必填）与 `capital_allocation`、`culture`（可省略，省略即留空，不等于中性）；**价格评级、价值区间和任何价格数字不得出现在公开的 thesis.yml 中**，它们放在私有仓库的 `valuation.yml`。
- `tests`：至少 5 条仍然有效的测试，且三类（`quantitative`、`qualitative`、`staleness`）各至少 1 条。

### 4.1 thesis tests

每条测试的共同字段：`id`（`<TICKER>-<Q|L|S><n>`）、`type`、`claim`（这条测试守护的论点，一句话）、`origin`、`severity`、`covers`、`effective_from`，可选 `supersedes`、`retired_at`、`pillar`、`note`。

- `origin`：`template:<category>`（来自林奇模板）、`report:breaker` / `report:watch`（来自报告的论点破坏信号 / 前瞻指标）、`archive:breaker` / `archive:watch`（来自档案第 12 部分 / 第 10 部分）、`proposal:04B`、`proposal:04B-lite`、`proposal:07`、`proposal:08`、`proposal:11`（审计或研究环节提出、经公司经理采纳的测试建议）、`manual`（公司经理自写）。
- `severity`：`breaker`（失败即该部分投资逻辑作废，7 天内按 00 §G3 处置）或 `watch`（失败即警告，进入下次更新）。
- `covers`：这条测试检验的质量维度，见 schema 枚举。宪法第 2、3 条要求每家公司仍然有效的测试合起来覆盖 `moat`、`pricing_power`、`returns_on_capital`、`free_cash_flow`、`capital_allocation` 和 `management`。
- **生命周期（00 §G7）。** `effective_from`（`FY<年>Q<季>`）：从这一期起按本条判定；新增或修改的测试只对以后的期间生效。改门槛不改旧条目：写一条新测试，`supersedes` 填旧测试的 id，旧测试写 `retired_at`（从这一期起不再判定，条目保留作记录）。写了 `retired_at` 的测试不计入最少 5 条和覆盖要求；给出 `--period` 时，只有 `retired_at` 不晚于当期的才算退役。
- `note` 可以带论点措辞；判定员看不到它。交给判定员的规则写在定性测试的 `judge_notes` 里。

**定量测试**（`type: quantitative`）：

```yaml
- id: MSFT-Q1
  type: quantitative
  claim: 微软云的毛利率守在资本开支周期能回本的水平之上
  origin: report:breaker
  severity: breaker
  covers: [returns_on_capital]
  metric: microsoft_cloud_gross_margin      # spec/metrics.yml 中的 id，或用 metric_def 就地定义
  fail_if: 连续两个季度低于 58%
  rule: {op: "<", threshold: 58, unit: "%", consecutive: 2, period: quarter}
  warn_if: 低于 62%
  warn_rule: {op: "<", threshold: 62, unit: "%", consecutive: 1, period: quarter}
  data: filing_text                          # xbrl | filing_text | external | mixed
  effective_from: FY2027Q1
  first_readable: 2026-10
  baseline: {value: 66, unit: "%", period: FY2026, source: MSFT-RPT1-2026-09-17#p10}
```

- `data`：`xbrl`（EDGAR XBRL）、`filing_text`（申报文件正文，由模型抽取并标注出处）、`external`（非 SEC 文件的官方数据，如 FRED、NAIC、ETF 资产规模）、`mixed`（组成部分来源不同）。`data` 必须与指标定义一致。
- `rule` 可以用 `all_of` / `any_of` 组合多个子规则。门槛是事先写下的判定标准，不需要出处；`baseline` 是事实，必须有出处。
- **一条测试用到多个量**时，写 `metric_def.components`：组成名（`^[a-z][a-z0-9_]*$`）→ `{description, unit, where?, xbrl?}`；子规则的 `metric` 写组成名，或 `<指标>.<组成>`（点号前是本测试的 `metric` 或 `metric_def.id`）。`rule.metric` 必须能解析：登记表中的指标、本测试的指标或它的组成。0.1 的 `params.metric_defs` 在迁移期仍能解析，应当改写为 `components`；`params` 本身仍然允许（例如 `params.segment`）。

```yaml
  metric_def:
    id: recurring_share
    description: 经常性收入 ÷ 总收入
    unit: "%"
    data: mixed
    formula: recurring / revenue
    components:
      recurring: {description: 经常性收入, unit: USD, where: 10-K 收入分解附注}
      revenue: {description: 总收入, unit: USD, xbrl: ["us-gaap:Revenues"]}
  rule:
    all_of:
      - {metric: recurring_share, op: "<", threshold: 50, unit: "%", consecutive: 2, period: year}
      - {metric: recurring_share.recurring, op: decrease, threshold: 0, unit: "%", period: year}
    evaluate_from: FY2028Q4
```

- **期间选择**：`rule`（及子规则）可以写 `evaluate_on`（只在这些期间求值）或 `evaluate_from`（从这一期起求值），取值为 `FY<年>` 或 `FY<年>Q<季>`。

**定性测试**（`type: qualitative`）：必须有 `question`（独立模型要回答的是非题）、`fail_if`、`judge: independent_model`、`evidence: required`、`where`（判定时读哪些文件：字符串或字符串列表，流水线据此抓取）和 `lookback`（读几期文件，含本期，正整数；一期是一个财季，与 `effective_from` 同一计法，年度文件按财季折算，例如要读到上一份年报写 5）；可选 `judge_notes`（交给判定员的判定规则，字符串或列表）。判定时必须附出处和一句以内的原文摘录。

**时效测试**（`type: staleness`）：`section` 取 `reviewed` 的十四个键之一，`max_age_quarters` 为整数；以 `reviewed.<section>` 为基准，超过 `max_age_quarters × 91` 天即失败。

测试结果只有四种：`pass`、`warn`、`fail`、`undetermined`。定量测试如何判定见 4.5。

### 4.2 流水线维护的字段（00 §G8）

公司经理不得修改 `trust_level`、`status`、`filer`、`schema_version`。流水线把各角色的信任等级记在公开仓库的 `trust/levels.yml`：

```yaml
as_of: 2026-10-30
companies:                 # 公司经理，按公司代码
  MSFT: 1
industries:                # 行业研究员，按行业模块 id（对应 industry.yml 的 trust_level）
  payments-card-networks: 1
```

`C-TRUST-WRITE`（警告）核对 `thesis.yml` 的 `trust_level` 与这里一致（`industry.yml` 写了 `trust_level` 时同样核对）。`reviewed` 日期只为本次实际复核过的部分更新，并列进该次更新记录 front matter 的 `reviewed_sections`：

```markdown
---
company: MSFT
doc: update
as_of: 2026-10-30
doc_status: final
reviewed_sections: [economics, monitoring]
---
```

`thesis.yml` 里等于某次更新 `as_of` 的每个 `reviewed` 日期，其部分都必须列在那次更新的 `reviewed_sections` 里（同一天的几次更新合起来算）。

### 4.3 结果出来后不改门槛（00 §G7）

`thesis-ci lint --base-ref <git 引用> --period FY<年>Q<季>` 把 `thesis.yml` 的测试与该引用下的版本逐条比较（`C-TEST-FROZEN`）：对当期有效的测试（base 版本的 `effective_from` 不晚于当期、且未退役；没有 `effective_from` 的旧测试视为一直有效），`rule`、`fail_if`、`warn_rule`、`warn_if`、`max_age_quarters` 不得改动，也不得删除。只改格式（例如行内映射改成块映射）不算改动。业绩文件入库之后的 PR 应当带上这两个参数。

### 4.5 求值（thesis-ci 0.4.0）

`thesis-ci evaluate <档案> --company <代码> --period FY<年>Q<季> --readings <文件> [--today YYYY-MM-DD] [--format yaml|json]` 用一份读数文件判定一家公司的定量测试，输出 `ci_results` 文件（`ci-results.schema.json`）。只要运行完成就以 0 退出，因为测试失败是结果而不是错误；用法错误（文件读不出或不合规、几处公司代码不一致）以 2 退出。

**读数**（`readings.schema.json`）：`{company, as_of, readings: [{metric, period, value, unit, source, basis?, note?, segment?, series?}]}`。

- `metric` 是登记表中的 id、测试的 `metric` 或 `metric_def.id`，或 `<指标>.<组成项>`；没有写指标的 `op: event` 子规则，其读数以测试 id 为键（`MSFT-Q9`）。`period` 取 `FY<年>`、`FY<年>H<半年>` 或 `FY<年>Q<季>`，按公司自己的财年。`source` 是来源标签（3.1）。
- `value` 是数字；事件为 `true` 或 `false`；指标查过、但没有可量的东西（没有符合条件的事件，或按定义不计算）时为 `null`，此时必须写 `note`。找不到的读数不写，绝不写成 `null`。
- 带 `params.segment` 的测试只用 `segment` 与之相同的读数，不带的测试只用不带 `segment` 的读数。同一指标的读数带 `series` 时（例如 `params.holders` 中每个持有人集团一组），逐组判定，任何一组成立即子规则成立。
- `data: xbrl` 的指标可以从 EDGAR companyfacts 计算（`thesis_ci.metrics`）：只用 10-K、10-Q、20-F 和 40-F 的事实，按起止日期放进财年日历，同一区间取最晚申报的数值；没有单独披露的季度用年初至今的数字推出（第四季度 = 全年 − 前九个月），股数和每股数据除外；来源写作 `<代码>-XBRL#<概念>:<登记号>`。算不出的指标不出现。

**判定哪些测试、哪些期间。** 只判定本期生效的测试（`effective_from` ≤ 本期 < `retired_at`），其余列在 `not_in_force`。`quarter` 或 `event` 规则读本季；`half` 规则读以本季结束的半年（`FY<年>H<n>`，在第二、第四季判定）；`year` 规则读以本季结束的财年（在第四季判定）。规则的期间不在本季结束、`evaluate_on` 没有列出本季（`evaluate_on` 中的年份代表该年的每个季度）或 `evaluate_from` 更晚时，该规则不到期。`all_of` 要所有子规则都到期才到期；`any_of` 只要有一个到期就到期，且只判定到期的子规则。没有任何规则到期的测试记为 `not_due` 并写明原因：这表示本期没有判定，不是第五种结果。

**规则如何判定。**

- 没写 `period` 的子规则继承上一层的；根的默认值是测试所用指标的频率，没有则为 `quarter`。
- `consecutive`（默认 1）写在比较上，要求它在最近 N 期每期都成立；写在 `all_of` 或 `any_of` 上，要求组合在同一期成立、连续 N 期，这时所有子规则的 `period` 必须与它相同。`evaluate_from` 之前的期间一律不计入连续期数。
- `increase` 和 `decrease` 与上一财年的同一期间比较（季度规则比上年同季，年度规则比上一年），变动超过 `threshold` 时成立：单位为 `pp` 时取两个百分比之差；为 `%` 时取本身不是百分比的指标的相对变动（百分比指标用 `%` 门槛有歧义，不接受）；为指标自己的单位时取差值。
- `between` 含两端，`outside` 为其补集。事件的读数为 `true` 时成立。
- 同类单位之间换算（`USD`、`USD million`、`RMB 100 million` 即 `CNY 100 million`）；其他不一致使比较无法判定。
- 缺读数的比较无法判定；连续期数中最近一期没有读数时，即使更早的某一期已经打断连续，也无法判定：某一期的结果要以该期的数据为据。`all_of` 只要有一个子规则不成立就不成立，`any_of` 只要有一个成立就成立，不管其他读数缺不缺。读数为 `null` 时比较不成立。
- 先判定失败规则：成立为 `fail`，无法判定为 `undetermined`。否则判定 `warn_rule`：成立为 `warn`，无法判定为 `undetermined`，其余为 `pass`。

`C-TEST-METRIC` 会报告引擎无法判定的规则（单位与指标不符、`increase` 或 `decrease` 的单位有歧义、`evaluate_on` 永远不会到期）。每条结果带 `reading`（规则第一个指标的本期读数）、`readings`（用到的全部读数，含连续期数中的前几期和同比基数）、按登记原样的 `rule` 与 `warn_rule`（规则只有一个比较时另有 `op`、`threshold`、`unit`）、`fail_if`、`warn_if`、`consecutive_count`、`missing`（无法判定时缺的读数）、`reason`，以及 `evaluation` 下判定过的规则树。在 `--today` 那天尚未结束的期间，其读数被忽略并列在 `ignored_readings`。

### 4.4 言行账本 ledger.yml

见 `ledger.schema.json`。`side`：`management`（管理层承诺，按四档结算：`kept`、`partially_kept`、`not_kept`、`silently_dropped`，或 `undetermined`）、`system` 与 `owner`（预测，必填 `probability`，0.05–0.95；状态只用 `pending`、`kept`、`not_kept`、`undetermined`，判定标准写在 `note`）。`last_mentioned`：管理层最近一次提到这条承诺的日期（判断“悄然消失”）；`acknowledged_source`：未兑现时主动承认的出处（来源标签或 null）。

## 5. story.md

两分钟持有理由。YAML front matter 见 `story.schema.json`。用中文（或日文、韩文）写的正文不超过 700 个字符，每个字计一个；用英文写的正文不超过 350 个词。两种计数都不含来源标签、Markdown 标记和链接地址。中日韩文字不少于英文词数的故事按字符计。350 个词大约是以每分钟 150–175 个词朗读两分钟的长度，也大约是 700 个汉字译成英文后的长度（一个汉字约合半个英文词）。正文不得出现价格、价值区间、隐含回报、仓位比例或买卖建议。事实数字按 3.4 标注出处。

## 6. 行业模块

`industry.yml` 见 `industry.schema.json`。行业模块只描述行业本身：**不得**列出持仓、不得给建议、不得写“依赖本行业的公司”。依赖关系只写在公司一侧的 `depends_on`。每个模块至少 3 个可观测的路标（`signposts`），每个路标有可观测量、事先写下的门槛和检查频率。可选 `trust_level`（0–3）记行业研究员的信任等级，由流水线维护（4.2）。

## 7. 私有仓库的文件

### 7.1 价值区间 valuation.yml

见 `valuation.schema.json`。要点：

- `doc_status`：`proposed`（重算后待 04C 审的版本）或 `effective`（生效版本）。任何时刻一家公司只有一个生效版本（00 §V20）。
- `value_ranges`：`center`（中枢）、`fair`（核心区间）、`cheap`（买入区间）、`error_band`（误差带 `[低, 高]`：与 `center` 同单位的绝对区间，不是相对比例）。
- `margin_of_safety`：安全边际区间 `[下限, 上限]`，小数，默认 `[0.25, 0.35]`（00 §V2）。
- `discount_rate`：`risk_free`（10 年期美国国债收益率）、`risk_free_date`（取值日期）、`premium`、`total`（= `risk_free` + `premium`）、`source`、`note`。`total` 有数值时必须写 `note`：溢价的判断依据，即本公司现金流记录里哪些读数让它更可预测、哪些更不可预测（00 §V1）。溢价只从本公司自己的记录推出，不在公司之间比较或插值（00 §V10）；`C-DISCOUNT-RATE` 因此不检查跨公司的溢价次序。
- `comparable_anchor`：第二参照锚 `{value, description, source}`，可比资产的市场隐含回报（00 §V6）。
- `price_rating`：`A`–`E`，按 00 §V11 的机械尺给出，不加正负号；`quality_rating` 是生意评级，与 `thesis.yml` 的 `ratings.business` 同一把尺。
- `method_note`：本次估值的方法说明，必须非空。

### 7.2 L3 备忘录 memos/*.yml

见 `memo.schema.json`。备忘录只由总部起草（`drafted_by: hq_capital_allocator`）：`options` 至少两个选项，其中一个的 `key` 是 `maintain`（默认选项，`default_option: maintain`，14 天不回复按默认处理）；`evidence: [{claim, source}]`；`trigger: {tests: [测试 id], update?}`；`constitution_refs` 引用 `R<n>` 或 `H<n>`。修宪备忘录（`action: amend_constitution`）可以没有 `company`，其余备忘录必须有。

买入、加仓备忘录还要写 `target_weight`、`order: {type: single}`、`implied_return` 与 `hurdle`。`target_weight` 不得低于入选门槛下沿（10%）；10–20% 是门槛，不是目标，高于上沿允许，但要在 `weight_note` 里写明理由（宪法第 4 条）。`hurdle` 不得低于该公司 `valuation.yml` 里伯克希尔那道第一门槛，`implied_return` 必须高于它；只过第一道、没过 VOO 参照时报警（宪法第 7 条，00 §V6）。

### 7.3 升级请求 escalations/*.yml

见 `escalation.schema.json`：`id`、`company`、`created_at`、`test_ids`、`facts: [{claim, source}]`（至少一条）、`reason`（R6 的四种企业内部原因之一：`moat_permanent_impairment`、`business_model_change`、`management_deterioration`、`capital_allocation_failure`）、`conclusion`、`drafted_by: company_manager`。“明显更好的机会”是跨公司判断，只由总部提出，不在升级请求里。

### 7.4 系列排名 hq/ranking.yml

总部按 00 §V13 综合判断排序，不按任何单一字段机械排序。每一行必须写一句排序理由 `reason`：

```yaml
as_of: 2026-10-01
rule: "§V13"
rows:
  - {rank: 1, company: ACME, reason: ……}   # 虚构公司，只作格式示例
```

`C-RATING-ORDER` 检查每一行都有 `reason`（行也可以写在 `ranking:` 下，或整个文件就是一个列表）。

### 7.5 公开仓库里不得出现的内容（00 §H4）

公开仓库中出现 `valuation.yml`、`memos/`、`escalations/`、`decision-log/`，`value_ranges`、`price_reference`、`implied_return`、`price_rating` 等键，或在公开内容（`companies/`（含 `updates/`）、`industries/`、`forecasts/`、`letters/`、`mistakes.md`）中出现 00 §H4 的用语，均为错误：估值用语（`买入区间`、`价值中枢`、`目标价`、`隐含回报`、`隐含年化回报`、`价格评级`、`price target`、`target price`、`buy range`、`fair value range`）由 `C-PUBLIC-NO-VALUATION` 检查，买卖建议用语（`建议买入`、`建议卖出`、`建议增持`、`建议减持`、`建议加仓`、`建议减仓`、`买入评级`、`卖出评级`、`强烈推荐`、`值得买入`、`应该买入`、`可以买入`、`逢低买入`、`建议建仓`、`建议清仓`、`strong buy`、`overweight`、`underweight`）由 `C-PUBLIC-NO-ADVICE` 检查。公开内容也不写以当前股价为输入的倍数或比率：同一句里出现 `市盈率`、`P/E`、`市值`、`自由现金流收益率`、`FCF yield`、`市净率`、`P/B`（或“价格低于 N 倍账面”一类写法；公司披露的回购均价与账面之比是公司的事实，不算）和数字（年份、日期、期间与一位数的编号不算）即为错误。

**英文用语（thesis-ci 0.3.0）。** 同样的检查也匹配这些用语的英文说法。估值：`implied return`、`implied annual` 或 `annualized return`、`price grade`、`price rating`、`value centre`（即禁用词价值中枢）出现即报错；`central value`（私有文件里估值中点的中性名称）、`fair range`、`value range`、`buy range`、`cheap range`、`intrinsic value`、`margin of safety` 后面跟着数字时报错（`margin of safety` 前面是百分比时也算），区间上的价格事件（“entered the buy range”）同样报错。建议：推荐买入、卖出、增持、减持、建仓或清仓（“we recommend buying”“recommend investors sell”“we recommend ACME”“recommend opening a position”）、买入或卖出评级（“rated a Buy”“upgraded to Buy”“Rating: Sell”“Buy-rated”）、以投资者为主语的 should buy / sell（“investors should buy the stock”“the shares should be sold”）、“is a buy”、对某个仓位加仓、减仓或逐步买入（“add to the position”“trim our stake”）、逢低买入（“buy on dips”）。与中文一样，否定句不例外：“we do not recommend buying” 同样报错（00 §H4）。公司回购自己的股票（“buyback”“the company should buy back stock”）和产品名称不算建议。倍数：`price-to-earnings`、`price/earnings`、`price-to-book` 以及 “trades at 25 times earnings” 一类写法与数字同句时报错。

**进度文件与价格评级（thesis-ci 0.3.0）。** 估值与建议用语的检查也读 `docs/STATUS.md` 和 `CLAUDE.md`（以及它们的中文版）：这两份文件汇报档案自身的工作，曾经写进价格评级的变化。规定规则、必须写出禁用词的文档（`docs/DESIGN.md`、`docs/decisions/`、`constitution/`）不读。在这些检查读的每个文件里，代码旁的价格评级（“AXP B− → C”“AXP: C”）所在句子谈价格或估值（价格、估值、分档、§V11），又没有谈生意、管理层、质量、企业文化或资本配置评级（它们用同样的字母）时，即为错误。

## 8. 检查

`spec/checks.yml` 是全部检查的登记表。每项检查有 `id`、`title`、`profile`（`core`、`pipeline`、`owners-office`；8.6）、`scope`（`public`、`private`、`both`、`workspace`）、`level`（`error` 或 `warning`）和 `description`。实现必须为每个登记的检查提供一个函数和至少一个单元测试；单元测试的名称或文档字符串必须包含检查 id。

在运行 `owners-office` 检查组的档案里，宪法的每条规则（`constitution/rules.yml`）必须引用至少一个登记的检查 id。

### 8.1 命令行

```bash
thesis-ci lint <path> [--counterpart <另一侧仓库>] [--today YYYY-MM-DD] [--expect-visibility public|private]
                      [--base-ref <git 引用>] [--period FY<年>Q<季>] [--profile <检查组>,...]
                      [--only <检查 id> ...] [--format text|json]
thesis-ci init <目录> [--visibility public|private] [--profiles <检查组>,...]
```

`--profile` 与 `--only` 选择运行哪些检查（8.6）。`--today` 决定截止时间是否已过（`C-PREREG-TIMING`、`C-PREREG-IMMUTABLE`）与时效（`C-STALENESS`）；`--base-ref` 与 `--period` 只用于 `C-TEST-FROZEN`；`--counterpart` 让私有仓库读到公开仓库的决策权配置与角色定义（`C-PROMPT-ISOLATION`）。

### 8.2 决策权与信任等级 decision-rights.yml

见 `decision-rights.schema.json`。`levels` 为三级决策权，动作取 schema 枚举（0.2 新增 `valuation_update`、`prompt_change`）；资金事项与修宪只在 L3。`trust` 除 `levels`、`initial`、`window`、`downgrade`、`upgrade` 外，必须有 `routing`：按信任等级分流（00 §G9），键 `"3"`、`"2"`、`"1"`、`"0"` 各写一句（3 级自动合并并公开；2 级自动合并、公开前由总部复核；1 级先留私有仓库、由总部逐条复核后公开；0 级暂停自治）；可选 `scoring` 写计分方法（事实错误怎样降级、分歧裁定怎样计入、谁的哪类产出算一次更新）。可选 `gate` 写 17A 的放行规则。`ranking` 为 `{rule, candidates?, rotation?}`：`rule` 引用排名条款（例如 `"§V13"`），不再有机械的 `order`。

### 8.3 角色与提示词的隔离

`agents/<role>.yml` 的 `role` 取 `company_manager`、`auditor`、`model_reviewer`、`red_team`、`synthesis_reviewer`、`design_reviewer`、`blind_reader`、`judge`、`settler`、`extractor`、`hq_capital_allocator`、`industry_researcher`、`typesetter`；`can_see`、`cannot_see` 用与提示词 front matter 相同的输入名。私有仓库的 `prompts/*.md` 在 front matter 里声明角色与输入：顶层的 `role` 与 `inputs`，或 `parts` 下各部分的 `role`（省略时取顶层）与 `inputs`（以及 `inputs_pass1`、`inputs_pass2` 等）；输入名末尾的 `?` 表示可选。`C-PROMPT-ISOLATION`（警告，私有仓库带 `--counterpart` 时运行）报告任何一部分的输入出现在该角色 `cannot_see` 里的情形；比较时去掉 `?` 和 00 §F0 的部分编号后缀（`findings_04A` 按 `findings` 比较）。

### 8.4 0.2 新增的检查

| id | 范围 | 级别 | 检查 |
| --- | --- | --- | --- |
| `C-PREREG-IMMUTABLE` | public | error | 截止之后的条目文件有 `<文件>.ots`；装有 `ots` 时 `ots verify` 通过，无法核验时报警 |
| `C-TRUST-WRITE` | public | warning | `trust_level` 等于 `trust/levels.yml`；改动的 `reviewed` 日期列在更新的 `reviewed_sections` 里 |
| `C-TEST-FROZEN` | public | error | 给出 `--base-ref` 与 `--period` 时，当期有效的测试门槛未被改动或删除 |
| `C-PROMPT-ISOLATION` | private | warning | 提示词各部分的输入与角色的 `cannot_see` 不相交 |

### 8.5 英文优先：zh-CN/ 与 C-LANGUAGE（thesis-ci 0.3.0）

运行 `owners-office` 检查组的档案以英文为主。关键文档的中文版放在仓库根目录的 `zh-CN/<相同路径>`，front matter 之后的第一行链接回英文原文，英文文件在开头附近写明中文版的位置。其余文件只有英文。

- 中文版与它翻译的文件一样对外发布。公开内容的检查（`C-PUBLIC-NO-VALUATION`、`C-PUBLIC-NO-ADVICE`、`C-PUBLIC-NO-AMOUNTS`、`C-NO-PRICE-FEED` 的股价检查、`C-DEPENDS` 的中立检查）像读英文文件一样读 `zh-CN/companies/`、`zh-CN/industries/`、`zh-CN/forecasts/`、`zh-CN/letters/` 和 `zh-CN/mistakes.md`；`C-SRC-TAG` 检查其中的事实数字，标签按英文文件的位置解析（`zh-CN/companies/<TICKER>/story.md` 读 `companies/<TICKER>/sources.yml`）。
- `C-LANGUAGE`（both，error）：`zh-CN/` 以外的文本文件不得含中日韩字符（汉字、假名、谚文、中日韩标点或全角字符）。例外：仓库根目录的 `zh-CN/`；测试与测试数据（`tests/`、`test/`、`fixtures/` 目录，`test_*.py`、`*_test.py`、`conftest.py`），它们可能需要中文文本；`sources.yml` 条目中 `title_original` 的值（3.5）。每个文件报一条错误，指向第一处含中日韩文字的行，并给出这样的行数。

| id | 范围 | 级别 | 检查 |
| --- | --- | --- | --- |
| `C-LANGUAGE` | both | error | 英文文件不含中日韩文字；`zh-CN/`、测试、测试数据和 `sources.yml` 的 `title_original` 例外 |

### 8.6 检查组（thesis-ci 0.5.0）

每项检查恰好属于一个检查组（profile），由 `spec/checks.yml` 中的 `profile` 给出：

| 检查组 | 适用于 | 检查 |
| --- | --- | --- |
| `core` | 任何论点档案 | `C-SCHEMA`、`C-SRC-TAG`、`C-SRC-FACT`、`C-SRC-ACCESSION`、`C-PUBLIC-NO-VALUATION`、`C-PUBLIC-NO-ADVICE`、`C-PUBLIC-NO-AMOUNTS`、`C-NO-PRICE-FEED`、`C-NO-TRADING`、`C-NO-SECRETS`、`C-TESTS-MIN`、`C-TESTS-COVERAGE`、`C-TESTS-CAPALLOC`、`C-TEST-METRIC`、`C-TEST-QUAL-EVIDENCE`、`C-STALENESS`、`C-DEPENDS`、`C-STORY`、`C-PREREG-TIMING`、`C-PREREG-IMMUTABLE`、`C-TEST-FROZEN` |
| `pipeline` | 由大模型研究流水线写成的档案 | `C-LLM-ENTRY`、`C-AGENT-ISOLATION`、`C-PROMPT-ISOLATION`、`C-TRUST-WRITE` |
| `owners-office` | 采用 Owner's Office 宪法的档案 | `C-RATING-ORDER`、`C-CONCENTRATION`、`C-DISCOUNT-RATE`、`C-SELL-REASONS`、`C-HURDLE`、`C-SINGLE-ORDER`、`C-DEFAULT-HOLD`、`C-DECISION-RIGHTS`、`C-CONSTITUTION-MAP`、`C-LANGUAGE` |

**怎样选择。** 档案在 `repo.yml` 中写明自己的检查组（`profiles: [core]`、`profiles: [core, pipeline]`），顺序无关。没有 `profiles` 时运行全部检查组，与 0.5.0 之前相同。如果取值不是由互不重复的已知检查组构成的非空列表，也运行全部检查组，并由 `C-SCHEMA` 报错：写错一个字不会关掉任何检查。`thesis-ci lint --profile <检查组>,...` 在这一次运行中以指定的检查组代替 `repo.yml` 里的（公开仓库的 CI 可以这样固定检查组，就像固定 `--expect-visibility` 一样）；`--only` 只运行它列出的检查，不管检查组。检查组选出检查，再由 `scope` 决定其中哪些在公开仓库或私有仓库上运行。`thesis-ci init` 新建的档案写 `profiles: [core]`，除非 `--profiles` 另有指定。

**各检查组需要什么。** `core` 只要求 `repo.yml`，以及 `companies/` 下每家公司的 `thesis.yml` 和 `story.md`，它们的来源标签在 `sources.yml` 中解析；它读到的其他内容（预注册、账本、行业模块、预测、信件、代码）存在时才检查。`core` 的检查不要求任何只有其他检查组才读的文件：`constitution/rules.yml` 和 `constitution/decision-rights.yml` 只有 `C-CONSTITUTION-MAP` 和 `C-DECISION-RIGHTS`（`owners-office`）要求；`agents/*.yml`、`trust/levels.yml` 和 `prompts/*.md` 只与 `pipeline` 的检查有关，这些文件不存在时那些检查空过。不管选了哪些检查组，`C-SCHEMA` 都校验第 2 节列出的每一个存在的文件，所以即使没有 `owners-office`，`memos/*.yml` 也要符合 `memo.schema.json`。

**边界情形的归属。** 一项检查只要保护的是任何论点档案，就归入 `core`，不管它源自谁的规则：

- `C-TESTS-COVERAGE` 和 `C-TESTS-CAPALLOC` 引用宪法第 2、3 条，但它们要求的（测试合起来考察护城河、定价权、资本回报、自由现金流、资本配置和管理层）是一篇关于生意的论点起码要检验的内容：`core`。`C-CONSTITUTION-MAP` 仍把第 2、3 条映射到它们。
- `C-TEST-QUAL-EVIDENCE` 要求 `judge: independent_model`，但它规定的是定性测试本身的形态（一道问题、一个不通过条件、指定的文件、回看期数），并不调用模型：`core`。
- `C-PUBLIC-NO-VALUATION`、`C-PUBLIC-NO-ADVICE`、`C-PUBLIC-NO-AMOUNTS`、`C-NO-PRICE-FEED` 和 `C-NO-TRADING` 源自 00 §H2 与 §H4，但它们让公开档案里没有估值、股价、持仓金额和建议，让任何档案里都没有股价来源和下单代码：`core`。`C-DEPENDS` 也属于 `core`：依赖必须能解析，而列出持仓的行业模块会泄露仓位。
- `C-LLM-ENTRY` 与 `C-NO-TRADING` 一样是代码的静态扫描，但只有模型参与撰写档案时，唯一的模型入口才有意义：`pipeline`。`C-TRUST-WRITE` 把 `thesis.yml` 与流水线保存的记录（`trust/levels.yml`、`reviewed_sections`）对照：`pipeline`。
- `C-RATING-ORDER` 检查的评级 thesis schema 已经要求，它只多检查 `hq/ranking.yml` 的排名理由（00 §V13），这是 Owner's Office 的做法：`owners-office`。`C-DECISION-RIGHTS` 检查这部宪法的 `decision-rights.yml` 中的三级决策权和信任等级：`owners-office`。
- `C-LANGUAGE` 要求档案以英文为主、中文版放在 `zh-CN/` 下（8.5），这是 Owner's Office 的约定；用其他语言写的档案会通不过：`owners-office`。

## 9. 指标登记表

`spec/metrics.yml` 列出定量测试可以引用的指标：`id`、`description`、`unit`、`frequency`、`data`（`xbrl` 或 `filing_text`）、`xbrl`（候选概念，按优先顺序）、`formula` 与 `where`。thesis-ci 从 EDGAR companyfacts 计算 `xbrl` 指标（4.5），`book_value_per_share_yoy` 除外，因为没有登记的概念给出它所需的股数。XBRL 概念跟着发行人采用的会计准则走，不跟表格走：按美国会计准则编报的外国私人发行人（例如 PDD 的 20-F）同样用 `us-gaap` 概念，只有按 IFRS 编报的发行人才用 `ifrs-full`。登记表中没有的指标，用测试里的 `metric_def` 就地定义（字段同登记表条目，另可写 `components`，`data` 可取 `external` 或 `mixed`）。

## 10. 版本

本规范为 v0.2。跑完两个财报季后定 v1.0，之前的不兼容改动在 `CHANGELOG.md` 中逐条记录。

thesis-ci 0.3.0 增加英文支持和 `C-LANGUAGE`（3.4、3.5、5、7.5、8.5），除可选的 `title_original` 外不改任何文件格式；档案的 `spec_version` 仍为 `"0.2"`。

thesis-ci 0.4.0 增加定量测试的求值（4.5）和两种新文件：读数与 `ci_results`（`readings.schema.json`、`ci-results.schema.json`）；`C-TEST-METRIC` 还会报告引擎无法判定的规则。档案文件的格式不变；档案的 `spec_version` 仍为 `"0.2"`。

thesis-ci 0.5.0 增加检查组（8.6）和 `repo.yml` 的可选字段 `profiles`；检查本身不变，没有 `profiles` 的档案检查结果与以前相同。档案的 `spec_version` 仍为 `"0.2"`。
