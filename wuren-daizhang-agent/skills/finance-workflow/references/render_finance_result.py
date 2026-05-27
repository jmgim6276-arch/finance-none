#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def text(value):
    if value is None:
        return "-"
    value = str(value).strip()
    if not value:
        return "-"
    return value.replace("|", "\\|").replace("\n", "<br>")


def markdown_table(headers, rows):
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(text(item) for item in row) + " |")
    return "\n".join(output)


def first_issue(items, keys=None):
    for item in items or []:
        if isinstance(item, dict):
            if keys:
                for key in keys:
                    value = item.get(key)
                    if value:
                        return value
            if item:
                return " / ".join(f"{k}:{v}" for k, v in item.items() if v)
        elif item:
            return str(item)
    return "-"


def import_status(report):
    step1 = report.get("step1", {})
    step1_dept = report.get("step1_department_sync", {})
    step1_roles = report.get("step1_roles", {})
    step2 = report.get("step2", {})
    step3 = report.get("step3", {})
    fail_count = sum(
        len(report.get(name, {}).get("fail", []))
        for name in ["step1", "step1_department_sync", "step1_roles"]
    )
    fail_count += len(step2.get("relations_fail", []))
    fail_count += len(step2.get("reset_fail", []))
    fail_count += len(step3.get("fail", []))
    fail_count += len(step3.get("default_model_fail", []))
    fail_count += len(step3.get("ui_save_fail", []))
    warn_count = len(step3.get("ui_save_warn", []))
    preflight = report.get("preflight", {})
    if preflight.get("has_risk"):
        warn_count += 1
    success_count = (
        step1.get("ok", 0)
        + step1_dept.get("ok", 0)
        + step1_roles.get("ok", 0)
        + step2.get("relations_ok", 0)
        + step3.get("ok", 0)
        + len(step3.get("ui_save_ok", []))
    )
    if fail_count == 0 and warn_count == 0:
        return "成功", fail_count, warn_count
    if success_count > 0:
        return "部分成功", fail_count, warn_count
    return "失败", fail_count, warn_count


def render_import(report, args):
    status, fail_count, warn_count = import_status(report)
    step1 = report.get("step1", {})
    step1_dept = report.get("step1_department_sync", {})
    step1_roles = report.get("step1_roles", {})
    step2 = report.get("step2", {})
    step3 = report.get("step3", {})
    preflight = report.get("preflight", {})

    top_rows = [
        ["状态", status],
        ["账号", args.login_account],
        ["公司", args.company_name],
        ["Company ID", report.get("companyId")],
        ["浏览器", args.browser_status],
        ["报告", Path(args.report).name],
    ]

    module_rows = [
        ["预检", "-", "0", "1" if preflight.get("has_risk") else "0"],
        ["员工导入", step1.get("ok", 0), len(step1.get("fail", [])), "0"],
        ["部门同步", step1_dept.get("ok", 0), len(step1_dept.get("fail", [])), "0"],
        ["角色绑定", step1_roles.get("ok", 0), len(step1_roles.get("fail", [])), "0"],
        ["费用绑定", step2.get("relations_ok", 0), len(step2.get("relations_fail", [])) + len(step2.get("reset_fail", [])), "0"],
        ["模板配置", step3.get("ok", 0), len(step3.get("fail", [])) + len(step3.get("default_model_fail", [])), "0"],
        ["页面保存", len(step3.get("ui_save_ok", [])), len(step3.get("ui_save_fail", [])), len(step3.get("ui_save_warn", []))],
    ]

    issue_rows = []
    if preflight.get("has_risk"):
        issue_rows.append(
            [
                "预检风险",
                sum(
                    1
                    for key in ["missing_primary", "missing_people", "doc_mismatch_02_only", "doc_mismatch_03_only"]
                    if preflight.get(key)
                ),
                first_issue(preflight.get("missing_primary")) if preflight.get("missing_primary") else first_issue(preflight.get("missing_people")),
            ]
        )
    if step2.get("relations_fail"):
        issue_rows.append(["费用绑定失败", len(step2.get("relations_fail", [])), first_issue(step2.get("relations_fail"), ["message", "doc"])])
    if step2.get("reset_fail"):
        issue_rows.append(["费用重置失败", len(step2.get("reset_fail", [])), first_issue(step2.get("reset_fail"), ["message", "doc"])])
    if step3.get("fail"):
        issue_rows.append(["模板失败", len(step3.get("fail", [])), first_issue(step3.get("fail"), ["message", "doc"])])
    if step3.get("default_model_fail"):
        issue_rows.append(["默认模板失败", len(step3.get("default_model_fail", [])), first_issue(step3.get("default_model_fail"), ["message", "type"])])
    if step3.get("ui_save_fail"):
        issue_rows.append(["页面保存失败", len(step3.get("ui_save_fail", [])), first_issue(step3.get("ui_save_fail"), ["message", "doc"])])
    if step3.get("ui_save_warn"):
        issue_rows.append(["页面保存告警", len(step3.get("ui_save_warn", [])), first_issue(step3.get("ui_save_warn"), ["message", "doc"])])

    parts = [
        markdown_table(["项目", "结果"], top_rows),
        "",
        markdown_table(["模块", "成功", "失败", "告警"], module_rows),
    ]
    if issue_rows:
        parts.extend(["", markdown_table(["异常类别", "数量", "示例"], issue_rows[:6])])
    return "\n".join(parts)


def erp_status(report):
    total_apply = 0
    total_skip = 0
    for step in report.get("steps", []):
        for key, value in step.items():
            if key.endswith("_apply_count") or key == "apply_count":
                total_apply += int(value or 0)
            if key.endswith("_skip_count") or key == "skip_count":
                total_skip += int(value or 0)
    if total_skip == 0:
        return "成功", total_apply, total_skip
    if total_apply > 0:
        return "部分成功", total_apply, total_skip
    return "未匹配", total_apply, total_skip


def render_erp(report, args):
    status, total_apply, total_skip = erp_status(report)
    accounting = report.get("erp_accounting") or {}
    top_rows = [
        ["状态", status],
        ["账号", args.login_account],
        ["公司", args.company_name],
        ["ERP账套", accounting.get("accountingName")],
        ["执行模式", "写入" if report.get("applied") else "预览"],
        ["报告", Path(args.report).name],
    ]

    step_rows = []
    issue_rows = []
    for step in report.get("steps", []):
        apply_count = 0
        skip_count = 0
        for key, value in step.items():
            if key.endswith("_apply_count") or key == "apply_count":
                apply_count += int(value or 0)
            if key.endswith("_skip_count") or key == "skip_count":
                skip_count += int(value or 0)
        step_rows.append([step.get("step"), apply_count, skip_count])

        examples = []
        for key in ["skipped", "customer_skipped", "pay_paths", "income_paths"]:
            value = step.get(key) or []
            if value:
                example = value[0]
                if isinstance(example, dict):
                    examples.append(example.get("name") or example.get("path") or json.dumps(example, ensure_ascii=False))
                elif isinstance(example, list):
                    examples.append(" / ".join(str(v) for v in example))
                else:
                    examples.append(str(example))
        if skip_count:
            issue_rows.append([step.get("step"), skip_count, examples[0] if examples else "-"])

    parts = [
        markdown_table(["项目", "结果"], top_rows),
        "",
        markdown_table(["模块", "应用", "跳过"], step_rows),
    ]
    if issue_rows:
        parts.extend(["", markdown_table(["异常类别", "数量", "示例"], issue_rows[:6])])
    return "\n".join(parts)


def detect_kind(report):
    if "steps" in report and "erp_accounting" in report:
        return "erp"
    return "import"


def main():
    parser = argparse.ArgumentParser(description="把财税通执行结果渲染为简洁 Markdown 表格")
    parser.add_argument("--report", required=True, help="JSON 报告路径")
    parser.add_argument("--kind", choices=["auto", "import", "erp"], default="auto")
    parser.add_argument("--company-name", default="-", help="集团/公司名称")
    parser.add_argument("--login-account", default="-", help="登录账号")
    parser.add_argument("--browser-status", default="未知", help="浏览器状态，例如 已关闭/保留")
    args = parser.parse_args()

    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    kind = detect_kind(report) if args.kind == "auto" else args.kind
    if kind == "erp":
        print(render_erp(report, args))
    else:
        print(render_import(report, args))


if __name__ == "__main__":
    main()
