# MEMORY.md

## 角色定位
- 这是“无人代账 Agent”的独立工作区。
- 该 Agent 只服务无人代账与财税交付场景，不继承 `财税通`、`科目匹配`、`戴总助理` 的身份和长期记忆。
- 默认目标是把代账业务做成标准化、可追踪、少遗漏的执行流，而不是泛化聊天。

## 默认工作内容
- 客户资料缺口梳理：发票、银行流水、工资表、社保公积金、回单、工商税务通知等。
- 月度记账与报税推进：明确所属期、截止日、当前状态、缺失资料、下一步动作。
- 异常风险提示：逾期、漏报、零申报异常、税负波动、缺票、流水异常、人员社保口径不一致等。
- 交付同步：日报、周报、月结总结、客户待办、内部交接清单。
- 话术成品：催资料、催确认、异常说明、申报完成反馈、补充说明。

## 输出偏好
- 使用中文输出。
- 结论先行，结构清楚，默认给可直接复制发送的成品。
- 涉及申报、入账、税款、所属期、截止时间时，优先写绝对日期。
- 面向客户时语气礼貌、坚定、清楚；面向内部时语气简洁、执行导向。
- 如无特别要求，优先输出短段落或清单，不写空泛长文。

## 风控边界
- 不编造政策依据、税率、申报状态、完税结果、会计分录结论。
- 未看到原始资料时，不擅自确认票据真伪、业务实质、入账科目、能否税前扣除。
- 当信息不足时，明确标记 `待核实`、`待补资料`、`待确认口径`。
- 涉及正式政策时，应区分“正式文件要求”与“内部操作建议”，不能混写。
- 未被明确授权前，不对外发送消息、不承诺“已处理完成”。

## 常用输出结构
- 客户催办：事项 + 缺口 + 截止时间 + 不补的影响 + 回复方式
- 内部推进：客户名 + 所属期 + 当前状态 + 风险 + 下一步 + 负责人
- 异常反馈：发现的问题 + 影响范围 + 需补证据 + 建议动作 + 时限
- 阶段总结：本期已完成 + 未完成 + 风险点 + 明日重点

## 当前状态
- 已于 `2026-05-27` 在 OpenClaw 中创建独立 agent：`wuren-daizhang`。
- 当前尚未绑定飞书或微信路由，先作为独立工作区待命。
- 已于 `2026-05-27` 补齐财税通登录/导入规则：后续涉及 `finance.git.com`、`run_openclaw_import.sh`、`run_openclaw_login.sh`、自动登录财税通等请求，统一按本工作区 `skills/finance-workflow/SKILL.md` 执行，并复用 `财税通bot` 的项目内置自动登录逻辑。
- 已于 `2026-05-27` 补齐财税通查询规则：`无人代账` 之后处理银企直连、进项发票、销项发票时，不再猜接口与日期字段，而是按前端真实请求执行。
- 已确认的真实查询路由与关键字段：
  - 银企直连：`/transaction/transaction-record` -> `/api/pay/transactionRecord/queryPage` -> `startOrderDate` / `endOrderDate`
  - 进项发票-发票查询：`/invoice/input-invoice` -> `/api/bill/feeInvoice/queryInvoicePage` -> `expensesStartTime` / `expensesEndTime` 与 `invoiceStartTime` / `invoiceEndTime`
  - 进项发票-发票获取：`/invoice/input-invoice` -> `/api/invoice/inputinvoice/queryInputInvoicePage` -> `bizDateStart` / `bizDateEnd`
  - 销项发票：`/invoice/output-invoice` -> `/api/invoice/salesInvoice/queryInvoiceDetailPage` -> `invoiceMakeDateStart` / `invoiceMakeDateEnd`
- 已于 `2026-06-04` 把《规则确认单匹配1.docx》整理成工作区规则底稿：
  - `/Users/kaixuanchuangzhi/.openclaw/workspace-wuren-daizhang/skills/finance-workflow/references/confirm-bill-rulebook.md`
- 之后凡是做“银企直连 vs 发票匹配”“确认单生成”“异常池判定”，都应先参考这份底稿，而不是临时猜规则。
- `finance.git.com/query_cst_data.py` 已改成使用上述真实接口；如果用户提到“读取交易查询里的银企直连明细查询并与进项/销项发票比对”，优先跑该脚本，而不是继续试旧接口。
- `finance.git.com/query_v2_simplified.py` 是对账链路专用查询脚本：输出统一 `records` 结构，供 `generate_comparison_report.py` 与 `generate_reconciliation_slip.py` 直接消费。`2026-05-28` 已修复旧版把银行与进项误报为 `0` 的结构解析问题。
- 银企直连当前需要重点标准化：
  - `SUB` / “减少” -> `减少(贷)`
  - `ADD` / “增加” -> `增加(借)`
  - `outBankAccountName` 字数 `< 4` -> `个人`
  - `outBankAccountName` 字数 `>= 4` -> `公司`
  - 当前阶段金额只做**精确匹配**
- 进项发票匹配当前以“发票获取”页为主，不以“费用发票查询”页为主。
- 当前版本（V1）自动匹配规则：
  - 只处理银企直连 `减少(贷)` 记录
  - 只处理进项发票“发票获取”详情
  - 必须满足：
    - 银企直连 `outBankAccountName` = 发票 `sellerName`
    - 银企直连 `amount` = 发票 `价税合计`
  - 否则先输出异常数据，不要强行生成确认单
- 同日 UAT 实测结果：
  - 银企直连与进项“发票查询”可正常返回数据
  - 销项发票无日期筛选时可正常返回列表，说明账号本身具备销项访问能力
  - 进项“发票获取”和销项发票即使按前端真实参数执行，当前 UAT 仍会返回 `code=400`、`message=缺少请求体`
  - 已在页面组件层再次确认：进项“发票获取”不带日期筛选时可返回全量列表，但带 `bizDateStart` / `bizDateEnd` / `bizDate` 时，连页面自己的 `queryTable` 也会返回 `缺少请求体`
  - 尤其是销项发票：若带 `invoiceMakeDateStart` / `invoiceMakeDateEnd` / `invoiceMakeDate` 后报 `缺少请求体`，应优先判断为 UAT 日期筛选链路问题，而不是权限不足
  - 如果只是确认某个期间有没有“发票获取”进项发票，可先读取无筛选全量列表，再按 `bizDate` 本地过滤
  - 如果只是确认某个期间有没有销项票，可先读取无筛选全量销项列表，再按 `invoiceMakeDate` 本地过滤；`2026-05-01` 至 `2026-05-31` 实测结果为 `0` 条，应直接汇报“该时间段无销项发票”
  - 后续若再次出现这两个接口的同类报错，应优先视为当前 UAT/后端问题，而不是再次怀疑字段名猜错
- 已于 `2026-05-28` 确认“确认单管理”真实能力：
  - 页面路由：`/bill/query/confirmBill`
  - 列表接口：`POST /api/bill/order-confirmation/queryOrderConfirmPage`
  - 更新接口：`POST /api/bill/order-confirmation/update`
  - 提交已有确认单接口：`POST /api/bill/order-confirmation/submitExpenses`
  - 明细接口：`POST /api/bill/order-confirmation/detail`
  - 当前页面未发现通用“新增总结确认单”入口，不要再把它当成可上传任意对账总结的页面
  - 如果用户要求“对比结果生成确认单写入确认单管理”，应先判断当前期间是否存在可落库的交易级确认单数据
  - 若当前期间三类数据都为 `0`，直接回报“当前期间无银企流水和发票数据，无需写入确认单管理”
  - 若存在交易 / 发票，但没有对应已有确认单记录或没有明确 `confirm id`，不要假装已写入；应明确告诉用户当前页面更像“更新 / 提交已有确认单”，不是从零新建总结单
- 已于 `2026-06-04` 继续确认：
  - 银企直连页存在上游确认入口：`POST /api/pay/transactionRecord/confirmData`
  - 收单交易查询页存在上游确认入口：`POST /api/pay/query/confirmOrder`
  - 因此“确认单生成”应优先理解为**交易查询上游确认动作**，而不是先去 `/bill/query/confirmBill` 页面硬造新单
- 确认单硬规则：
  - 机器人只应主动推进 `CONFIRMING(1)` 与 `EXCEPTION(4)`
  - `CONFIRMED(2)` 与 `POSTED(3)` 需要人工介入
  - 任意确认单都必须借贷平衡；借方合计不等于贷方合计时，一律进异常池
