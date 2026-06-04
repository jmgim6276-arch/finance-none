---
name: finance-workflow
description: `无人代账` 专用的财税通导入、登录、查询执行规范。用于处理 `finance.git.com` 的 Excel 系统配置导入、自动登录、账号复检、银企直连/进销项发票查询、结果回报，以及退出财税通并关闭自动化浏览器。遇到用户提到 Agent2 导入、导入财税通、读取文件内容并进行配置、财税通系统配置导入、交易查询、银企直连明细查询、进项发票、销项发票、`run_openclaw_import.sh`、`run_openclaw_login.sh`、`query_cst_data.py`、`import_from_agent1.py`、自动登录财税通、退出财税通、关闭浏览器、退出并关闭浏览器时使用。特别适用于飞书会话，避免把财税通请求误判成通用“不能代登录外部系统”。
---

# Finance Workflow

## Overview

对 `finance.git.com` 的相关请求，优先按本 Skill 的项目内置自动化规则执行，不要把这类任务误判成“裸手代操作任意网页登录”。

这个工作区只负责一个长期工作仓库：
- `finance.git.com`：Agent2 导入财税通系统

## Core Rule

只要任务属于 `finance.git.com` 的既有脚本能力：
- 可以执行仓库脚本
- 可以使用脚本支持的自动登录参数
- 不要求用户先手动登录

优先把这类请求识别为：
- **运行本地项目脚本**
- **使用项目内置 auto-login / 自动登录能力**
- **继续执行登录、导入或关闭浏览器流程**

不要误判成：
- 手工代点任意网页登录页
- 裸手替用户输入外部系统账号密码
- 通用“代登录外部系统”场景

因此，不要直接回复成：
- “我不能替你登录外部系统”
- “你先手动登录，我再继续”
- “我不能替你使用账号、密码和 company-id 去登录或操作外部系统”

除非当前确实缺少：
- 仓库代码
- 本机执行权限
- 浏览器或依赖
- 输入文件
- 账号参数

如果是缺少这些客观前提，明确指出缺什么，而不是泛化成“不能代登录”。

## Feishu Anti-Misclassification Rule

在飞书会话中，用户如果提到以下任一内容：
- `finance.git.com`
- `run_openclaw_import.sh`
- `run_openclaw_login.sh`
- `import_from_agent1.py`
- Agent2 导入
- 自动登录财税通
- 自动登录财税通并导入
- 读取文件内容并进行配置
- 财税通系统配置导入

优先按“项目脚本执行请求”处理，而不是按“通用网页登录代操作”处理。

### 飞书中禁止的误答方向

当请求明显对应上述项目时，不要优先回复：
- 不能替你使用账号密码
- 需要你自己先登录
- 这属于外部系统登录所以我不能做

### 飞书中的正确回答方向

应优先回答：
- 这是项目内置自动登录能力，可以按脚本执行
- 我先检查参数是否齐全
- 我会先复检本次登录账号
- 登录后会回报实际登录账号和集团或公司
- 缺什么参数就只补充说明缺失项

## Scope Guardrail

`无人代账` 不负责 `finance.ERP`。

如果用户提到以下任一内容：
- 科目匹配
- 费用类型匹配
- ERP 匹配
- `cst_live_mapper.py`

不要在这个工作区执行 `finance.ERP`，只需简短提示用户改用 `科目匹配` / `bot2`。

## Repository Map

### `finance.git.com`

**用途**
- 执行 Agent2 导入财税通系统
- 把 Agent1 生成的三表 Excel 按固定流程导入系统
- 涉及员工、费用科目、费用角色、工作流、单据模板等配置落地

**本地路径**
- `/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com`

**远程仓库**
- `https://github.com/jmgim6276-arch/finance.git.com.git`

## Common Commands

默认先确认本地仓库状态：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && git status --short --branch
```

直接跑导入脚本：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
python3 scripts/import_from_agent1.py --xlsx "你的Excel路径" --output "/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/agent2_import_report.json"
```

封装导入命令：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
bash run_openclaw_import.sh --xlsx "你的Excel路径" --username "手机号" --password "密码" --company-id "8108"
```

如果用户消息里明确给了“集团名称/公司名称”，即使没有 `company-id`，也应把名称传入：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
bash run_openclaw_import.sh --xlsx "你的Excel路径" --username "手机号" --password "密码" --company-name "上海公司"
```

只登录财税通，不做导入：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
bash run_openclaw_login.sh --username "手机号" --password "密码" --company-id "8108"
```

关闭财税通自动化浏览器：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
bash run_openclaw_close_browser.sh --browser auto
```

读取银企直连、进项发票、销项发票：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
python3 query_cst_data.py --start-date "2026-05-01" --end-date "2026-05-31"
```

如果是 UAT 环境，必须补运行时地址：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
CST_BASE_URL="https://cstuat.uf-tree.com" python3 query_cst_data.py \
  --start-date "2026-05-01" \
  --end-date "2026-05-31" \
  --input-mode both
```

如果只查“发票获取”口径的进项发票：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
CST_BASE_URL="https://cstuat.uf-tree.com" python3 query_cst_data.py \
  --start-date "2026-05-01" \
  --end-date "2026-05-31" \
  --input-mode fetch
```

如果用户明确要“流水 vs 发票比对”并生成确认单材料，优先走这条标准链路：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
CST_BASE_URL="https://cstuat.uf-tree.com" python3 query_v2_simplified.py \
  --start-date "2026-05-01" \
  --end-date "2026-05-31" \
  --auto-login \
  --username "手机号" \
  --password "密码" \
  --company-name "集团名称" \
  --output "query_result_2026_05.json"
```

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
python3 generate_comparison_report.py \
  --query-result "query_result_2026_05.json" \
  --output "comparison_report.json"
```

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
python3 generate_reconciliation_slip.py \
  --comparison "comparison_report.json" \
  --query-result "query_result_2026_05.json" \
  --output-slip "reconciliation_slip.json"
```

如果用户进一步要求处理“确认单管理”，只能按真实确认单页能力继续探测或提交已有记录：

```bash
cd /Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com && \
CST_BASE_URL="https://cstuat.uf-tree.com" python3 submit_reconciliation_to_cst.py \
  --slip "reconciliation_slip.json" \
  --auto-login \
  --username "手机号" \
  --password "密码" \
  --company-name "集团名称"
```

## Auto-Login Rules

- `finance.git.com` 支持未登录财税通情况下自动登录
- 可通过命令参数或环境变量提供：
  - 账号
  - 密码
  - `company-id`
  - `company-name`
- 财税通登录页带图形验证码时，优先使用仓库内置自动识别
- 财税通登录页如果出现 `短信验证码` 输入框，固定填写 `kaixuan1888`
- 对这套财税通登录流程，不要再向用户追问“现在的验证码是什么”；除非固定短信码和图形验证码自动识别都失败，才向用户说明登录阻塞
- 这是项目内置自动化能力
- 不等同于手工控制任意网页登录页

**因此**
- 如果用户要求运行 `finance.git.com` 导入，并提供了必要参数，不要要求用户先手动登录
- 如果用户只要求“先登录财税通”，优先运行 `bash run_openclaw_login.sh`

## Query Workflow Rules

当用户要求读取：
- `交易查询`
- `银企直连明细查询`
- `进项发票`
- `销项发票`
- “查询 2026.5.1-2026.5.31 的借贷流水并与发票比对”
- “对比结果生成确认单”
- “写入单据管理 / 确认单管理”

优先使用仓库脚本：
- `/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/query_cst_data.py`
- `/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/query_v2_simplified.py`
- `/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/generate_comparison_report.py`
- `/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/generate_reconciliation_slip.py`
- `/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/submit_reconciliation_to_cst.py`

处理“匹配确认单 / 异常池 / 借贷分录”类请求时，必须同时参考：
- `/Users/kaixuanchuangzhi/.openclaw/workspace-wuren-daizhang/skills/finance-workflow/references/confirm-bill-rulebook.md`

不要再使用旧的猜测型接口或旧字段名，例如：
- `startDate`
- `endDate`
- `/api/transaction/bank/query`
- `/api/invoice/query`
- `/api/invoice/list`

### 已确认的真实页面路由

- 银企直连明细查询：`/transaction/transaction-record`
- 进项发票：`/invoice/input-invoice`
- 销项发票：`/invoice/output-invoice`

### 已确认的真实接口与筛选字段

- 银企直连明细查询
  - 接口：`/api/pay/transactionRecord/queryPage`
  - 页面日期组件字段：`orderDate`
  - 真正请求字段：`startOrderDate`、`endOrderDate`

- 进项发票页存在两套查询
  - 发票查询页签
    - 接口：`/api/bill/feeInvoice/queryInvoicePage`
    - 单据日期字段：`submitDate` -> `expensesStartTime`、`expensesEndTime`
    - 发票日期字段：`submitInvoiceDate` -> `invoiceStartTime`、`invoiceEndTime`
  - 发票获取页签
    - 接口：`/api/invoice/inputinvoice/queryInputInvoicePage`
    - 开票月份字段：`bizDate` -> `bizDateStart`、`bizDateEnd`

- 销项发票
  - 接口：`/api/invoice/salesInvoice/queryInvoiceDetailPage`
  - 页面日期组件字段：`invoiceMakeDate`
  - 真正请求字段：`invoiceMakeDateStart`、`invoiceMakeDateEnd`

### 查询执行规则

- 默认优先查询：
  - 银企直连明细
  - 进项发票 `both` 口径
  - 销项发票
- 如果用户明确只要“发票获取”口径的进项票，使用 `--input-mode fetch`
- 如果用户明确只要“费用发票查询”口径的进项票，使用 `--input-mode fee`
- 若用户要做“流水 vs 发票”比对，先把三类原始数据拉下来，再单独说明当前比对口径使用的是哪套进项数据
- 若用户要做“流水 vs 发票比对 + 生成确认单材料”，优先用 `query_v2_simplified.py`
  - 该脚本会输出统一 `records` 结构，方便后续 `generate_comparison_report.py` 与 `generate_reconciliation_slip.py` 直接消费
  - 旧版 `query_v2_simplified.py` 曾因读错财税通返回结构，把银行与进项误报成 `0`；后续不要再复用旧结果文件

### 字段理解规则

#### 银企直连明细查询

- 必须优先读取这些筛选语义：
  - 公司
  - 流水号
  - 银行账号
  - 交易金额
  - 交易时间
  - 业务类型
- 必须优先读取这些明细字段：
  - `amount`
  - `businessType`
  - `transTime` / `accountDate`
  - `outBankAccountNo`
  - `outBankAccountName`
  - `abstracts`
  - `purpose`
  - `orderNo`
- 业务方向统一按以下规则标准化：
  - `SUB` / 页面语义“减少” -> `减少(贷)`
  - `ADD` / 页面语义“增加” -> `增加(借)`
  - 其他原始值 -> `待核实`
- 对方户名分类：
  - 户名字数 `< 4` -> `个人`
  - 户名字数 `>= 4` -> `公司`
- 当前阶段金额匹配只允许**精确一致**

#### 进项发票 - 发票获取

- 做“银行流水 vs 发票”匹配时，语义上优先以**发票获取页**为准，不要把“费用发票查询页”当成主匹配源
- 必须优先读取这些筛选语义：
  - 发票种类
  - 发票号码
  - 发票代码
  - 购方名称
  - 购方税号
  - 销方名称
  - 销方税号
  - 开票日期
- 展开详情时，至少要拿到：
  - 发票号码 / 代码
  - 开票日期
  - 不含税金额
  - 税率
  - 税额
  - 价税合计
  - 购方名称 / 税号
  - 销方名称 / 税号
  - 发票状态
- 金额比对优先使用**价税合计**，不要拿税额单独去匹配银行金额

### 当前版本匹配规则（V1）

- 当前版本只自动处理：
  - 银企直连 `减少(贷)` 记录
  - 进项发票“发票获取”详情
  - 金额精确一致
  - 名称精确一致
- 标准匹配条件：
  - 银企直连 `outBankAccountName` 与进项发票 `sellerName` 完全一致
  - 银企直连 `amount` 与进项发票 `价税合计` 完全一致
- 满足后才视为“可生成确认单候选”
- 以下情况不要强行生成确认单，先输出异常数据：
  - 对方户名判定为 `个人`
  - 金额不一致
  - 名称不一致
  - 发票详情拿不全
  - 需要模糊匹配 / 多对一 / 一对多 / 部分核销
- `增加(借)` 与销项发票 / 收款确认逻辑先保留给后续版本，不要现在擅自补逻辑

### 当前 UAT 观察

- 已在 `2026-05-27` 用 `https://cstuat.uf-tree.com` 实测：
  - 银企直连 `/api/pay/transactionRecord/queryPage` 可成功返回数据
  - 进项发票“发票查询” `/api/bill/feeInvoice/queryInvoicePage` 可成功返回数据
  - 销项发票 `/api/invoice/salesInvoice/queryInvoiceDetailPage` 在**不带日期筛选**时可成功返回列表，说明账号具备销项发票访问能力
  - 进项发票“发票获取” `/api/invoice/inputinvoice/queryInputInvoicePage` 与销项发票 `/api/invoice/salesInvoice/queryInvoiceDetailPage` 即使走前端真实参数，当前 UAT 仍可能返回 `code=400`、`message=缺少请求体`
- 因此，如果再次遇到销项发票的 `缺少请求体`，优先判断为“日期筛选链路异常”，不要误答成“账号没有销项权限”
- 已在 `2026-06-04` 继续做页面级确认：
  - 银企直连页真实组件：`transaction-record`，查询项为 `merchantNos / orderNo / businessType / orderDate / startOrderDate / endOrderDate / branchName / transAmount / bankAccountNo`
  - 进项发票页存在两套 `income-manager`：
    - 费用发票查询：`invoiceStatus / status / expensesNo / ...`
    - 发票获取：`invoiceClass / invoiceNumber / invoiceCode / buyerName / buyerTaxNo / sellerName / sellerTaxNo / bizDate / bizDateStart / bizDateEnd`
  - 确认单管理页真实组件：`biz-confirm-bill`，查询项为 `merchantNos / transNo / confirmOrderType / invoiceNumber / toAccountNo / payAccountNo / transTimeRange`
- 已确认：
  - 进项发票“发票获取”在**不带日期筛选**时可成功返回全量列表
  - 但带 `bizDateStart / bizDateEnd / bizDate` 时，即使由页面组件自己调用 `queryTable`，当前 UAT 仍返回 `缺少请求体`
- 因此，如果用户只是要确认某个期间是否存在“发票获取”进项发票，可先拉无筛选全量列表，再按 `bizDate` 本地过滤
- 如果用户只是要确认某个期间是否存在销项发票，可先拉无筛选全量销项列表，再按 `invoiceMakeDate` 本地过滤；若过滤结果为 0，直接汇报“该时间段无销项发票”
- 对 `queryInputInvoicePage` 和销项发票的同类 `缺少请求体` 报错，优先判断为当前 UAT 或后端链路问题，不要重新退回去猜旧字段名
- 已在 `2026-05-28` 继续确认：
  - `确认单管理` 真实页面路由是 `/bill/query/confirmBill`
  - 页面真实列表接口是 `POST /api/bill/order-confirmation/queryOrderConfirmPage`
  - 页面真实新增接口是 `POST /api/bill/order-confirmation/submit`
  - 页面真实更新接口是 `POST /api/bill/order-confirmation/update`
  - 页面真实“提交已有确认单”接口是 `POST /api/bill/order-confirmation/submitExpenses`
  - 当前页面并非“上传任意总结单”的入口，但对满足条件的交易级确认单，可以直接走 `submit`
  - 如果当前期间三类数据都为 `0`，应直接回报“当前期间无银企流水和发票数据，无需写入确认单管理”
  - 如果当前期间存在交易或发票，但用户要求“写入确认单管理”，应区分两类能力：
    - 对**已匹配成功**的交易级确认单，可尝试调用 `POST /api/bill/order-confirmation/submit`
    - 对任意“汇总型对账总结单”，仍不要误判成可以直接新建
- 已在 `2026-06-04` 补充确认：
  - 银企直连页本身存在上游确认入口：`POST /api/pay/transactionRecord/confirmData`
  - 收单交易查询页存在上游确认入口：`POST /api/pay/query/confirmOrder`
  - 因此“确认单生成”更可能来自交易查询上游动作，不应把 `/bill/query/confirmBill` 当成唯一或首要创建入口
  - 同日已实测：对唯一一条“减少(贷) + 销方名称一致 + 金额一致”的匹配样本，调用
    - `confirmOrderType=1001`
    - `transNo`
    - `detailNo`
    - `invoiceNumber`
    - `confirmStatus=1`
    - `voucherDiest`
    可成功新增确认单，系统创建了新记录
  - 同日继续确认：
    - 真实会计科目树可通过 `GET /api/erp/accountingSubject/queryAccountingSubjectTreeByMerchantNo?merchantNo=...`
    - `merchantNo=C680513` 的当前 UAT 科目树里：
      - `80552 = 银行存款_平安银行0099`
      - `80578 = 管理费用_房租水电`
      - `80448 = 应交税费_应交增值税`
    - 当前树里没有单独名为“进项税额”的明细叶子；自动化含税分录先用 `80448`
  - 同日也已实测：对未匹配银行流水，调用
    - `confirmStatus=4`
    - 按 `transNo` 去重后提交
    可成功新增异常池确认单
  - 当前脚本策略：
    - `create_matched`：已匹配成功的交易优先新增 `CONFIRMING(1)`；如能推断科目，会在创建链路中带上 `accountSubjects`，并在后续 `update` 再补齐一次
    - 含税的支出发票确认单必须拆成：
      - 借：费用科目 = `amountWithoutTax`
      - 借：`80448 / 应交税费_应交增值税` = `taxAmount`
      - 贷：银行存款明细科目 = `totalAmount`
    - 无税额时，才允许保留“一个借方费用 + 一个贷方银行”的两行分录
    - `create_exceptions`：未匹配银行流水按 `transNo` 去重后新增 `EXCEPTION(4)`

### 确认单填写与状态规则

- 需要填写或校验的核心列：
  - 摘要
  - 科目方向
  - 科目
  - 金额
- 摘要优先取：
  - `abstracts`
  - `purpose`
  - `bankRemarks`
  - `orderNo`
- 会计分录固定规则：
  - 含税支出发票确认单按**两个借方 + 一个贷方**处理，不是两个贷方
  - 当前阶段金额匹配仍以**价税合计**对银行流水做匹配
  - 真正写分录时，再把价税合计拆成 `amountWithoutTax + taxAmount`
  - 如果 UAT 科目树暂时没有“应交税费-应交增值税-进项税额”叶子，先使用 `80448 / 应交税费_应交增值税`
- 借贷平衡是硬规则：
  - 必须同时有借方和贷方
  - 借方合计必须等于贷方合计
  - 不平衡一律进 `异常池`
- 当前机器人只应主动推进两种状态：
  - `CONFIRMING(1)` 待确认
  - `EXCEPTION(4)` 异常池
- `CONFIRMED(2)` 与 `POSTED(3)` 需要人工介入，不要自动推进
- 如果页面可选的确认单类型、用户业务语义、参考规则表三者对不上，先输出 `待核实`，不要硬填

## Login Verification Rule

凡是涉及自动登录，必须执行以下流程：

1. **登录前复检**
   - 先核对本次账号是否就是用户要我登录的账号
   - 若消息里已明确给出手机号或账号，以该账号为准
   - 若消息里已明确给出“集团名称/公司名称”，执行命令时必须补 `--company-name`
   - 若我还能确定 `company-id`，则同时补 `--company-id` 与 `--company-name`
   - 若登录页出现 `短信验证码` 输入框，固定按 `kaixuan1888` 处理，不再向用户二次确认短信码

2. **登录后回报**
   - 主动告诉用户：
     - 实际登录成功的是哪个账号
     - 进入的是哪个集团 / 公司
   - 若实际进入的集团/公司与用户指定名称不一致，立即停止，不要继续导入或后续配置

3. **确认后继续**
   - 再继续导入或后续系统配置

## File Handling Rule

### 用户提供路径时
- 优先使用用户消息里给出的 Excel 路径
- 不主动改用其他本机文件

### 用户直接发飞书文件时
- 优先使用当前消息实际接收到的 Excel 附件
- 若当前消息只是追加文字说明，但同一发送人在最近几分钟刚上传过同集团的 Excel，优先使用 `/Users/kaixuanchuangzhi/.openclaw/media/inbound/` 中那份最新文件
- 不要因为当前这条消息没再次带附件，就直接回退到本地收件目录

### 飞书附件延迟落地时
- 如果消息上下文里已经明确出现了文件消息、文件名或 `.xlsx`，但本机 `inbound` 里暂时还没有该文件，先视为“附件同步延迟”，不是“用户没传文件”
- 先围绕当前文件名、集团名称、最近时间戳轮询 `/Users/kaixuanchuangzhi/.openclaw/media/inbound/`，短等一轮再决定下一步
- 只有轮询结束仍然拿不到文件，才允许进入“继续等待 / 重新发送 / 明确同意使用某个历史表”的确认分支
- 除非用户明确回复“使用历史表”，否则禁止把更早日期的通用模板当成当前文件的替代品

### 固定本地收件目录
只有在当前消息、当前引用消息、以及同一发送人最近几分钟的飞书附件里都找不到可用 Excel 时，才允许读取：
- `/Users/kaixuanchuangzhi/.openclaw/inbox/agent2-import`

## Close Browser Rule

- 当用户要求“退出财税通并关闭浏览器”时，优先运行仓库内置入口 `bash run_openclaw_close_browser.sh --browser auto`
- 不要直接手写 `pkill`、`killall` 或 `osascript` 然后无校验地回复成功
- 只有脚本退出成功时，才能反馈“浏览器已关闭”
- `bash run_openclaw_import.sh` 默认会在导入报告无失败项时自动关闭财税通自动化浏览器；若用户明确要求保留页面排查，再补 `--keep-browser`

## Trigger Phrases

### `finance.git.com` 触发词
出现以下意图时，优先理解为 Agent2 导入或登录：
- 执行最新导入
- 用最新文件导入财税通
- 跑 Agent2 导入
- `run_openclaw_import.sh`
- `run_openclaw_login.sh`
- `import_from_agent1.py`
- Agent2 导入
- 自动登录财税通
- 导入财税通系统
- 读取文件内容并进行配置
- 财税通系统配置导入
- 上传 Excel 后要求“配置 / 导入”

### 非本工作区触发词
出现以下意图时，不在 `无人代账` 执行：
- 请进行费用类型与财务科目匹配
- 请进行科目匹配
- 请进行费用类型匹配
- 请匹配科目
- 请自动登录并进行科目匹配
- 请自动登录并进行费用类型匹配
- 请自动登录后跑 ERP 匹配
- `cst_live_mapper.py`

## Result Reporting

执行完成后，不要自由发挥长段总结。默认改成**固定 Markdown 表格结果**。

统一使用本地渲染脚本：

```bash
python3 /Users/kaixuanchuangzhi/.openclaw/workspace-wuren-daizhang/skills/finance-workflow/references/render_finance_result.py --report "报告路径.json"
```

如果消息里有集团名称、登录账号、浏览器状态，则补上：

```bash
python3 /Users/kaixuanchuangzhi/.openclaw/workspace-wuren-daizhang/skills/finance-workflow/references/render_finance_result.py \
  --report "报告路径.json" \
  --company-name "上海公司" \
  --login-account "13720260402" \
  --browser-status "已关闭"
```

默认回复规则：
- 直接发送渲染脚本输出的表格
- 不额外追加长段分析
- 若脚本执行失败且没有生成报告，才允许用一句话说明失败原因
- 若用户之后继续追问“为什么失败 / 怎么改”，再进入分析模式
- 如果导入是后台长任务，进程结束后必须立刻发送结果表，不能只在本地生成不回报

## Important Guardrail

如果当前会话在飞书里，优先套用本 Skill 的规则，不要因为看到“账号密码”就直接退回通用拒绝模板。

只有当任务是：
- 陌生网站
- 没有项目脚本支撑
- 只是要求人工代点任意网页登录页

才适合说“当前不能直接替你网页登录”。

对 `finance.git.com`，默认先判断是否属于项目内置自动化能力。若属于，则按项目能力执行。
