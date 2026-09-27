> 中文版。英文原文：[README.md](../README.md)

# thesis-ci

**投资论点的持续集成。** thesis-ci 把写成文字的论点变成可能不通过的测试，检查每个数字是否引用了申报文件，在某一季度业绩公开后冻结这一季度的门槛，并给财报前登记的预测打分。

> **不构成投资建议。** thesis-ci 不抓取股价，不给买卖信号，也不执行任何交易。

## 为什么

大多数投资论点是一段文字：写起来容易，检查起来难，事实一变就被悄悄改写。thesis-ci 让论点像代码一样运转：

| 软件工程 | 投资（用 thesis-ci） |
| --- | --- |
| 源代码 | `thesis.yml`：论点、对生意质量、管理层和资本配置的评级、所依赖的行业模块，以及测试 |
| 单元测试 | 论点测试，每一条都在数据出来之前写好（三种，见下） |
| CI | `thesis-ci evaluate` 用一个季度的读数判定量化测试；某一期的业绩一旦公开，CI 就拒绝修改这一期的门槛（对照 git 历史检查） |
| Lint | `thesis-ci lint`：每个数字都引用一手来源，公开文件会被扫描估值数字和买卖用语，你写下的投资规则（`constitution/rules.yml`）每一条都有对应的检查 |
| 测试报告 | `thesis-ci brier` 给已结算的预测打分：Brier 分数和分领域校准，系统的预测与主人的覆盖分开计算 |

三种测试：

- **量化测试：** 一个必须守住的数字，从公司的 SEC XBRL 数据计算，或从申报文件的指定行读出；门槛、方向和连续期数事先写好。
- **定性测试：** 一道是非题，由另一个模型读指定文件作答，并且必须引用证据。thesis-ci 规定问题、文件和回看多远；模型调用属于你自己的流水线。
- **过期测试：** 论点的某一部分超过规定的季度数没有重新审视，就判为不通过。

它面向写成文字的论点、并希望这些论点能被检验的个人投资者和小团队；也面向需要护栏的大模型研究流水线：事实必须有出处，公开输出不含建议，审计的模型看不到起草模型的输入。

**默认带着观点。** 有几项检查编码的是一位投资者写下的规则，也就是 thesis-ci 诞生地 [Owner's Office](https://github.com/kentian742-creator/owners-office) 的宪法：持仓保持集中，一次下单建仓，卖出必须给出允许的理由，买入必须越过比较线（伯克希尔·哈撒韦，或标普 500 指数基金），折现率等于国债收益率加公司溢价。输入不存在时（没有决策备忘录、没有估值）这些检查空过；`--only` 可以只运行你选的检查；关闭这套投资规则的开关在计划中。

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

包内的示例档案（[`fixtures/workspace`](../src/thesis_ci/fixtures/workspace)，全部为虚构数据）展示了每一种文件。一个用 thesis-ci 运转的真实档案公开在 [owners-office](https://github.com/kentian742-creator/owners-office)。

## 规范

规范（v0.2）在 [`spec/`](../spec/)：[`SPEC.md`](../spec/SPEC.md)（中文版在 [`zh-CN/spec/SPEC.md`](spec/SPEC.md)）、18 个 JSON Schema、检查登记表 [`checks.yml`](../spec/checks.yml)（35 项检查）、指标登记表 [`metrics.yml`](../spec/metrics.yml)，以及 [`templates/lynch/`](../spec/templates/lynch/) 下的六个监控模板，对应彼得·林奇的六类公司（缓慢增长型、稳定增长型、快速增长型、周期型、困境反转型和资产型）。`SPEC.md` 与机器可读文件不一致时，以机器可读文件为准。

你的研究放在一个档案里：一个公开仓库（论点、预测、信件），如果你还要保存估值或仓位大小，旁边再放一个私有仓库（各自 `repo.yml` 里的 `visibility` 说明哪个是哪个）。`thesis-ci lint` 读取 `repo.yml` 决定运行哪些检查。每次预注册是三个文件（SPEC 2.1）：

- `prereg/<period>.yml`：预测本身，截止之后冻结（主人的覆盖写在 `<period>-owner.yml`）；
- `<period>.yml.ots`：OpenTimestamps 证明，说明这个文件在业绩公布之前就已存在；
- `<period>.settlement.yml`：按事先写好的标准做的结算。

档案以英文为主：关键文档的中文版放在 `zh-CN/<同一路径>`，其余文件都用英文（SPEC 8.5）。

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
thesis-ci brier path/to/archive/forecasts/2026.yml       # Brier 分数和校准：按领域，系统与主人分开
thesis-ci evaluate path/to/archive --company ACME --period FY2027Q1 --readings readings.yml   # 判定定量测试（SPEC 4.5）
```

- `lint` 有错误级别的发现时退出码为 1，只有警告时为 0；参数错误为 2。
- `--expect-visibility public|private`：不管 `repo.yml` 怎么写，都按这个可见性运行检查，写得不一致时报 `C-SCHEMA` 错误。公开仓库的 CI 应当带上 `--expect-visibility public`，否则把 `repo.yml` 改成 `private` 就能跳过全部公开检查。
- `--base-ref <git 引用> --period FY<年>Q<季>`：把 `thesis.yml` 的测试与该引用比较（`C-TEST-FROZEN`），当期有效的测试不得改门槛或被删除。两个参数缺一个时这项检查空过。
- `--format json` 输出 `{"repo", "visibility", "errors": [{"check","file","line","message"}], "warnings": [...], "checks_run": [...]}`。
- `staleness` 有测试失败时退出码为 1。`brier` 只计已结算（`happened` / `not_happened`）的预测：BS = mean((p − o)²)，每条都报 50% 得 0.25。
- `evaluate` 输出一家公司一个财季的 `ci_results`（YAML；`--format json` 时为 JSON），只要运行完成就以 0 退出：测试失败是结果，不是错误。

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
| `C-PUBLIC-NO-ADVICE` | public | error | 扫描公开文件中的买卖用语 |
| `C-PUBLIC-NO-AMOUNTS` | public | error | 公开仓库不含持仓金额 |
| `C-NO-PRICE-FEED` | both | error | 代码里没有每日股价来源（静态扫描） |
| `C-NO-TRADING` | both | error | 代码里没有券商或下单接口（静态扫描） |
| `C-LLM-ENTRY` | both | error | 所有模型调用都经过同一个模块 pipeline/llm.py |
| `C-NO-SECRETS` | both | error | 不提交密钥 |
| `C-TESTS-MIN` | public | error | 每家公司至少 5 条测试，三类齐全 |
| `C-TESTS-COVERAGE` | public | error | 测试覆盖护城河、定价权、资本回报和自由现金流 |
| `C-TESTS-CAPALLOC` | public | error | 测试覆盖资本配置 |
| `C-TEST-METRIC` | public | error | 定量测试可执行 |
| `C-TEST-QUAL-EVIDENCE` | public | error | 定性测试要求独立判定与出处 |
| `C-STALENESS` | public | warning | 时效测试可计算且当前不过期 |
| `C-DEPENDS` | public | error | 行业依赖可解析、行业模块中立 |
| `C-STORY` | public | error | 每家公司都有两分钟故事（英文不超过 350 词，中日韩文字不超过 700 字） |
| `C-RATING-ORDER` | both | error | 质量第一，管理层第二，估值第三 |
| `C-CONCENTRATION` | both | error | 持仓保持集中，新仓位越过入选门槛 |
| `C-DISCOUNT-RATE` | private | error | 折现率 = 10 年期国债收益率 + 本公司溢价，写明依据 |
| `C-SELL-REASONS` | both | error | 卖出给出允许的理由：永久恶化或明显更好的机会 |
| `C-HURDLE` | private | error | 买入越过比较线：先是伯克希尔·哈撒韦，再是标普 500 基金 |
| `C-SINGLE-ORDER` | both | error | 一个仓位一次下单建成 |
| `C-DEFAULT-HOLD` | both | error | 涉及资金的决定默认不动 |
| `C-DECISION-RIGHTS` | public | error | 三级决策权（自行决定、先做后报、主人决定）配置自洽 |
| `C-CONSTITUTION-MAP` | public | error | 宪法每条规则都有可执行检查 |
| `C-AGENT-ISOLATION` | public | error | 审计和盲读看不到它们需要独立判断的对象 |
| `C-PREREG-TIMING` | public | error | 预注册在业绩首次公开之前合并 |
| `C-PREREG-IMMUTABLE` | public | error | 截止之后预注册不可改 |
| `C-TRUST-WRITE` | public | warning | 只有流水线能修改信任等级和复核日期 |
| `C-TEST-FROZEN` | public | error | 业绩出来之后不改当期门槛 |
| `C-PROMPT-ISOLATION` | private | warning | 提示词的输入不越过角色的可见范围 |
| `C-LANGUAGE` | both | error | 英文文件不含中日韩文字 |

每项检查的完整定义见 [`spec/checks.yml`](../spec/checks.yml)。

各项检查如何读取档案（断句、什么算事实数字、扫描哪些文件、用语归一、故事长度、语言检查、空过和自检）见 [docs/reference.md](docs/reference.md)。

## 尚未包含

- **EDGAR 监听**：定时查询 EDGAR submissions 接口，有新文件就自动开 PR（计划中）。
- **结算**：按事先写好的标准结算预注册和言行账本；文件格式已有规定（`prereg-settlement.schema.json`），结算本身由你的流水线完成。
- **投资规则开关**：让编码了一位投资者规则的那几项检查可以关闭。
- 校准看板、行业路标触发的复核 issue：与 v1.0 一起发布。

不在范围内：thesis-ci 不打时间戳。请用 OpenTimestamps 的 `ots` 客户端给预注册打时间戳；`C-PREREG-IMMUTABLE` 检查截止之后证明是否存在，并在装有 `ots` 时核验。

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
