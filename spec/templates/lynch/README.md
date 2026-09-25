# 林奇六类监控模板

公司按林奇分类套用默认测试，再从企业报告的论点破坏信号和前瞻指标补充。模板里的门槛是默认值：公司经理可以按公司情况改写，但必须在测试的 `note` 里写明理由；改写后的门槛同样要在结果出来之前写下。

模板测试的 `origin` 写成 `template:<category>`。套用时补上 `id` 和 `effective_from`（从哪一期起判定）；定性测试另写 `judge: independent_model`、`evidence: required`，模板给出的 `where`（判定时读哪些文件）与 `lookback`（读几期，含本期）是默认值，可以按公司改写。

类别变化时，旧模板的测试不删除：写 `retired_at`（从哪一期起不再判定），新模板的测试写 `effective_from`；逐条接替的新测试写 `supersedes`（被接替的测试 id）。

所有模板共有三条时效测试：`moat`、`management` 各 4 个季度，`bear_case`（反方论证）2 个季度。
