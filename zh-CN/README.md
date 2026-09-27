> 中文版。英文原文：[README.md](../README.md)

# thesis-ci

**投资论点的持续集成。** 把"什么会证明我错了"写成机器能执行的测试；在业绩公布之前登记预测并加时间戳；事后按事先定好的标准打分。

> **不构成投资建议。** thesis-ci 不抓取股价，不给买卖信号，也不执行任何交易。

## 为什么

大多数投资论点是一段文字：写起来容易，检查起来难，事实一变就被悄悄改写。thesis-ci 让论点像代码一样运转：

| 软件工程 | 投资（用 thesis-ci） |
| --- | --- |
| 源代码 | `thesis.yml`：论点、评级、行业依赖和测试 |
| 单元测试 | 论点测试，每一条都在数据出来之前写好：必须守住的数字（从 XBRL 或申报文件的指定行计算）、由独立模型引用证据作答的是非题，或者一条过期上限，论点的某一部分太久没有重新审视就判为不通过 |
| CI | 每份新的 10-Q、10-K 或 8-K 都会运行测试；某一期的业绩一旦公开，这一期的门槛就对照 git 历史冻结 |
| Lint | `thesis-ci lint`：每个数字都引用一手来源，公开文件不含估值和建议，投资者宪法的每条规则都对应一项可执行的检查 |
| 测试报告 | 预测带概率预先登记、加时间戳、结算并打分（Brier 分数、分领域校准） |

它面向写成文字的论点、并希望这些论点能被检验的个人投资者和小团队；也面向需要护栏的大模型研究流水线：事实必须有出处，公开输出不含建议，起草的模型和审计的模型彼此隔离。

## 一个测试长什么样

```yaml
# 取自包内的示例档案（虚构公司），略有删减
- id: ACME-Q2
  type: quantitative
  claim: Gross margin shows that pricing power holds
  origin: report:breaker       # 测试的来历：研究报告列出的论点破坏条件
  severity: breaker            # 不通过就意味着论点被打破；watch 只是亮一个提醒
  covers: [pricing_power, moat]
  metric: gross_margin         # 在 spec/metrics.yml 中定义，从 XBRL 计算
  fail_if: below 55% for two consecutive quarters
  rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}
  warn_if: below 58%
  effective_from: FY2027Q1     # 从这一期开始判定；业绩公开之后不再修改
  baseline: {value: 62, unit: "%", period: FY2026, source: ACME-10K-FY2026#Item8}
```

定性测试把规则换成一个 `question`、要读的文件和 `lookback`；过期测试在论点的某一部分超过规定的季度数没有重新审视时判为不通过。包内的示例档案（[`fixtures/workspace`](../src/thesis_ci/fixtures/workspace)，全部为虚构数据）展示了每一种文件。一个用 thesis-ci 运转的真实档案公开在 [owners-office](https://github.com/kentian742-creator/owners-office)。

## 规范

规范（v0.2）在 [`spec/`](../spec/)：[`SPEC.md`](../spec/SPEC.md)（中文版在 [`zh-CN/spec/SPEC.md`](spec/SPEC.md)）、16 个 JSON Schema、检查登记表 [`checks.yml`](../spec/checks.yml)（35 项检查）、指标登记表 [`metrics.yml`](../spec/metrics.yml)，以及 [`templates/lynch/`](../spec/templates/lynch/) 下的六个监控模板，对应彼得·林奇的六类公司。`SPEC.md` 与机器可读文件不一致时，以机器可读文件为准。

一个档案是一对仓库。公开仓库（`repo.yml` 中 `visibility: public`）存放论点、预注册、预测和信件；私有仓库（`visibility: private`）存放价值区间、决策备忘录和带金额的决策日志。`thesis-ci lint` 读取 `repo.yml` 决定运行哪些检查。每次预注册是三个文件：冻结的条目 `prereg/<period>.yml`（主人的覆盖写在 `<period>-owner.yml`）、时间戳证明 `<period>.yml.ots` 和结算文件 `<period>.settlement.yml`（SPEC 2.1）。档案以英文为主：关键文档的中文版放在 `zh-CN/<同一路径>`，其余文件都用英文（SPEC 8.5）。

## 快速开始

```bash
pip install git+https://github.com/kentian742-creator/thesis-ci
thesis-ci lint path/to/archive                  # 按 repo.yml 的 visibility 运行适用的检查
thesis-ci lint path/to/private --counterpart path/to/public   # 私有仓库可读取公开仓库的决策权配置
thesis-ci lint path/to/archive --format json --today 2026-09-24 --only C-SRC-TAG C-STORY
thesis-ci lint . --expect-visibility public     # 按公开仓库检查；repo.yml 若不是 public 就报错
thesis-ci lint . --base-ref origin/main --period FY2027Q1   # 业绩入库后的 PR：当期有效的测试门槛不得改动
thesis-ci checks                                # 列出全部检查：范围、级别、是否实现、自检结果
thesis-ci selftest                              # 每项检查都必须抓住违规样例、放过合规样例
thesis-ci staleness path/to/archive --today 2026-09-24   # 计算每个 thesis.yml 的时效测试
thesis-ci brier path/to/archive/forecasts/2026.yml       # Brier 分与校准分箱（按领域、按账本）
```

- `lint` 有错误级别的发现时退出码为 1，只有警告时为 0；参数错误为 2。
- `--expect-visibility public|private`：不管 `repo.yml` 怎么写，都按这个可见性运行检查，写得不一致时报 `C-SCHEMA` 错误。公开仓库的 CI 应当带上 `--expect-visibility public`，否则把 `repo.yml` 改成 `private` 就能跳过全部公开检查。
- `--base-ref <git 引用> --period FY<年>Q<季>`：把 `thesis.yml` 的测试与该引用比较（`C-TEST-FROZEN`），当期有效的测试不得改门槛或被删除。两个参数缺一个时这项检查空过。
- `--format json` 输出 `{"repo", "visibility", "errors": [{"check","file","line","message"}], "warnings": [...], "checks_run": [...]}`。
- `staleness` 有测试失败时退出码为 1。`brier` 只计已结算（`happened` / `not_happened`）的预测：BS = mean((p − o)²)，每条都报 50% 得 0.25。

在 GitHub Actions 中使用：

```yaml
- uses: actions/checkout@v5
- uses: kentian742-creator/thesis-ci@v0.3.0
  with:
    path: .                      # 档案仓库根目录
    # counterpart: ../private    # 可选：另一侧仓库
    expect-visibility: public    # 可选，建议公开仓库使用
    # base-ref: origin/main      # 可选：与 period 一起用于 C-TEST-FROZEN（checkout 需 fetch-depth: 0）
    # period: FY2027Q1
```

## 检查一览

| id | 范围 | 级别 | 检查 |
| --- | --- | --- | --- |
| `C-SCHEMA` | both | error | 文件符合 schema |
| `C-SRC-TAG` | both | error | Markdown 事实数字带来源标签 |
| `C-SRC-FACT` | both | error | YAML 事实带可解析的来源 |
| `C-SRC-ACCESSION` | both | warning | 定期报告来源带 EDGAR 登记号 |
| `C-PUBLIC-NO-VALUATION` | public | error | 公开仓库不含价值区间与价格区间 |
| `C-PUBLIC-NO-ADVICE` | public | error | 公开内容不含买卖建议 |
| `C-PUBLIC-NO-AMOUNTS` | public | error | 公开仓库不含持仓金额 |
| `C-NO-PRICE-FEED` | both | error | 不抓取日常股价 |
| `C-NO-TRADING` | both | error | 不执行任何交易 |
| `C-LLM-ENTRY` | both | error | 模型调用只在 pipeline/llm.py |
| `C-NO-SECRETS` | both | error | 不提交密钥 |
| `C-TESTS-MIN` | public | error | 每家公司至少 5 条测试，三类齐全 |
| `C-TESTS-COVERAGE` | public | error | 测试覆盖企业质量的试金石 |
| `C-TESTS-CAPALLOC` | public | error | 测试覆盖资本配置 |
| `C-TEST-METRIC` | public | error | 定量测试可执行 |
| `C-TEST-QUAL-EVIDENCE` | public | error | 定性测试要求独立判定与出处 |
| `C-STALENESS` | public | warning | 时效测试可计算且当前不过期 |
| `C-DEPENDS` | public | error | 行业依赖可解析、行业模块中立 |
| `C-STORY` | public | error | 两分钟故事存在且够短 |
| `C-RATING-ORDER` | both | error | 质量第一，管理层第二，估值第三 |
| `C-CONCENTRATION` | both | error | 集中持有与入选门槛 |
| `C-DISCOUNT-RATE` | private | error | 折现率 = 10 年期国债收益率 + 本公司溢价，写明依据 |
| `C-SELL-REASONS` | both | error | 只因永久性恶化或明显更好的机会卖出 |
| `C-HURDLE` | private | error | 长期预期过得了伯克希尔或 VOO 这条比较线 |
| `C-SINGLE-ORDER` | both | error | 一次下单建仓 |
| `C-DEFAULT-HOLD` | both | error | 资金事项默认不动 |
| `C-DECISION-RIGHTS` | public | error | 三级决策权配置自洽 |
| `C-CONSTITUTION-MAP` | public | error | 宪法每条规则都有可执行检查 |
| `C-AGENT-ISOLATION` | public | error | 审计与盲推的可见范围隔离 |
| `C-PREREG-TIMING` | public | error | 预注册在业绩首次公开之前合并 |
| `C-PREREG-IMMUTABLE` | public | error | 截止之后预注册不可改 |
| `C-TRUST-WRITE` | public | warning | 信任等级与复核日期由流水线维护 |
| `C-TEST-FROZEN` | public | error | 业绩出来之后不改当期门槛 |
| `C-PROMPT-ISOLATION` | private | warning | 提示词的输入不越过角色的可见范围 |
| `C-LANGUAGE` | both | error | 英文文件不含中日韩文字 |

每项检查的完整定义见 [`spec/checks.yml`](../spec/checks.yml)。

## 参考：检查如何读取档案

- **出处（SPEC 3.1、3.4）。** 中文、日文、韩文按 `。！？；` 和换行切分句子；英文按后接空白的 `.`、`!`、`?`、`;` 切分，小数点（`3.5%`）、缩写（`U.S.`、`Inc.`、`e.g.`、`vs.`、`No. 1`）后的句点和来源标签内的句点不算句末，英文段落内的换行不结束句子（英文常折行），空行、标题、列表项、表格行和引用块则结束句子；紧跟在句点后的标签（`16%.[src:TAG]`）属于前一句。含事实数字（`$495`、`16%`、`1,020 亿美元`、`1.04×`、`45 个百分点` 等）的句子必须带 `[src:TAG#LOCATOR]`。SPEC 3.4 所列单位的其他写法同样算事实数字：英文（`16 percent`、`30 basis points`、`40 cents`、`1.2 trillion`、`25x`）、其他货币（`€500`、`RMB 5`、`5 港元`、`1.50 比索`）和数量级（`5 千美元`、`3 百亿`）；数字和单位之间可以有任意空白，零宽字符不能把它们隔开。年份、日期、季度、`FY2026`、章节号不算事实数字（`2019-06 百亿补贴` 这类“日期 + 名称”也不算）；front matter、代码块、行内代码和链接 URL 不参与判断。英文单位不分大小写（`3 bn`、`16 PERCENT`），`5 USD`、`5 dollars` 也算；英文日期（`September 30, 2026`）、`3Q26` 这样的期间和章节号不算。Markdown 检查覆盖 `companies/`、`industries/`、`letters/` 和根目录的 `mistakes.md`，以及它们在 `zh-CN/` 下的中文版。标签先在文件所在目录及上级目录的 `sources.yml` 中查找，最后是仓库根目录（`zh-CN/` 下的文件从它所翻译的文件的目录查起）。
- **YAML 自由文本。** `claim`、`summary`、`category_rationale`、`pillars[].claim`、`permanent_loss_paths`、`structure`、`implication`、`observable`、`title`、`note`、`statement`、`label` 中的事实数字同样要带标签；`fail_if`、`warn_if`、`threshold`、`question`、`rule` 是事先写下的判定标准，不需要出处。`companies/` 和 `industries/` 下任何 YAML（包括 `updates/` 和多文档流的每个文档）中的 `source` 字段都必须能解析。
- **YAML 日期**在 JSON Schema 校验前转成 ISO 字符串，并启用 `format` 校验（例如 `2026-02-30` 会报错）。重复的键（PyYAML 会静默保留最后一个值）是 `C-SCHEMA` 错误；`companies/<TICKER>/` 下文件的 `company` 必须等于目录名，`industry.yml` 的 `id` 必须等于目录名，同一个 `sources.yml` 里标签不得重复；带 `--counterpart` 时两个仓库的 `visibility` 不得相同。
- **扫描范围。** 除 `.git`、虚拟环境、缓存和 `build/`、`dist/` 外，所有目录都扫描，包括 `.claude/` 这类隐藏目录（隐藏目录同样会被发布）。在 git 工作区里只扫描 git 会发布的文件（已跟踪的，以及未被忽略的新文件），所以本地被忽略的 `.env`、`logs/` 不会让 lint 失败；若档案本身被外层仓库忽略，则扫描全部文件。
- **公开仓库的键与用语。** 键检查覆盖每个 YAML 文档（`---` 之后的文档也算）和 JSON 数据文件，键名先归一（`valueRanges`、`Value-Ranges` 都算 `value_ranges`）。用语表与 00 §H4 一字不差，其他写法（`推荐买入`、`buy rating`、`I recommend buying` 等）另由模式匹配发现，0.3.0 起包括整张表的英文说法（`implied return`、`price grade`、带数字的 `central value` 或 `fair range`、`rated a Buy`、`investors should sell`、`add to the position`、`buy the dip` 等，SPEC 7.5）；与中文一样，否定句不例外（`we do not recommend buying` 同样报错，00 §H4）；公司回购自己的股票（`buyback`、`the company should buy back stock`）和产品名称不算建议。扫描 `companies/`（含 `updates/`）、`industries/`、`forecasts/`、`letters/`、根目录的 `mistakes.md`、进度文件 `docs/STATUS.md` 与 `CLAUDE.md`，以及它们在 `zh-CN/` 下的中文版；谈价格或估值的句子里代码旁的价格评级（`AXP B− → C`）即为错误。用语检查先做 NFKC、去掉零宽字符并把繁体换成简体，中文词之间允许空白，英文词之间允许空格、`_` 或 `-`，所以 `建議買入`、`建议 买入`、`strong-buy` 都会被发现；`overweight`、`underweight` 只在作为评级时算建议（`Rating: Overweight`、`rated Overweight`），`overweight adults` 不算。以股价为输入的倍数（`市盈率`、`P/E`、`市值`、`自由现金流收益率`、`FCF yield`，以及 `price-to-earnings`、`trades at 25 times earnings` 等英文写法）与数字出现在同一句时报错；年份、日期、期间、章节号和一位数的编号不算数字。
- **两分钟故事（SPEC 5）。** 用中文、日文或韩文写的故事正文不超过 700 个字符；用英文写的不超过 350 个词，大约是朗读两分钟的长度。来源标签、标记和链接地址不计。
- **英文优先（SPEC 8.5）。** `C-LANGUAGE` 报告根目录 `zh-CN/` 以外含中日韩字符（包括标点和全角字符）的每个文本文件，每个文件一条，指向第一处这样的行。测试与测试数据可能需要中文文本，不在此列；`sources.yml` 条目的 `title_original` 照录来源的原文标题，也不在此列。
- **输入尚不存在时检查空过**（没有备忘录、没有预注册等）；公开仓库必须有 `constitution/rules.yml` 和 `constitution/decision-rights.yml`。
- **自检。** `thesis-ci selftest` 把包内的示例档案（[`src/thesis_ci/fixtures/workspace`](../src/thesis_ci/fixtures/workspace)，全部为虚构数据）复制到临时目录，对每项检查施加至少一个违规改动。`C-CONSTITUTION-MAP` 要求宪法引用的每项检查都通过自检，并且 `spec/checks.yml` 中注明“Constitution rule N”（宪法第 N 条）的检查都被 `rules.yml` 的某条规则引用。

## 尚未包含（按阶段计划）

- **EDGAR 监听**：定时查询 EDGAR submissions 接口、新文件自动开 PR（第 2 阶段）。
- **结算**：财报入库后按事先的判定标准结算预注册和言行账本（第 1 阶段半自动，第 2–3 阶段自动化）。
- **OpenTimestamps 打时间戳**：由流水线完成；`C-PREREG-IMMUTABLE` 只检查截止之后证明是否存在，并在装有 `ots` 客户端时核验。
- 校准看板、行业路标触发的复核 issue：第 4 阶段，与 v1.0 一起发布。

规范在跑完两个财报季之前保持 v0.x，不兼容的改动逐条记入 [CHANGELOG](../CHANGELOG.md)。

## 开发

```bash
pip install -e ".[test]"
pytest -q
thesis-ci selftest
```

新增一项检查：先在 `spec/checks.yml` 登记，再在 `src/thesis_ci/checks/` 中用 `@check("C-...")` 实现，
在 `src/thesis_ci/selftest.py` 中加至少一个违规样例，并写一个文档字符串含检查 id 的单元测试。
测试会核对登记表与实现一一对应。

## 许可

代码以 [MIT](../LICENSE) 许可发布；`spec/` 和文档（包括 `zh-CN/` 下的中文版）以 [CC BY 4.0](../LICENSE-SPEC.md) 许可发布。
