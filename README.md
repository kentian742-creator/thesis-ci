# thesis-ci

**论点即代码（thesis as code）。** 把投资论点当作软件项目来维护，并用 CI 检查它。
*English version below.*

> 本项目不构成投资建议。thesis-ci 不抓取股价、不产生买卖信号、不执行任何交易。

## 中文

### 这是什么

thesis-ci 是一个开源的格式规范和检查工具，用来维护“所有者视角”的企业论点档案：

| 软件工程 | 在 thesis-ci 里 |
| --- | --- |
| 源代码 | `thesis.yml`：一家公司的论点、评级、依赖的行业和论点测试 |
| 单元测试 | thesis tests：事先写好门槛的定量、定性和时效测试（“什么会证明我错”） |
| CI | 每份新的 10-Q、10-K、8-K 都触发一次全部测试 |
| lint | `thesis-ci lint`：档案里每个数字都有出处、公开内容不含估值和建议、宪法的每条规则都有可执行检查 |

格式规范（v0.2）在 [`spec/`](spec/)：[`SPEC.md`](spec/SPEC.md)、16 个 JSON Schema、检查登记表
[`checks.yml`](spec/checks.yml)（34 项检查）、指标登记表 [`metrics.yml`](spec/metrics.yml)
和林奇六类监控模板 [`templates/lynch/`](spec/templates/lynch/)。机器可读文件与 `SPEC.md` 冲突时，以机器可读文件为准。

一个档案由两个仓库组成：公开仓库（`repo.yml` 中 `visibility: public`）放论点、预注册、预测和股东信；
私有仓库（`visibility: private`）放价值区间、L3 备忘录、升级请求、系列排名和带金额的决策日志。`thesis-ci lint` 读 `repo.yml`
决定运行哪些检查。预注册按事件分成三件：不可变的条目文件 `prereg/<期间>.yml`（所有者的改写在 `<期间>-owner.yml`）、
时间戳证明 `<期间>.yml.ots` 和流水线维护的结算文件 `<期间>.settlement.yml`（SPEC 2.1）。

### 快速开始

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
- uses: kentian742-creator/thesis-ci@v0.2.0
  with:
    path: .                      # 档案仓库根目录
    # counterpart: ../private    # 可选：另一侧仓库
    expect-visibility: public    # 可选，建议公开仓库使用
    # base-ref: origin/main      # 可选：与 period 一起用于 C-TEST-FROZEN（checkout 需 fetch-depth: 0）
    # period: FY2027Q1
```

### 检查一览

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

每项检查的完整定义见 [`spec/checks.yml`](spec/checks.yml)。实现上的几个约定：

- **出处（SPEC 3.1、3.4）。** 句子按 `。！？；` 和换行切分；含事实数字（`$495`、`16%`、`1,020 亿美元`、`1.04×`、`45 个百分点` 等）的句子必须带 `[src:TAG#LOCATOR]`。SPEC 3.4 所列单位的其他写法同样算事实数字：英文（`16 percent`、`30 basis points`、`40 cents`、`1.2 trillion`、`25x`）、其他货币（`€500`、`RMB 5`、`5 港元`、`1.50 比索`）和数量级（`5 千美元`、`3 百亿`）；数字和单位之间可以有任意空白，零宽字符不能把它们隔开。年份、日期、季度、`FY2026`、章节号不算事实数字（`2019-06 百亿补贴` 这类“日期 + 名称”也不算）；front matter、代码块、行内代码和链接 URL 不参与判断。Markdown 检查覆盖 `companies/`、`industries/`、`letters/` 和根目录的 `mistakes.md`。标签先在文件所在目录及上级目录的 `sources.yml` 中查找，最后是仓库根目录。
- **YAML 自由文本。** `claim`、`summary`、`category_rationale`、`pillars[].claim`、`permanent_loss_paths`、`structure`、`implication`、`observable`、`title`、`note`、`statement`、`label` 中的事实数字同样要带标签；`fail_if`、`warn_if`、`threshold`、`question`、`rule` 是事先写下的判定标准，不需要出处。`companies/` 和 `industries/` 下任何 YAML（包括 `updates/` 和多文档流的每个文档）中的 `source` 字段都必须能解析。
- **YAML 日期**在 JSON Schema 校验前转成 ISO 字符串，并启用 `format` 校验（例如 `2026-02-30` 会报错）。重复的键（PyYAML 会静默保留最后一个值）是 `C-SCHEMA` 错误；`companies/<TICKER>/` 下文件的 `company` 必须等于目录名，`industry.yml` 的 `id` 必须等于目录名，同一个 `sources.yml` 里标签不得重复；带 `--counterpart` 时两个仓库的 `visibility` 不得相同。
- **扫描范围。** 除 `.git`、虚拟环境、缓存和 `build/`、`dist/` 外，所有目录都扫描，包括 `.claude/` 这类隐藏目录（隐藏目录同样会被发布）。在 git 工作区里只扫描 git 会发布的文件（已跟踪的，以及未被忽略的新文件），所以本地被忽略的 `.env`、`logs/` 不会让 lint 失败；若档案本身被外层仓库忽略，则扫描全部文件。
- **公开仓库的键与用语。** 键检查覆盖每个 YAML 文档（`---` 之后的文档也算）和 JSON 数据文件，键名先归一（`valueRanges`、`Value-Ranges` 都算 `value_ranges`）。用语表与 00 §H4 一字不差，其他写法（`推荐买入`、`buy rating`、`I recommend buying` 等）另由模式匹配发现；扫描 `companies/`（含 `updates/`）、`industries/`、`forecasts/`、`letters/` 和根目录的 `mistakes.md`。用语检查先做 NFKC、去掉零宽字符并把繁体换成简体，中文词之间允许空白，英文词之间允许空格、`_` 或 `-`，所以 `建議買入`、`建议 买入`、`strong-buy` 都会被发现；`overweight`、`underweight` 只在作为评级时算建议（`Rating: Overweight`、`rated Overweight`），`overweight adults` 不算。以股价为输入的倍数（`市盈率`、`P/E`、`市值`、`自由现金流收益率`、`FCF yield`）与数字出现在同一句时报错；年份、日期、期间和一位数的编号不算数字。
- **输入尚不存在时检查空过**（没有备忘录、没有预注册等）；公开仓库必须有 `constitution/rules.yml` 和 `constitution/decision-rights.yml`。
- **自检。** `thesis-ci selftest` 把包内的示例档案（[`src/thesis_ci/fixtures/workspace`](src/thesis_ci/fixtures/workspace)，全部为虚构数据）复制到临时目录，对每项检查施加至少一个违规改动。`C-CONSTITUTION-MAP` 要求宪法引用的每项检查都通过自检，并且 `spec/checks.yml` 中注明“宪法第 N 条”的检查都被 `rules.yml` 的某条规则引用。

### 尚未包含（按阶段计划）

- **EDGAR 监听**：定时查询 EDGAR submissions 接口、新文件自动开 PR（第 2 阶段）。
- **结算**：财报入库后按事先的判定标准结算预注册和言行账本（第 1 阶段半自动，第 2–3 阶段自动化）。
- **OpenTimestamps 打时间戳**：由流水线完成；`C-PREREG-IMMUTABLE` 只检查截止之后证明是否存在，并在装有 `ots` 客户端时核验。
- 校准看板、行业路标触发的复核 issue：第 4 阶段，与 v1.0 一起发布。

规范在跑完两个财报季之前保持 v0.x，不兼容的改动逐条记入 [CHANGELOG](CHANGELOG.md)。

### 开发

```bash
pip install -e ".[test]"
pytest -q
thesis-ci selftest
```

新增一项检查：先在 `spec/checks.yml` 登记，再在 `src/thesis_ci/checks/` 中用 `@check("C-...")` 实现，
在 `src/thesis_ci/selftest.py` 中加至少一个违规样例，并写一个文档字符串含检查 id 的单元测试。
测试会核对登记表与实现一一对应。

### 许可

代码以 [MIT](LICENSE) 许可发布；`spec/` 和文档以 [CC BY 4.0](LICENSE-SPEC.md) 许可发布。

---

## English

### What it is

thesis-ci is an open format specification and linter for owner-style investment thesis archives:

| Software engineering | In thesis-ci |
| --- | --- |
| Source code | `thesis.yml`: a company's thesis, ratings, industry dependencies and thesis tests |
| Unit tests | Thesis tests: quantitative, qualitative and staleness tests with thresholds written down in advance ("what would prove me wrong") |
| CI | Every new 10-Q, 10-K or 8-K triggers all tests |
| Lint | `thesis-ci lint`: every number carries a source, public content has no valuation or advice, every constitution rule maps to an executable check |

The specification (v0.2) lives in [`spec/`](spec/): [`SPEC.md`](spec/SPEC.md) (Chinese), 16 JSON Schemas, the check
registry [`checks.yml`](spec/checks.yml) (34 checks), the metric registry [`metrics.yml`](spec/metrics.yml) and the
six Lynch monitoring templates in [`templates/lynch/`](spec/templates/lynch/). Where `SPEC.md` and the machine-readable
files disagree, the machine-readable files win.

An archive is a pair of repositories: a public one (`visibility: public` in `repo.yml`) with theses,
pre-registrations, forecasts and letters, and a private one (`visibility: private`) with value ranges, L3 memos,
escalation requests, the series ranking and the decision log with amounts. `thesis-ci lint` reads `repo.yml` to
decide which checks apply. A pre-registration is three files per event: the immutable items file
`prereg/<period>.yml` (the owner's overrides in `<period>-owner.yml`), the timestamp proof `<period>.yml.ots`, and the
settlement file `<period>.settlement.yml` kept by the pipeline (SPEC 2.1).

> Not investment advice. thesis-ci never fetches prices, produces no buy or sell signals and executes no trades.

### Quickstart

```bash
pip install git+https://github.com/kentian742-creator/thesis-ci
thesis-ci lint path/to/archive                  # runs the checks that apply to repo.yml's visibility
thesis-ci lint path/to/private --counterpart path/to/public   # private checks may read the public decision rights
thesis-ci lint path/to/archive --format json --today 2026-09-24 --only C-SRC-TAG C-STORY
thesis-ci lint . --expect-visibility public     # lint as a public archive; fail if repo.yml says otherwise
thesis-ci lint . --base-ref origin/main --period FY2027Q1   # after results: thresholds in force stay frozen
thesis-ci checks                                # every check: scope, level, implemented, selftest result
thesis-ci selftest                              # each check must flag a violating fixture and pass a clean one
thesis-ci staleness path/to/archive --today 2026-09-24   # evaluate the staleness tests of every thesis.yml
thesis-ci brier path/to/archive/forecasts/2026.yml       # Brier score and calibration bins per domain and book
```

- `lint` exits 1 when there is any error-level finding, 0 otherwise (warnings do not fail); usage errors exit 2.
- `--expect-visibility public|private` runs the checks for that visibility whatever `repo.yml` says and reports a
  mismatch as a `C-SCHEMA` error. A public archive's CI should pass `--expect-visibility public`; otherwise changing
  `repo.yml` to `private` skips every public check.
- `--base-ref <git ref> --period FY<year>Q<quarter>` compares the thesis tests with that ref (`C-TEST-FROZEN`): the
  criteria of tests in force for the period may not be edited or removed. Without both, the check passes vacuously.
- `--format json` prints `{"repo", "visibility", "errors": [{"check","file","line","message"}], "warnings": [...], "checks_run": [...]}`.
- `staleness` exits 1 when a test fails. `brier` scores resolved forecasts only (`happened` / `not_happened`):
  BS = mean((p − o)²); answering 50% every time scores 0.25.

As a GitHub Action:

```yaml
- uses: actions/checkout@v5
- uses: kentian742-creator/thesis-ci@v0.2.0
  with:
    path: .                      # archive repository root
    # counterpart: ../private    # optional: the other side
    expect-visibility: public    # optional, recommended for a public archive
    # base-ref: origin/main      # optional, with period, for C-TEST-FROZEN (check out with fetch-depth: 0)
    # period: FY2027Q1
```

### Checks

The table above lists all 34 checks with their scope (`public`, `private`, `both`, or `workspace`, which runs only
with `--counterpart`) and level. Full definitions are in [`spec/checks.yml`](spec/checks.yml). Implementation notes:

- **Sources (SPEC 3.1, 3.4).** Sentences split on `。！？；` and newlines. A sentence with a fact number (`$495`, `16%`,
  `1,020 亿美元`, `1.04×`, `45 个百分点`, ...) needs a `[src:TAG#LOCATOR]` tag. Other spellings of the SPEC 3.4 units
  count too: English (`16 percent`, `30 basis points`, `40 cents`, `1.2 trillion`, `25x`), other currencies (`€500`,
  `RMB 5`, `5 港元`, `1.50 比索`) and magnitudes (`5 千美元`, `3 百亿`); any whitespace may separate number and unit, and
  zero-width characters do not split them. Years, dates, quarters, `FY2026` and section numbers are not facts (nor is a
  date followed by a name, `2019-06 百亿补贴`); front matter, code and link URLs are ignored. Markdown under
  `companies/`, `industries/`, `letters/` and the root `mistakes.md` is checked. Tags resolve through `sources.yml` in
  the file's directory and its parents, up to the repository root.
- **YAML free text.** Fact numbers in `claim`, `summary`, `category_rationale`, `pillars[].claim`,
  `permanent_loss_paths`, `structure`, `implication`, `observable`, `title`, `note`, `statement` and `label` need tags
  too; `fail_if`, `warn_if`, `threshold`, `question` and `rule` are pre-registered criteria, not facts. A `source`
  field in any YAML under `companies/` or `industries/` (update records and every document of a stream included)
  must resolve.
- **YAML dates** are converted to ISO strings before JSON Schema validation, with format checking on. A repeated key
  (PyYAML silently keeps the last value) is a `C-SCHEMA` error; files under `companies/<TICKER>/` must name that
  company, `industry.yml` must carry its directory's id, a tag may appear once per `sources.yml`, and with
  `--counterpart` the two archives must not declare the same `visibility`.
- **What is scanned.** Every directory except `.git`, virtual environments, caches, `build/` and `dist/`, hidden ones
  such as `.claude/` included (they are published too). Inside a git work tree only what git would publish is scanned
  (tracked files and untracked files that are not ignored), so an ignored local `.env` or `logs/` does not fail the
  lint; if an enclosing repository ignores the archive itself, every file is scanned.
- **Public keys and wording.** Key checks read every YAML document (also the ones after `---`) and JSON data files,
  with key names normalized (`valueRanges` and `Value-Ranges` both mean `value_ranges`). The phrase lists are exactly
  the terms of 00 §H4, other wordings (`推荐买入`, `buy rating`, `I recommend buying`) are matched as patterns, and
  `companies/` (with `updates/`), `industries/`, `forecasts/`, `letters/` and the root `mistakes.md` are scanned. A
  price-derived multiple (`市盈率`, `P/E`, `市值`, `自由现金流收益率`, `FCF yield`) with a number in the same sentence is
  an error; years, dates, periods and one-digit numbers do not count. Wording checks apply NFKC,
  drop zero-width characters and map traditional to simplified characters first; Chinese phrases may contain spaces
  and English words may be joined by spaces, `_` or `-`, so `建議買入`, `建议 买入` and `strong-buy` are found.
  `overweight` / `underweight` count as advice only as a rating (`Rating: Overweight`, `rated Overweight`), not in
  `overweight adults`.
- **Vacuous pass**: checks pass when their inputs do not exist yet (no memos, no pre-registrations, ...). A public
  archive must have `constitution/rules.yml` and `constitution/decision-rights.yml`.
- **Selftest.** `thesis-ci selftest` copies the bundled example archive
  ([`src/thesis_ci/fixtures/workspace`](src/thesis_ci/fixtures/workspace), fictitious data) to a temporary directory
  and applies at least one violating edit per check. `C-CONSTITUTION-MAP` requires every check the constitution
  references to pass its selftest, and every check that `spec/checks.yml` ties to a constitution rule (宪法第 N 条)
  to be referenced by some rule in `rules.yml`.

### Not included yet (planned phases)

- **EDGAR listener**: scheduled polling of the EDGAR submissions API and automatic PRs for new filings (phase 2).
- **Settlement** of pre-registrations and the say-do ledger against the pre-written criteria (semi-automatic in
  phase 1, automated in phases 2–3).
- **OpenTimestamps stamping** is the pipeline's job; `C-PREREG-IMMUTABLE` checks that a proof exists after the
  deadline and verifies it when the `ots` client is installed.
- Calibration dashboard and signpost-triggered review issues: phase 4, together with v1.0.

The specification stays at v0.x until two earnings seasons have run; incompatible changes are listed in the
[CHANGELOG](CHANGELOG.md).

### Development

```bash
pip install -e ".[test]"
pytest -q
thesis-ci selftest
```

To add a check: register it in `spec/checks.yml`, implement it in `src/thesis_ci/checks/` with `@check("C-...")`,
add at least one violating case to `src/thesis_ci/selftest.py`, and write a unit test whose docstring names the
check id. The test suite verifies that the registry and the implementations match one to one.

### License

Code: [MIT](LICENSE). Specification (`spec/`) and documentation: [CC BY 4.0](LICENSE-SPEC.md).
