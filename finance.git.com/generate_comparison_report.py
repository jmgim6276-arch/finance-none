#!/usr/bin/env python3
"""
对比脚本：比对银企直连 vs 发票（进项 + 销项）

兼容 `query_cst_data.py` 的原始结构，也兼容 `query_v2_simplified.py`
输出的统一 records 结构。
"""

import argparse
import json
from datetime import datetime
from typing import Any, Dict, List, Optional


def parse_query_result(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_records(section: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(section, dict):
        return []
    data = section.get("data") or {}
    if isinstance(data, dict):
        if isinstance(data.get("records"), list):
            return list(data.get("records") or [])
        result = data.get("result") or {}
        if isinstance(result, dict) and isinstance(result.get("data"), list):
            return list(result.get("data") or [])
    return []


def field_float(item: Dict[str, Any], names: List[str]) -> float:
    for name in names:
        value = item.get(name)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except Exception:
            continue
    return 0.0


def normalize_date_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def field_date(item: Dict[str, Any], names: List[str]) -> str:
    for name in names:
        date_text = normalize_date_text(item.get(name))
        if date_text:
            return date_text
    return ""


def compare_data(query_result: Dict[str, Any]) -> Dict[str, Any]:
    bank_txns = extract_records(query_result.get("bank_transactions"))
    input_invoices = extract_records(query_result.get("input_fee_invoices"))
    output_invoices = extract_records(query_result.get("output_invoices"))

    print("\n📊 对比数据：")
    print(f"  银企直连交易：{len(bank_txns)} 条")
    print(f"  进项发票：{len(input_invoices)} 条")
    print(f"  销项发票：{len(output_invoices)} 条")

    bank_total = sum(field_float(item, ["transactionAmount", "transAmount", "amount"]) for item in bank_txns)
    input_total = sum(field_float(item, ["feeInvoiceAmount", "amountTax", "amount"]) for item in input_invoices)
    output_total = sum(field_float(item, ["invoiceMoney", "invoiceMakeTotalAmount", "invoiceAmount", "amountTax"]) for item in output_invoices)

    matched_pairs: List[Dict[str, Any]] = []
    unmatched_bank = list(bank_txns)
    unmatched_input = list(input_invoices)
    unmatched_output = list(output_invoices)

    for invoice in input_invoices:
        invoice_amount = field_float(invoice, ["feeInvoiceAmount", "amountTax", "amount"])
        invoice_date = field_date(invoice, ["expensesDate", "expenseTime", "invoiceTime", "invoiceDate"])
        if not invoice_amount or not invoice_date:
            continue
        for bank in list(unmatched_bank):
            bank_amount = field_float(bank, ["transactionAmount", "transAmount", "amount"])
            bank_date = field_date(bank, ["orderDate", "accountDate", "transTime"])
            if abs(invoice_amount - bank_amount) < 0.01 and invoice_date == bank_date:
                matched_pairs.append(
                    {
                        "type": "进项发票 <-> 银企直连",
                        "invoice": invoice,
                        "bank_txn": bank,
                    }
                )
                unmatched_bank.remove(bank)
                if invoice in unmatched_input:
                    unmatched_input.remove(invoice)
                break

    for invoice in output_invoices:
        invoice_amount = field_float(invoice, ["invoiceMoney", "invoiceMakeTotalAmount", "invoiceAmount", "amountTax"])
        invoice_date = field_date(invoice, ["invoiceMakeDate", "invoiceDate"])
        if not invoice_amount or not invoice_date:
            continue
        for bank in list(unmatched_bank):
            bank_amount = field_float(bank, ["transactionAmount", "transAmount", "amount"])
            bank_date = field_date(bank, ["orderDate", "accountDate", "transTime"])
            if abs(invoice_amount - bank_amount) < 0.01 and invoice_date == bank_date:
                matched_pairs.append(
                    {
                        "type": "销项发票 <-> 银企直连",
                        "invoice": invoice,
                        "bank_txn": bank,
                    }
                )
                unmatched_bank.remove(bank)
                if invoice in unmatched_output:
                    unmatched_output.remove(invoice)
                break

    no_activity = not bank_txns and not input_invoices and not output_invoices
    if no_activity:
        reconciliation_status = "○ 当前期间无银企流水和发票数据"
        business_conclusion = "当前期间无可对账数据，也无可写入确认单管理的交易级记录。"
    elif not unmatched_bank and not unmatched_input and not unmatched_output:
        reconciliation_status = "✓ 完全匹配"
        business_conclusion = "当前期间银企流水与发票数据已完成匹配。"
    else:
        reconciliation_status = "⚠ 部分不匹配"
        business_conclusion = "当前期间存在未匹配的银企流水或发票，需人工复核。"

    return {
        "timestamp": datetime.now().isoformat(),
        "query_period": query_result.get("query_period"),
        "statistics": {
            "bank_total_amount": round(bank_total, 2),
            "input_total_amount": round(input_total, 2),
            "output_total_amount": round(output_total, 2),
            "bank_transaction_count": len(bank_txns),
            "input_invoice_count": len(input_invoices),
            "output_invoice_count": len(output_invoices),
        },
        "matched_pairs": matched_pairs,
        "unmatched": {
            "bank_transactions": unmatched_bank,
            "input_invoices": unmatched_input,
            "output_invoices": unmatched_output,
        },
        "summary": {
            "total_matched_pairs": len(matched_pairs),
            "unmatched_bank_count": len(unmatched_bank),
            "unmatched_invoice_count": len(unmatched_input) + len(unmatched_output),
            "reconciliation_status": reconciliation_status,
            "business_conclusion": business_conclusion,
            "no_activity": no_activity,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-result", default="query_result_2026_05.json")
    parser.add_argument("--output", default="comparison_report.json")
    args = parser.parse_args()

    query_result = parse_query_result(args.query_result)
    comparison = compare_data(query_result)

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(comparison, handle, indent=2, ensure_ascii=False)

    print(f"\n✅ 对比报告已生成：{args.output}")
    print("\n📋 对比摘要：")
    print(f"  银企直连 vs 发票：{comparison['summary']['total_matched_pairs']} 对已匹配")
    print(f"  未匹配银企交易：{comparison['summary']['unmatched_bank_count']} 条")
    print(f"  未匹配发票：{comparison['summary']['unmatched_invoice_count']} 张")
    print(f"  协调状态：{comparison['summary']['reconciliation_status']}")


if __name__ == "__main__":
    main()
