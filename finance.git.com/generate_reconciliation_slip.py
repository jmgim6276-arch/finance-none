#!/usr/bin/env python3
"""
根据对比报告生成“流水与发票对账确认单”。

这里生成的是本地确认单文件，不再把“确认单管理”误当成通用上传页。
财税通当前 UAT 下的“确认单管理”真实页面是 `/bill/query/confirmBill`，
对应的是交易级确认单列表，而不是任意总结单上传入口。
"""

import argparse
import json
from datetime import datetime
from typing import Any, Dict


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def generate_slip(comparison: Dict[str, Any], query_result: Dict[str, Any]) -> Dict[str, Any]:
    period = query_result.get("query_period", {})
    stats = comparison.get("statistics", {})
    summary = comparison.get("summary", {})

    no_activity = bool(summary.get("no_activity"))
    if no_activity:
        submit_hint = "当前期间无银企流水与发票数据，无需写入确认单管理。"
    else:
        submit_hint = (
            "当前财税通 UAT 的确认单管理页为交易级确认单页面。"
            "若要继续落库，需要先确认是否存在可更新/可提交的确认单记录。"
        )

    return {
        "docType": "reconciliationSlip",
        "title": f"流水与发票对账确认单 ({period.get('start_date')} ~ {period.get('end_date')})",
        "documentDate": datetime.now().strftime("%Y-%m-%d"),
        "period": period,
        "summary": {
            "bankTransactionCount": stats.get("bank_transaction_count", 0),
            "inputInvoiceCount": stats.get("input_invoice_count", 0),
            "outputInvoiceCount": stats.get("output_invoice_count", 0),
            "bankTotal": stats.get("bank_total_amount", 0),
            "inputTotal": stats.get("input_total_amount", 0),
            "outputTotal": stats.get("output_total_amount", 0),
            "matchedPairs": summary.get("total_matched_pairs", 0),
            "unmatchedBank": summary.get("unmatched_bank_count", 0),
            "unmatchedInvoice": summary.get("unmatched_invoice_count", 0),
        },
        "reconciliationStatus": summary.get("reconciliation_status", ""),
        "businessConclusion": summary.get("business_conclusion", ""),
        "details": {
            "matchedPairs": comparison.get("matched_pairs", []),
            "unmatchedBankTransactions": comparison.get("unmatched", {}).get("bank_transactions", []),
            "unmatchedInputInvoices": comparison.get("unmatched", {}).get("input_invoices", []),
            "unmatchedOutputInvoices": comparison.get("unmatched", {}).get("output_invoices", []),
        },
        "remark": "自动生成的流水与发票对账确认单，供复核与留档使用。",
        "submitHint": submit_hint,
        "generatedAt": datetime.now().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", default="comparison_report.json")
    parser.add_argument("--query-result", default="query_result_2026_05.json")
    parser.add_argument("--output-slip", default="reconciliation_slip.json")
    args = parser.parse_args()

    comparison = load_json(args.comparison)
    query_result = load_json(args.query_result)
    slip = generate_slip(comparison, query_result)

    with open(args.output_slip, "w", encoding="utf-8") as handle:
        json.dump(slip, handle, indent=2, ensure_ascii=False)

    print(f"✅ 确认单已生成：{args.output_slip}")
    print("\n📋 确认单摘要：")
    print(f"  期间：{slip['period'].get('start_date')} ~ {slip['period'].get('end_date')}")
    print(f"  银企交易：{slip['summary']['bankTransactionCount']} 条 (¥{slip['summary']['bankTotal']})")
    print(f"  进项发票：{slip['summary']['inputInvoiceCount']} 张 (¥{slip['summary']['inputTotal']})")
    print(f"  销项发票：{slip['summary']['outputInvoiceCount']} 张 (¥{slip['summary']['outputTotal']})")
    print(f"  对账状态：{slip['reconciliationStatus']}")
    print(f"  后续动作：{slip['submitHint']}")


if __name__ == "__main__":
    main()
