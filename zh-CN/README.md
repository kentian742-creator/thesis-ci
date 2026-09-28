> 中文版。英文原文：[README.md](../README.md)

# thesis-ci

[![CI](https://github.com/kentian742-creator/thesis-ci/actions/workflows/ci.yml/badge.svg)](https://github.com/kentian742-creator/thesis-ci/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/thesis-ci)](https://pypi.org/project/thesis-ci/)
[![Python](https://img.shields.io/pypi/pyversions/thesis-ci)](https://pypi.org/project/thesis-ci/)
[![Code: MIT](https://img.shields.io/badge/code-MIT-blue)](../LICENSE)
[![Spec: CC BY 4.0](https://img.shields.io/badge/spec-CC%20BY%204.0-lightgrey)](../LICENSE-SPEC.md)

**投资论点的持续集成。** thesis-ci 把写成文字的论点变成可能不通过的测试，检查每个数字是否引用了申报文件，在某一季度业绩公开后冻结这一季度的门槛，并给财报前登记的预测打分。

> **不构成投资建议。** thesis-ci 不抓取股价，不给买卖信号，也不执行任何交易。

## 两分钟试用

需要 Python 3.10 或更高版本；不需要账号、API 密钥，也不调用任何模型。

```bash
pip install thesis-ci
thesis-ci init my-archive     # 一个只含虚构公司 ACME 的档案
thesis-ci lint my-archive
```

```text
thesis-ci: 0 error(s), 0 warning(s); 21 checks (profiles: core) on public repo .../my-archive
```

再加一句公开档案里不允许出现的话，重新检查：

```bash
echo 'Revenue grew 40% last year, so this is a strong buy with a price target of $120.' >> my-archive/companies/ACME/story.md
thesis-ci lint my-archive
```

```text
companies/ACME/story.md:16: error [C-PUBLIC-NO-ADVICE] buy/sell advice wording: 'strong buy'
companies/ACME/story.md:16: error [C-PUBLIC-NO-VALUATION] price-range wording in public content: 'price target'
companies/ACME/story.md:16: error [C-SRC-TAG] fact number '40%' has no [src:] tag in its sentence: Revenue grew 40% last year, so this is a strong buy with a …
thesis-ci: 3 error(s), 0 warning(s); 21 checks (profiles: core) on public repo .../my-archive
```

40% 没有引用任何申报文件，"strong buy" 是买卖建议，"price target" 是估值。测试格式、在 GitHub Actions 里跑 CI 等其余内容，见下面的[快速开始](#快速开始)。

## 为什么

大多数投资论点是一段文字：写起来容易，检查起来难，事实一变就被悄悄改写。thesis-ci 让论点像代码一样运转：

| 软件工程 | 投资（用 thesis-ci） |
| --- | --- |
| 源代码 | `thesis.yml`：论点、对生意质量、管理层和资本配置的评级、所依赖的行业模块，以及测试 |
| 单元测试 | 论点测试，每一条都在数据出来之前写好（三种，见下） |
| CI | `thesis-ci evaluate` 用一个季度的读数判定量化测试；某一期的业绩一旦公开，CI 就拒绝修改这一期的门槛（对照 git 历史检查） |
| Lint | `thesis-ci lint`：每个数字都引用一手来源，公开文件会被扫描估值数字和买卖用语，运行哪几组检查（检查组）由你选择 |
| 测试报告 | `thesis-ci brier` 给已结算的预测打分：Brier 分数和分领域校准，系统的预测与主人的覆盖分开计算 |

三种测试：

- **量化测试：** 一个必须守住的数字，从公司的 SEC XBRL 数据计算，或从申报文件的指定行读出；门槛、方向和连续期数事先写好。
- **定性测试：** 一道是非题，由另一个模型读指定文件作答，并且必须引用证据。thesis-ci 规定问题、文件和回看多远；模型调用属于你自己的流水线。
- **过期测试：** 论点的某一部分超过规定的季度数没有重新审视，就判为不通过。

它面向写成文字的论点、并希望这些论点能被检验的个人投资者和小团队；也面向需要护栏的大模型研究流水线：事实必须有出处，公开输出不含建议，审计的模型看不到起草模型的输入。

## 检查组

每项检查属于三个检查组（profile）之一，档案自己选择运行哪几组：

- **`core`**：适用于任何论点档案。文件符合 schema；每个数字都引用来源；论点测试完整、可执行，合起来覆盖护城河、定价权、资本回报、自由现金流、资本配置和管理层；复核没有逾期；每家公司都有一篇简短的两分钟故事；预注册在业绩出来之前完成，之后不再改动；业绩公开后门槛冻结；不提交密钥、不抓取股价、不下单；公开档案里没有估值、股价、持仓金额或买卖建议。
- **`pipeline`**：适用于由大模型研究流水线写成的档案。所有模型调用都经过同一个模块；审计和盲读看不到它们要评判的草稿和结论；每个提示词只把角色可以看的内容交给它；只有流水线能修改信任等级和复核日期。
- **`owners-office`**：一位投资者的规则，即 thesis-ci 诞生地 [Owner's Office](https://github.com/kentian742-creator/owners-office) 的宪法。持仓保持集中，新仓位至少占组合的 10%；一个仓位一次下单建成；卖出必须给出允许的理由；买入必须越过比较线（先是伯克希尔·哈撒韦，再是标普 500 指数基金）；折现率等于 10 年期国债收益率加公司溢价；涉及资金的决定默认不动，并由主人决定；宪法每条规则都对应一项检查；`zh-CN/` 以外的文件都用英文。没有备忘录和估值时，它对备忘录和估值的检查空过，但公开档案必须有 `constitution/rules.yml` 和 `constitution/decision-rights.yml`。

在 `repo.yml` 中选择，例如 `profiles: [core]` 或 `profiles: [core, pipeline]`。大多数档案用 `core` 就够了；研究由模型撰写时再加 `pipeline`；只有把那套规则当作自己的规则时才加 `owners-office`。`thesis-ci init` 新建的档案写的是 `profiles: [core]`。`repo.yml` 没有 `profiles` 这一行时运行全部检查组，这也是引入检查组之前 thesis-ci 的行为。`thesis-ci checks` 显示每项检查所属的检查组，[检查一览](#检查一览)的表格也列出了它们。

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

你的研究放在一个档案里：一个公开仓库（论点、预测、信件），如果你还要保存估值或仓位大小，旁边再放一个私有仓库（各自 `repo.yml` 里的 `visibility` 说明哪个是哪个）。`thesis-ci lint` 读取 `repo.yml` 中的 `visibility` 和 `profiles` 决定运行哪些检查。每次预注册是三个文件（SPEC 2.1）：

- `prereg/<period>.yml`：预测本身，截止之后冻结（主人的覆盖写在 `<period>-owner.yml`）；
- `<period>.yml.ots`：OpenTimestamps 证明，说明这个文件在业绩公布之前就已存在；
- `<period>.settlement.yml`：按事先写好的标准做的结算。

使用 `owners-office` 检查组时，档案以英文为主：关键文档的中文版放在 `zh-CN/<同一路径>`，其余文件都用英文（SPEC 8.5）。

## 快速开始

```bash
pip install thesis-ci                           # 从 PyPI 安装（或：pip install git+https://github.com/kentian742-creator/thesis-ci）
thesis-ci init my-archive                       # 新建一个档案，含一家虚构的示例公司，profiles: [core]
thesis-ci lint my-archive                       # 0 error(s), 0 warning(s)
thesis-ci lint path/to/archive                  # 运行 repo.yml 所选检查组中适用于其 visibility 的检查
thesis-ci lint path/to/private --counterpart path/to/public   # 私有仓库可读取公开仓库的决策权配置
thesis-ci lint path/to/archive --format json --today 2026-09-24 --only C-SRC-TAG C-STORY
thesis-ci lint . --expect-visibility public     # 按公开仓库检查；repo.yml 若不是 public 就报错
thesis-ci lint . --profile core                 # 不管 repo.yml 怎么写，只运行 core 检查
thesis-ci lint . --base-ref origin/main --period FY2027Q1   # 业绩入库后的 PR：当期有效的测试门槛不得改动
thesis-ci checks                                # 列出全部检查：检查组、范围、级别、是否实现、自检结果
thesis-ci selftest                              # 每项检查都必须抓住违规样例、放过合规样例
thesis-ci staleness path/to/archive --today 2026-09-24   # 计算每个 thesis.yml 的时效测试
thesis-ci brier path/to/archive/forecasts/2026.yml       # Brier 分数和校准：按领域，系统与主人分开
thesis-ci evaluate path/to/archive --company ACME --period FY2027Q1 --readings readings.yml   # 判定定量测试（SPEC 4.5）
```

- `init <目录> [--visibility public|private] [--profiles core,pipeline,owners-office]` 写入 `repo.yml`、一份简短的 `README.md` 和一家示例公司 `companies/ACME/`（`thesis.yml` 含五条测试，即最低数量，其中有一条定量测试、一条定性测试和一条时效测试；`story.md`；`sources.yml`）。数据都是虚构的。它从不覆盖文件：只要其中任何一个文件已经存在，就什么也不写，并以 2 退出。选了 `owners-office` 的公开档案还会得到这个检查组必需的两个文件：`constitution/rules.yml` 和 `constitution/decision-rights.yml`。
- `lint` 有错误级别的发现时退出码为 1，只有警告时为 0；参数错误为 2。
- `--profile core,pipeline`：运行这几个检查组，而不是 `repo.yml` 指定的那些（可以重复这个参数，也可以用逗号分隔）。`--only` 只运行它列出的检查，不管检查组。
- `--expect-visibility public|private`：不管 `repo.yml` 怎么写，都按这个可见性运行检查，写得不一致时报 `C-SCHEMA` 错误。公开仓库的 CI 应当带上 `--expect-visibility public`，否则把 `repo.yml` 改成 `private` 就能跳过全部公开检查。出于同样的原因，CI 可以用 `--profile` 固定检查组，这样从 `repo.yml` 删掉一个检查组也关不掉它的检查。
- `--base-ref <git 引用> --period FY<年>Q<季>`：把 `thesis.yml` 的测试与该引用比较（`C-TEST-FROZEN`），当期有效的测试不得改门槛或被删除。两个参数缺一个时这项检查空过。
- `--format json` 输出 `{"repo", "visibility", "errors": [{"check","file","line","message"}], "warnings": [...], "checks_run": [...]}`。
- `staleness` 有测试失败时退出码为 1。`brier` 只计已结算（`happened` / `not_happened`）的预测：BS = mean((p − o)²)，每条都报 50% 得 0.25。
- `evaluate` 输出一家公司一个财季的 `ci_results`（YAML；`--format json` 时为 JSON），只要运行完成就以 0 退出：测试失败是结果，不是错误。

在 GitHub Actions 中使用：

```yaml
- uses: actions/checkout@v5
- uses: kentian742-creator/thesis-ci@v0.5.1
  with:
    path: .                      # 档案仓库根目录
    # counterpart: ../private    # 可选：另一侧仓库
    expect-visibility: public    # 可选，建议公开仓库使用
    # profile: core              # 可选：不管 repo.yml 怎么写，都运行这些检查组
    # base-ref: origin/main      # 可选：与 period 一起用于 C-TEST-FROZEN（checkout 需 fetch-depth: 0）
    # period: FY2027Q1
```

## 检查一览

| id | 检查组 | 范围 | 级别 | 检查 |
| --- | --- | --- | --- | --- |
| `C-SCHEMA` | core | both | error | 文件符合 schema |
| `C-SRC-TAG` | core | both | error | Markdown 事实数字带来源标签 |
| `C-SRC-FACT` | core | both | error | YAML 事实带可解析的来源 |
| `C-SRC-ACCESSION` | core | both | warning | 定期报告来源带 EDGAR 登记号 |
| `C-PUBLIC-NO-VALUATION` | core | public | error | 公开仓库不含价值区间与价格区间 |
| `C-PUBLIC-NO-ADVICE` | core | public | error | 扫描公开文件中的买卖用语 |
| `C-PUBLIC-NO-AMOUNTS` | core | public | error | 公开仓库不含持仓金额 |
| `C-NO-PRICE-FEED` | core | both | error | 代码里没有每日股价来源（静态扫描） |
| `C-NO-TRADING` | core | both | error | 代码里没有券商或下单接口（静态扫描） |
| `C-LLM-ENTRY` | pipeline | both | error | 所有模型调用都经过同一个模块 pipeline/llm.py |
| `C-NO-SECRETS` | core | both | error | 不提交密钥 |
| `C-TESTS-MIN` | core | public | error | 每家公司至少 5 条测试，三类齐全 |
| `C-TESTS-COVERAGE` | core | public | error | 测试覆盖护城河、定价权、资本回报和自由现金流 |
| `C-TESTS-CAPALLOC` | core | public | error | 测试覆盖资本配置 |
| `C-TEST-METRIC` | core | public | error | 定量测试可执行 |
| `C-TEST-QUAL-EVIDENCE` | core | public | error | 定性测试要求独立判定与出处 |
| `C-STALENESS` | core | public | warning | 时效测试可计算且当前不过期 |
| `C-DEPENDS` | core | public | error | 行业依赖可解析、行业模块中立 |
| `C-STORY` | core | public | error | 每家公司都有两分钟故事（英文不超过 350 词，中日韩文字不超过 700 字） |
| `C-RATING-ORDER` | owners-office | both | error | 质量第一，管理层第二，估值第三 |
| `C-CONCENTRATION` | owners-office | both | error | 持仓保持集中，新仓位越过入选门槛 |
| `C-DISCOUNT-RATE` | owners-office | private | error | 折现率 = 10 年期国债收益率 + 本公司溢价，写明依据 |
| `C-SELL-REASONS` | owners-office | both | error | 卖出给出允许的理由：永久恶化或明显更好的机会 |
| `C-HURDLE` | owners-office | private | error | 买入越过比较线：先是伯克希尔·哈撒韦，再是标普 500 基金 |
| `C-SINGLE-ORDER` | owners-office | both | error | 一个仓位一次下单建成 |
| `C-DEFAULT-HOLD` | owners-office | both | error | 涉及资金的决定默认不动 |
| `C-DECISION-RIGHTS` | owners-office | public | error | 三级决策权（自行决定、先做后报、主人决定）配置自洽 |
| `C-CONSTITUTION-MAP` | owners-office | public | error | 宪法每条规则都有可执行检查 |
| `C-AGENT-ISOLATION` | pipeline | public | error | 审计和盲读看不到它们需要独立判断的对象 |
| `C-PREREG-TIMING` | core | public | error | 预注册在业绩首次公开之前合并 |
| `C-PREREG-IMMUTABLE` | core | public | error | 截止之后预注册不可改 |
| `C-TRUST-WRITE` | pipeline | public | warning | 只有流水线能修改信任等级和复核日期 |
| `C-TEST-FROZEN` | core | public | error | 业绩出来之后不改当期门槛 |
| `C-PROMPT-ISOLATION` | pipeline | private | warning | 提示词的输入不越过角色的可见范围 |
| `C-LANGUAGE` | owners-office | both | error | 英文文件不含中日韩文字 |

检查组为 `core`、`pipeline` 或 `owners-office`（见[检查组](#检查组)）。范围为 `public`、`private`、`both` 或 `workspace`（只在带 `--counterpart` 时运行）。每项检查的完整定义见 [`spec/checks.yml`](../spec/checks.yml)，SPEC 8.6 说明了几项边界情形的检查为什么归入各自的检查组。

各项检查如何读取档案（断句、什么算事实数字、扫描哪些文件、用语归一、故事长度、语言检查、空过和自检）见 [docs/reference.md](docs/reference.md)。

## 尚未包含

- **EDGAR 监听**：定时查询 EDGAR submissions 接口，有新文件就自动开 PR（计划中）。
- **结算**：按事先写好的标准结算预注册和言行账本；文件格式已有规定（`prereg-settlement.schema.json`），结算本身由你的流水线完成。
- 校准看板、行业路标触发的复核 issue：与 v1.0 一起发布。

不在范围内：thesis-ci 不打时间戳。请用 OpenTimestamps 的 `ots` 客户端给预注册打时间戳；`C-PREREG-IMMUTABLE` 检查截止之后证明是否存在，并在装有 `ots` 时核验。

规范在跑完两个财报季之前保持 v0.x，不兼容的改动逐条记入 [CHANGELOG](../CHANGELOG.md)。

## 反馈

问题、想法，以及你用 thesis-ci 搭建的档案，欢迎发到 [Discussions](https://github.com/kentian742-creator/thesis-ci/discussions)。某项检查误报或漏报都算缺陷：请提交 [issue](https://github.com/kentian742-creator/thesis-ci/issues)，附一个能复现问题的最小档案（见 [CONTRIBUTING.md](../CONTRIBUTING.md)）。

## 开发

```bash
pip install -e ".[test]"
pytest -q
thesis-ci selftest
```

新增一项检查：先在 `spec/checks.yml` 登记并写明所属检查组，再在 `src/thesis_ci/checks/` 中用 `@check("C-...")` 实现，
在 `src/thesis_ci/selftest.py` 中加至少一个违规样例，写一个文档字符串含检查 id 的单元测试，
并把它列进本 README 和 SPEC 8.6 的检查表（及其英文版）。测试会核对登记表、实现和这些表格一一对应。

提问题、修改规范和发版的流程见 [CONTRIBUTING.md](../CONTRIBUTING.md)（英文）。

## 许可

代码以 [MIT](../LICENSE) 许可发布；`spec/` 和文档（包括 `zh-CN/` 下的中文版）以 [CC BY 4.0](../LICENSE-SPEC.md) 许可发布。
