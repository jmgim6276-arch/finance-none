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


def extract_section_counts(section: Optional[Dict[str, Any]]) -> Dict[str, int]:
    records = extract_records(section)
    if not isinstance(section, dict):
        return {
            "records_total_count": len(records),
            "records_filtered_count": len(records),
        }
    data = section.get("data") or {}
    return {
        "records_total_count": int(
            data.get("records_total_count")
            or data.get("totalCount")
            or len(records)
            or 0
        ),
        "records_filtered_count": int(
            data.get("records_filtered_count")
            or len(records)
            or 0
        ),
    }


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


def invoice_tax_amount(invoice: Dict[str, Any]) -> float:
    return field_float(
        invoice,
        [
            "invoiceTax",
            "taxPrice",
            "taxAmount",
            "tax",
        ],
    )


def output_invoice_total_amount(invoice: Dict[str, Any]) -> float:
    return field_float(
        invoice,
        [
            "invoiceMakeTotalAmount",
            "invoiceMoney",
            "invoiceAmount",
            "amountTax",
            "amount",
        ],
    )


def has_bank_receipt(bank: Dict[str, Any]) -> bool:
    return bool(bank.get("ereceiptUrl") or bank.get("attachment"))


def make_bank_reason(reason: str, bank: Dict[str, Any], *, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        "reason": reason,
        "businessType": standardize_business_type(bank.get("businessType")),
        "counterpartyType": classify_counterparty(bank.get("outBankAccountName")),
        "hasBankReceipt": has_bank_receipt(bank),
        "bank_txn": bank,
    }
    if extra:
        payload.update(extra)
    return payload


def compare_data(query_result: Dict[str, Any]) -> Dict[str, Any]:
    bank_section = query_result.get("bank_transactions")
    input_section = query_result.get("input_fetch_invoices") or query_result.get("input_fee_invoices")
    output_section = query_result.get("output_invoices")

    bank_txns = extract_records(bank_section)
    input_invoices = extract_input_invoices(query_result)
    output_invoices = extract_records(output_section)
    bank_counts = extract_section_counts(bank_section)
    input_counts = extract_section_counts(input_section)
    output_counts = extract_section_counts(output_section)

    print("\n📊 对比数据：")
    print(
        f"  银企直连交易：{bank_counts['records_filtered_count']} 条"
        f"（全量 {bank_counts['records_total_count']} 条）"
    )
    print(
        f"  进项发票：{input_counts['records_filtered_count']} 条"
        f"（全量 {input_counts['records_total_count']} 条）"
    )
    print(
        f"  销项发票：{output_counts['records_filtered_count']} 条"
        f"（全量 {output_counts['records_total_count']} 条）"
    )

    bank_total = sum(field_float(item, ["transactionAmount", "transAmount", "amount"]) for item in bank_txns)
    input_total = sum(invoice_total_amount(item) for item in input_invoices)
    output_total = sum(output_invoice_total_amount(item) for item in output_invoices)

    matched_pairs: List[Dict[str, Any]] = []
    unmatched_bank: List[Dict[str, Any]] = []
    unmatched_input: List[Dict[str, Any]] = []
    unmatched_output: List[Dict[str, Any]] = []
    used_input_invoice_ids = set()
    used_output_invoice_ids = set()
    accounts_payable_candidates: List[Dict[str, Any]] = []
    accounts_receivable_candidates: List[Dict[str, Any]] = []

    input_candidate_map: Dict[str, List[Dict[str, Any]]] = {}
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
        input_candidate_map.setdefault(key, []).append(invoice)

    output_candidate_map: Dict[str, List[Dict[str, Any]]] = {}
    for invoice in output_invoices:
        buyer_name = normalize_name(invoice.get("buyerName"))
        amount = output_invoice_total_amount(invoice)
        if not buyer_name or not amount:
            unmatched_output.append(
                {
                    "reason": "销项发票缺少购方名称或价税合计，当前版本不自动匹配收款流水",
                    "invoice": invoice,
                }
            )
            continue
        key = f"{buyer_name}|{amount:.2f}"
        output_candidate_map.setdefault(key, []).append(invoice)

    for bank in bank_txns:
        business_type = standardize_business_type(bank.get("businessType"))
        amount = field_float(bank, ["transactionAmount", "transAmount", "amount"])
        counterparty_name = normalize_name(bank.get("outBankAccountName"))
        counterparty_type = classify_counterparty(counterparty_name)

        if business_type["code"] not in {"SUB", "ADD"}:
            unmatched_bank.append(
                make_bank_reason("当前版本只自动处理银企直连“减少(贷)”和“增加(借)”的发票匹配", bank)
            )
            continue
        if counterparty_type != "公司":
            unmatched_bank.append(
                make_bank_reason("对方银行户名字数少于四个字，按个人处理，不自动匹配公司发票", bank)
            )
            continue
        if not counterparty_name or not amount:
            unmatched_bank.append(
                make_bank_reason("银行流水缺少对方户名或订单金额，当前版本不自动匹配", bank)
            )
            continue

        key = f"{counterparty_name}|{amount:.2f}"
        if business_type["code"] == "SUB":
            candidates = [
                invoice
                for invoice in input_candidate_map.get(key, [])
                if str(invoice.get("id")) not in used_input_invoice_ids
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
            if not has_bank_receipt(bank):
                unmatched_bank.append(
                    make_bank_reason(
                        "已找到同名同额进项发票，但该银行流水无回单，不自动生成支出发票确认单",
                        bank,
                        extra={"candidateInvoice": invoice},
                    )
                )
                continue

            used_input_invoice_ids.add(str(invoice.get("id")))
            matched_pairs.append(
                {
                    "type": "进项发票(发票获取) <-> 银企直连减少(贷)",
                    "confirmOrderType": 1001,
                    "confirmOrderTypeName": "支出发票确认单（对公）",
                    "hasBankReceipt": True,
                    "matchBasis": [
                        "businessType = 减少(贷)",
                        "sellerName = outBankAccountName",
                        "invoiceTotalPrice = amount",
                        "ereceiptUrl/attachment 非空",
                    ],
                    "invoice": invoice,
                    "bank_txn": bank,
                }
            )
            continue

        candidates = [
            invoice
            for invoice in output_candidate_map.get(key, [])
            if str(invoice.get("id")) not in used_output_invoice_ids
        ]
        if not candidates:
            unmatched_bank.append(
                make_bank_reason(
                    "未找到购方名称和订单金额都完全一致的销项发票",
                    bank,
                )
            )
            continue
        if len(candidates) > 1:
            unmatched_bank.append(
                make_bank_reason(
                    "存在多张同名同金额销项发票，当前版本不做自动归并",
                    bank,
                    extra={
                        "candidateInvoices": candidates,
                    },
                )
            )
            continue

        invoice = candidates[0]
        if not has_bank_receipt(bank):
            unmatched_bank.append(
                make_bank_reason(
                    "已找到同名同额销项发票，但该银行流水无回单，不自动生成收款发票确认单",
                    bank,
                    extra={"candidateInvoice": invoice},
                )
            )
            continue

        used_output_invoice_ids.add(str(invoice.get("id")))
        matched_pairs.append(
            {
                "type": "销项发票 <-> 银企直连增加(借)",
                "confirmOrderType": 2001,
                "confirmOrderTypeName": "收款发票确认单",
                "hasBankReceipt": True,
                "matchBasis": [
                    "businessType = 增加(借)",
                    "buyerName = outBankAccountName",
                    "invoiceMakeTotalAmount = amount",
                    "ereceiptUrl/attachment 非空",
                ],
                "invoice": invoice,
                "bank_txn": bank,
            }
        )

    for invoice in input_invoices:
        invoice_id = str(invoice.get("id"))
        if invoice_id in used_input_invoice_ids:
            continue
        if any(entry.get("invoice") is invoice for entry in unmatched_input):
            continue
        payable_candidate = {
            "confirmOrderType": 1004,
            "confirmOrderTypeName": "应付账款确认单",
            "requiresBankReceipt": False,
            "invoiceDirection": "进项",
            "invoice": invoice,
            "amountWithoutTax": money_text(invoice_total_amount(invoice) - invoice_tax_amount(invoice)),
            "taxAmount": money_text(invoice_tax_amount(invoice)),
            "totalAmount": money_text(invoice_total_amount(invoice)),
            "reason": "当前期间未匹配到可确认的付款回单，保留为应付账款确认单候选",
        }
        unmatched_input.append(
            {
                "reason": "未找到满足减少(贷) + 回单存在 + 销方名称一致 + 金额一致的银企直连流水",
                "candidateConfirm": payable_candidate,
                "invoice": invoice,
            }
        )
        accounts_payable_candidates.append(payable_candidate)

    for invoice in output_invoices:
        invoice_id = str(invoice.get("id"))
        if invoice_id in used_output_invoice_ids:
            continue
        if any(entry.get("invoice") is invoice for entry in unmatched_output):
            continue
        receivable_candidate = {
            "confirmOrderType": 2003,
            "confirmOrderTypeName": "应收账款确认单",
            "requiresBankReceipt": False,
            "invoiceDirection": "销项",
            "invoice": invoice,
            "amountWithoutTax": money_text(output_invoice_total_amount(invoice) - invoice_tax_amount(invoice)),
            "taxAmount": money_text(invoice_tax_amount(invoice)),
            "totalAmount": money_text(output_invoice_total_amount(invoice)),
            "reason": "当前期间未匹配到可确认的收款回单，保留为应收账款确认单候选",
        }
        unmatched_output.append(
            {
                "reason": "未找到满足增加(借) + 回单存在 + 购方名称一致 + 金额一致的银企直连流水",
                "candidateConfirm": receivable_candidate,
                "invoice": invoice,
            }
        )
        accounts_receivable_candidates.append(receivable_candidate)

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
            "bank_transaction_count": bank_counts["records_filtered_count"],
            "bank_transaction_full_count": bank_counts["records_total_count"],
            "input_invoice_count": input_counts["records_filtered_count"],
            "input_invoice_full_count": input_counts["records_total_count"],
            "output_invoice_count": output_counts["records_filtered_count"],
            "output_invoice_full_count": output_counts["records_total_count"],
        },
        "matched_pairs": matched_pairs,
        "candidate_confirms": {
            "accounts_payable": accounts_payable_candidates,
            "accounts_receivable": accounts_receivable_candidates,
        },
        "unmatched": {
            "bank_transactions": unmatched_bank,
            "input_invoices": unmatched_input,
            "output_invoices": unmatched_output,
        },
        "summary": {
            "total_matched_pairs": len(matched_pairs),
            "unmatched_bank_count": len(unmatched_bank),
            "unmatched_invoice_count": len(unmatched_input) + len(unmatched_output),
            "accounts_payable_candidate_count": len(accounts_payable_candidates),
            "accounts_receivable_candidate_count": len(accounts_receivable_candidates),
            "reconciliation_status": reconciliation_status,
            "business_conclusion": business_conclusion,
            "no_activity": no_activity,
            "matching_rule_version": "v2-receipt-aware-payable-receivable-candidates",
        },
    }


def money_text(value: Any) -> str:
    return f"{field_float({'value': value}, ['value']):.2f}"


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
