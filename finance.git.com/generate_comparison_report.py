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


def normalize_name(value: Any) -> str:
    return "".join(str(value or "").split())


def classify_counterparty(name: Any) -> str:
    cleaned = normalize_name(name)
    if not cleaned:
        return "未知"
    return "个人" if len(cleaned) < 4 else "公司"


def standardize_business_type(value: Any) -> Dict[str, str]:
    raw = str(value or "").strip().upper()
    if raw in {"SUB", "减少", "减少(贷)"}:
        return {"code": "SUB", "label": "减少(贷)"}
    if raw in {"ADD", "增加", "增加(借)"}:
        return {"code": "ADD", "label": "增加(借)"}
    return {"code": raw or "UNKNOWN", "label": str(value or "UNKNOWN")}


def extract_input_invoices(query_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = extract_records(query_result.get("input_fetch_invoices"))
    if records:
        return records
    return extract_records(query_result.get("input_fee_invoices"))


def invoice_total_amount(invoice: Dict[str, Any]) -> float:
    return field_float(
        invoice,
        [
            "invoiceTotalPrice",
            "totalPrice",
            "invoiceMakeTotalAmount",
            "feeInvoiceAmount",
            "amountTax",
            "amount",
        ],
    )


def make_bank_reason(reason: str, bank: Dict[str, Any], *, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        "reason": reason,
        "businessType": standardize_business_type(bank.get("businessType")),
        "counterpartyType": classify_counterparty(bank.get("outBankAccountName")),
        "bank_txn": bank,
    }
    if extra:
        payload.update(extra)
    return payload


def compare_data(query_result: Dict[str, Any]) -> Dict[str, Any]:
    bank_txns = extract_records(query_result.get("bank_transactions"))
    input_invoices = extract_input_invoices(query_result)
    output_invoices = extract_records(query_result.get("output_invoices"))

    print("\n📊 对比数据：")
    print(f"  银企直连交易：{len(bank_txns)} 条")
    print(f"  进项发票：{len(input_invoices)} 条")
    print(f"  销项发票：{len(output_invoices)} 条")

    bank_total = sum(field_float(item, ["transactionAmount", "transAmount", "amount"]) for item in bank_txns)
    input_total = sum(invoice_total_amount(item) for item in input_invoices)
    output_total = sum(field_float(item, ["invoiceMoney", "invoiceMakeTotalAmount", "invoiceAmount", "amountTax"]) for item in output_invoices)

    matched_pairs: List[Dict[str, Any]] = []
    unmatched_bank: List[Dict[str, Any]] = []
    unmatched_input: List[Dict[str, Any]] = []
    unmatched_output: List[Dict[str, Any]] = []
    used_invoice_ids = set()

    candidate_map: Dict[str, List[Dict[str, Any]]] = {}
    for invoice in input_invoices:
        seller_name = normalize_name(invoice.get("sellerName"))
        amount = invoice_total_amount(invoice)
        if not seller_name or not amount:
            unmatched_input.append(
                {
                    "reason": "进项发票缺少销方名称或价税合计，当前版本不自动匹配",
                    "invoice": invoice,
                }
            )
            continue
        key = f"{seller_name}|{amount:.2f}"
        candidate_map.setdefault(key, []).append(invoice)

    for bank in bank_txns:
        business_type = standardize_business_type(bank.get("businessType"))
        amount = field_float(bank, ["transactionAmount", "transAmount", "amount"])
        counterparty_name = normalize_name(bank.get("outBankAccountName"))
        counterparty_type = classify_counterparty(counterparty_name)

        if business_type["code"] != "SUB":
            unmatched_bank.append(
                make_bank_reason("当前版本只自动处理银企直连“减少(贷)”的进项发票匹配", bank)
            )
            continue
        if counterparty_type != "公司":
            unmatched_bank.append(
                make_bank_reason("对方银行户名字数少于四个字，按个人处理，不自动匹配进项发票", bank)
            )
            continue
        if not counterparty_name or not amount:
            unmatched_bank.append(
                make_bank_reason("银行流水缺少对方户名或订单金额，当前版本不自动匹配", bank)
            )
            continue

        key = f"{counterparty_name}|{amount:.2f}"
        candidates = [
            invoice
            for invoice in candidate_map.get(key, [])
            if str(invoice.get("id")) not in used_invoice_ids
        ]
        if not candidates:
            unmatched_bank.append(
                make_bank_reason(
                    "未找到销方名称和订单金额都完全一致的进项发票",
                    bank,
                )
            )
            continue
        if len(candidates) > 1:
            unmatched_bank.append(
                make_bank_reason(
                    "存在多张同名同金额进项发票，当前版本不做自动归并",
                    bank,
                    extra={
                        "candidateInvoices": candidates,
                    },
                )
            )
            continue

        invoice = candidates[0]
        used_invoice_ids.add(str(invoice.get("id")))
        matched_pairs.append(
            {
                "type": "进项发票(发票获取) <-> 银企直连减少(贷)",
                "matchBasis": [
                    "businessType = 减少(贷)",
                    "sellerName = outBankAccountName",
                    "invoiceTotalPrice = amount",
                ],
                "invoice": invoice,
                "bank_txn": bank,
            }
        )

    for invoice in input_invoices:
        invoice_id = str(invoice.get("id"))
        if invoice_id in used_invoice_ids:
            continue
        if any(entry.get("invoice") is invoice for entry in unmatched_input):
            continue
        unmatched_input.append(
            {
                "reason": "未找到满足减少(贷) + 销方名称一致 + 金额一致的银企直连流水",
                "invoice": invoice,
            }
        )

    for invoice in output_invoices:
        unmatched_output.append(
            {
                "reason": "当前版本未开放销项发票自动匹配，先保留为待人工复核数据",
                "invoice": invoice,
            }
        )

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
            "matching_rule_version": "v1-exact-counterparty-and-amount",
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
