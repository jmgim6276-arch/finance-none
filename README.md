# finance-none

这个仓库收口了两部分可复用内容：

- `finance.git.com/`
  - 财税通自动登录、导入、银企直连/进销项发票查询脚本
  - 已包含 UAT 下真实接口与真实筛选参数的查询逻辑
  - 已包含销项发票“无筛选全量拉取 + 本地按 `invoiceMakeDate` 过滤”的兜底逻辑
- `wuren-daizhang-agent/`
  - OpenClaw `无人代账` agent 的身份、规则、记忆与 `finance-workflow` skill
  - 已同步财税通登录、交易查询、进销项发票查询的最新执行规范

本仓库只保留源码和 agent 配置，不包含真实账号、密码、查询结果、日志等调试产物。
