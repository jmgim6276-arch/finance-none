#!/usr/bin/env python3
"""
确认单管理探针 / 提交脚本。

说明：
- 财税通 UAT 当前“确认单管理”真实页面为 `/bill/query/confirmBill`
- 已确认接口：
  - 查询列表：`/api/bill/order-confirmation/queryOrderConfirmPage`
  - 新增确认单：`/api/bill/order-confirmation/submit`
  - 更新记录：`/api/bill/order-confirmation/update`
  - 提交已有记录：`/api/bill/order-confirmation/submitExpenses`
- 当前未发现通用“新增总结确认单”入口，因此这里不再盲猜 `/api/document/*`
"""

import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, "/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/scripts")

REAL_ENDPOINTS = {
    "page_route": "/bill/query/confirmBill",
    "query": "/api/bill/order-confirmation/queryOrderConfirmPage",
    "submit_new": "/api/bill/order-confirmation/submit",
    "update": "/api/bill/order-confirmation/update",
    "submit_existing": "/api/bill/order-confirmation/submitExpenses",
    "detail": "/api/bill/order-confirmation/detail",
    "query_by_verification": "/api/bill/order-confirmation/queryOrderConfirmsByVerification",
    "subject_tree_by_merchant": "/api/erp/accountingSubject/queryAccountingSubjectTreeByMerchantNo",
}

DEBIT_DIRECTION = 1
CREDIT_DIRECTION = -1
DEFAULT_INPUT_VAT_SUBJECT = {
    "subjectId": 80448,
    "subjectName": "应交税费_应交增值税",
    "subjectFullName": "应交税费_应交增值税",
    "subjectCode": "222101",
}
SUBJECT_TREE_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def build_headers(token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
        "X-Platform": "cst-pc",
        "x-token": token,
    }


def load_slip(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def post_json(base_url: str, endpoint: str, token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{base_url}{endpoint}"
    resp = requests.post(url, json=payload, headers=build_headers(token), timeout=20)
    data = resp.json() if resp.text else {}
    return {
        "url": url,
        "endpoint": endpoint,
        "status_code": resp.status_code,
        "ok": resp.ok and bool(data.get("success", data.get("code") == 200)),
        "payload": payload,
        "response": data,
    }


def query_confirm_bill_page(
    base_url: str,
    token: str,
    company_id: int,
    *,
    trans_no: Optional[str] = None,
    confirm_order_type: Optional[int] = None,
    invoice_number: Optional[str] = None,
    to_account_no: Optional[str] = None,
    pay_account_no: Optional[str] = None,
    page_size: int = 10,
) -> Dict[str, Any]:
    payload = {
        "merchantNos": [],
        "transNo": trans_no,
        "confirmOrderType": confirm_order_type,
        "invoiceNumber": invoice_number,
        "toAccountNo": to_account_no,
        "payAccountNo": pay_account_no,
        "pageSize": page_size,
        "pageNumber": 1,
        "confirmOrderTypes": ["1001", "1002", "1003", "1004", "1005", "1006", "2001", "2002", "2003", "2004", "2005"],
        "companyId": company_id,
    }
    return post_json(base_url, REAL_ENDPOINTS["query"], token, payload)


def first_text(*values: Any) -> Optional[str]:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def money(value: Any) -> float:
    try:
        decimal_value = Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        decimal_value = Decimal("0")
    return float(decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def normalize_account_no(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def build_voucher_diest(bank_txn: Dict[str, Any]) -> Optional[str]:
    return first_text(
        bank_txn.get("abstracts"),
        bank_txn.get("purpose"),
        bank_txn.get("bankRemarks"),
        bank_txn.get("orderNo"),
    )


def build_confirm_voucher_diest(bank_txn: Dict[str, Any]) -> Optional[str]:
    summary = first_text(
        bank_txn.get("abstracts"),
        bank_txn.get("bankRemarks"),
        bank_txn.get("orderNo"),
    )
    purpose = first_text(bank_txn.get("purpose"))
    if summary and purpose and purpose not in summary:
        return f"{summary}-{purpose}"
    return summary or purpose


def build_create_payload_from_pair(
    pair: Dict[str, Any],
    *,
    confirm_status: int,
    subject_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bank_txn = pair.get("bank_txn") or {}
    invoice = pair.get("invoice") or {}
    payload: Dict[str, Any] = {
        "confirmOrderType": 1001,
        "transNo": first_text(bank_txn.get("orderNo")),
        "detailNo": first_text(bank_txn.get("detailNo")),
        "invoiceNumber": first_text(invoice.get("invoiceNumber")),
        "confirmStatus": int(confirm_status),
    }
    voucher_diest = build_confirm_voucher_diest(bank_txn)
    if voucher_diest:
        payload["voucherDiest"] = voucher_diest

    project_id = bank_txn.get("projectId") or invoice.get("projectId")
    project_name = first_text(bank_txn.get("projectName"), invoice.get("projectName"))
    if project_id not in (None, ""):
        payload["projectId"] = project_id
    if project_name:
        payload["projectName"] = project_name

    contract_id = bank_txn.get("contractId") or invoice.get("contractId")
    contract_no = first_text(bank_txn.get("contractNo"), invoice.get("contractNo"))
    contract_name = first_text(bank_txn.get("contractName"), invoice.get("contractName"))
    if contract_id not in (None, ""):
        payload["contractId"] = contract_id
    if contract_no:
        payload["contractNo"] = contract_no
    if contract_name:
        payload["contractName"] = contract_name

    if subject_bundle and subject_bundle.get("ok"):
        payload.update(
            {
                "subjectId": (subject_bundle.get("bank_subject") or {}).get("subjectId"),
                "subjectName": (subject_bundle.get("bank_subject") or {}).get("subjectName"),
                "debitSubjectId": (subject_bundle.get("expense_subject") or {}).get("subjectId"),
                "debitSubjectName": (subject_bundle.get("expense_subject") or {}).get("subjectName"),
                "accountSubjects": subject_bundle.get("account_subjects"),
                "subjectJson": {
                    "subjects": subject_bundle.get("account_subjects") or [],
                    "voucherDiest": voucher_diest,
                },
            }
        )

    return payload


def extract_matched_pairs(slip: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((((slip or {}).get("details") or {}).get("matchedPairs") or []))


def extract_unmatched_bank_entries(slip: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((((slip or {}).get("details") or {}).get("unmatchedBankTransactions") or []))


def contains_text(value: Any, needle: str) -> bool:
    return needle in str(value or "")


def is_fee_like_bank_txn(bank_txn: Dict[str, Any]) -> bool:
    return any(
        contains_text(bank_txn.get(field), "手续费")
        for field in ("abstracts", "purpose", "remark")
    )


def pick_exception_confirm_order_type(item: Dict[str, Any]) -> int:
    bank_txn = item.get("bank_txn") or {}
    reason = str(item.get("reason") or "")
    counterparty_type = str(item.get("counterpartyType") or "")
    purpose_text = f"{bank_txn.get('abstracts') or ''} {bank_txn.get('purpose') or ''}"

    if "手续费" in purpose_text:
        return 3006
    if counterparty_type == "个人" or "个人" in reason:
        return 1002
    return 1001


def build_create_payload_from_unmatched_bank(item: Dict[str, Any], *, confirm_status: int) -> Dict[str, Any]:
    bank_txn = item.get("bank_txn") or {}
    reason = str(item.get("reason") or "").strip()
    payload: Dict[str, Any] = {
        "confirmOrderType": pick_exception_confirm_order_type(item),
        "transNo": first_text(bank_txn.get("orderNo")),
        "detailNo": first_text(bank_txn.get("detailNo")),
        "confirmStatus": int(confirm_status),
    }
    voucher_diest = build_voucher_diest(bank_txn)
    if voucher_diest:
        payload["voucherDiest"] = voucher_diest
    if reason:
        payload["remark"] = reason
    return payload


def exception_priority(item: Dict[str, Any]) -> tuple:
    bank_txn = item.get("bank_txn") or {}
    fee_like = is_fee_like_bank_txn(bank_txn)
    amount = float(bank_txn.get("amount") or 0)
    counterparty_type = str(item.get("counterpartyType") or "")
    personal = counterparty_type == "个人"
    return (1 if fee_like else 0, 0 if personal else 1, -amount)


def dedupe_exception_candidates(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        bank_txn = item.get("bank_txn") or {}
        trans_no = first_text(bank_txn.get("orderNo"))
        if not trans_no:
            continue
        grouped.setdefault(trans_no, []).append(item)

    selected: List[Dict[str, Any]] = []
    for trans_no in sorted(grouped):
        candidates = grouped[trans_no]
        candidates.sort(key=exception_priority)
        selected.append(candidates[0])
    return selected


def fetch_confirm_detail(base_url: str, token: str, company_id: int, confirm_id: int) -> Dict[str, Any]:
    url = f"{base_url}{REAL_ENDPOINTS['detail']}"
    resp = requests.get(
        url,
        params={"id": int(confirm_id), "companyId": company_id},
        headers=build_headers(token),
        timeout=20,
    )
    data = resp.json() if resp.text else {}
    return {
        "url": url,
        "status_code": resp.status_code,
        "ok": resp.ok and bool(data.get("success", data.get("code") == 200)),
        "response": data,
    }


def query_accounting_subject_tree(
    base_url: str,
    token: str,
    merchant_no: Optional[str],
    company_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    merchant_key = first_text(merchant_no)
    if not merchant_key:
        return []
    cache_key = f"{base_url}|{company_id}|{merchant_key}"
    if cache_key in SUBJECT_TREE_CACHE:
        return SUBJECT_TREE_CACHE[cache_key]

    url = f"{base_url}{REAL_ENDPOINTS['subject_tree_by_merchant']}"
    params: Dict[str, Any] = {"merchantNo": merchant_key}
    if company_id is not None:
        params["companyId"] = company_id
    resp = requests.get(
        url,
        params=params,
        headers=build_headers(token),
        timeout=20,
    )
    data = resp.json() if resp.text else {}
    result = data.get("result") or []
    SUBJECT_TREE_CACHE[cache_key] = result if isinstance(result, list) else []
    return SUBJECT_TREE_CACHE[cache_key]


def infer_bank_subject(
    base_url: str,
    token: str,
    company_id: int,
    pay_account_no: Optional[str],
    *,
    merchant_no: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    tree = query_accounting_subject_tree(base_url, token, merchant_no, company_id)
    normalized_pay_account_no = normalize_account_no(pay_account_no)
    if tree and normalized_pay_account_no:
        for subject in tree:
            if normalize_account_no(subject.get("bankAccountNo")) == normalized_pay_account_no:
                return {
                    "subjectId": subject.get("id"),
                    "subjectName": subject.get("subjectFullName") or subject.get("subjectName"),
                    "subjectCode": subject.get("subjectCode"),
                }

    if not pay_account_no:
        pay_account_no = None
    result = query_confirm_bill_page(
        base_url,
        token,
        company_id,
        pay_account_no=pay_account_no,
        page_size=100,
    )
    rows = (((result.get("response") or {}).get("result") or {}).get("data") or [])
    for row in rows:
        for subject in row.get("accountSubjects") or []:
            if subject.get("direction") in (-1, 2):
                return {
                    "subjectId": subject.get("subjectId"),
                    "subjectName": row.get("subjectName"),
                    "subjectCode": None,
                }
        if row.get("subjectId") and row.get("subjectName"):
            return {
                "subjectId": row.get("subjectId"),
                "subjectName": row.get("subjectName"),
                "subjectCode": None,
            }
    return None


def is_sales_related(bank_txn: Dict[str, Any], invoice: Optional[Dict[str, Any]] = None) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            bank_txn.get("purpose"),
            bank_txn.get("remark"),
            bank_txn.get("abstracts"),
            bank_txn.get("projectName"),
            (invoice or {}).get("sellerName"),
            (invoice or {}).get("remark"),
        )
    )
    sales_keywords = (
        "销售",
        "广告",
        "宣传",
        "市场",
        "推广",
        "客户",
        "物流",
        "运输",
        "发货",
        "售后",
    )
    return any(keyword in text for keyword in sales_keywords)


def infer_expense_subject(
    bank_txn: Dict[str, Any],
    invoice: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    text = " ".join(
        str(bank_txn.get(field) or "")
        for field in ("purpose", "remark", "abstracts")
    )
    sales_related = is_sales_related(bank_txn, invoice)
    keyword_map = [
        (
            ("电费", "水电"),
            {
                "management": {"subjectId": 80578, "subjectName": "管理费用_房租水电"},
                "sales": {"subjectId": 80577, "subjectName": "销售费用_房租水电"},
            },
        ),
        (
            ("车票", "交通"),
            {
                "management": {"subjectId": 80521, "subjectName": "管理费用_交通费"},
                "sales": {"subjectId": 80567, "subjectName": "销售费用_交通费"},
            },
        ),
        (
            ("差旅",),
            {
                "management": {"subjectId": 80520, "subjectName": "管理费用_差旅费"},
                "sales": {"subjectId": 80566, "subjectName": "销售费用_差旅费"},
            },
        ),
        (
            ("办公",),
            {
                "management": {"subjectId": 80517, "subjectName": "管理费用_办公费"},
                "sales": {"subjectId": 80581, "subjectName": "销售费用_办公费"},
            },
        ),
        (
            ("快递",),
            {
                "management": {"subjectId": 80571, "subjectName": "管理费用_快递费"},
                "sales": {"subjectId": 80569, "subjectName": "销售费用_快递费"},
            },
        ),
    ]
    for keywords, subjects in keyword_map:
        if any(keyword in text for keyword in keywords):
            return subjects["sales" if sales_related else "management"]
    return {
        "subjectId": 80509 if sales_related else 80515,
        "subjectName": "销售费用" if sales_related else "管理费用",
    }


def infer_input_vat_subject(
    base_url: str,
    token: str,
    company_id: int,
    merchant_no: Optional[str],
) -> Dict[str, Any]:
    tree = query_accounting_subject_tree(base_url, token, merchant_no, company_id)
    for subject in tree:
        subject_code = str(subject.get("subjectCode") or "")
        full_name = str(subject.get("subjectFullName") or "")
        name = str(subject.get("subjectName") or "")
        if subject_code == "222101" or "应交税费_应交增值税" == full_name or name == "应交增值税":
            return {
                "subjectId": subject.get("id"),
                "subjectName": full_name or name,
                "subjectCode": subject_code or DEFAULT_INPUT_VAT_SUBJECT["subjectCode"],
            }
    return dict(DEFAULT_INPUT_VAT_SUBJECT)


def build_account_subjects(
    base_url: str,
    token: str,
    company_id: int,
    *,
    bank_txn: Dict[str, Any],
    invoice: Optional[Dict[str, Any]] = None,
    pay_account_no: Optional[str] = None,
    merchant_no: Optional[str] = None,
) -> Dict[str, Any]:
    merchant_no = first_text(merchant_no, bank_txn.get("merchantNo"))
    pay_account_no = first_text(
        pay_account_no,
        bank_txn.get("paymentNo"),
        bank_txn.get("bankAccountNo"),
    )
    bank_subject = infer_bank_subject(
        base_url,
        token,
        company_id,
        pay_account_no,
        merchant_no=merchant_no,
    )
    expense_subject = infer_expense_subject(bank_txn, invoice)
    total_amount = money(
        (invoice or {}).get("invoiceTotalPrice")
        or (invoice or {}).get("totalPrice")
        or bank_txn.get("amount")
    )
    tax_amount = money(
        (invoice or {}).get("invoiceTax")
        or (invoice or {}).get("taxPrice")
        or (invoice or {}).get("tax")
        or 0
    )
    if tax_amount <= 0 or tax_amount >= total_amount:
        tax_amount = 0.0
    amount_without_tax = money(total_amount - tax_amount)
    voucher_diest = build_confirm_voucher_diest(bank_txn)

    if not bank_subject or not expense_subject or not total_amount:
        return {
            "ok": False,
            "reason": "无法推断科目分录所需的银行科目、费用科目或金额",
            "bank_subject": bank_subject,
            "expense_subject": expense_subject,
            "total_amount": total_amount,
            "tax_amount": tax_amount,
        }

    account_subjects = [
        {
            "direction": DEBIT_DIRECTION,
            "subjectId": expense_subject.get("subjectId"),
            "amount": amount_without_tax if tax_amount > 0 else total_amount,
        }
    ]
    input_vat_subject = None
    if tax_amount > 0:
        input_vat_subject = infer_input_vat_subject(
            base_url,
            token,
            company_id,
            merchant_no,
        )
        account_subjects.append(
            {
                "direction": DEBIT_DIRECTION,
                "subjectId": input_vat_subject.get("subjectId"),
                "amount": tax_amount,
            }
        )

    account_subjects.append(
        {
            "direction": CREDIT_DIRECTION,
            "subjectId": bank_subject.get("subjectId"),
            "amount": total_amount,
        }
    )

    return {
        "ok": True,
        "voucher_diest": voucher_diest,
        "bank_subject": bank_subject,
        "expense_subject": expense_subject,
        "input_vat_subject": input_vat_subject,
        "total_amount": total_amount,
        "tax_amount": tax_amount,
        "amount_without_tax": amount_without_tax if tax_amount > 0 else total_amount,
        "account_subjects": account_subjects,
    }


def enrich_confirm_with_subjects(
    base_url: str,
    token: str,
    company_id: int,
    *,
    confirm_id: int,
    bank_txn: Dict[str, Any],
    invoice: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    detail_result = fetch_confirm_detail(base_url, token, company_id, confirm_id)
    detail = (detail_result.get("response") or {}).get("result") or {}
    if not detail_result.get("ok") or not detail:
        return {
            "ok": False,
            "reason": "无法读取新建确认单详情",
            "detail_result": detail_result,
        }

    subject_bundle = build_account_subjects(
        base_url,
        token,
        company_id,
        bank_txn=bank_txn,
        invoice=invoice,
        pay_account_no=detail.get("payAccountNo"),
        merchant_no=detail.get("merchantNo") or bank_txn.get("merchantNo"),
    )
    if not subject_bundle.get("ok"):
        return {
            "ok": False,
            "reason": subject_bundle.get("reason") or "无法推断补充分录所需的科目或金额",
            "subject_bundle": subject_bundle,
        }

    payload = dict(detail)
    payload.update(
        {
            "subjectId": (subject_bundle.get("bank_subject") or {}).get("subjectId"),
            "subjectName": (subject_bundle.get("bank_subject") or {}).get("subjectName"),
            "debitSubjectId": (subject_bundle.get("expense_subject") or {}).get("subjectId"),
            "debitSubjectName": (subject_bundle.get("expense_subject") or {}).get("subjectName"),
            "voucherDiest": subject_bundle.get("voucher_diest"),
            "accountSubjects": subject_bundle.get("account_subjects"),
        }
    )
    payload["subjectJson"] = {
        "subjects": payload["accountSubjects"],
        "voucherDiest": payload["voucherDiest"],
    }
    update_result = post_json(base_url, REAL_ENDPOINTS["update"], token, payload)
    update_result["bank_subject"] = subject_bundle.get("bank_subject")
    update_result["expense_subject"] = subject_bundle.get("expense_subject")
    update_result["input_vat_subject"] = subject_bundle.get("input_vat_subject")
    update_result["amount_without_tax"] = subject_bundle.get("amount_without_tax")
    update_result["tax_amount"] = subject_bundle.get("tax_amount")
    return update_result


def submit_new_confirm(
    base_url: str,
    token: str,
    payload: Dict[str, Any],
    *,
    company_id: Optional[int] = None,
) -> Dict[str, Any]:
    primary = post_json(base_url, REAL_ENDPOINTS["submit_new"], token, payload)
    if primary.get("ok"):
        return primary

    response = primary.get("response") or {}
    message = str(response.get("message") or response.get("msg") or "")
    if company_id is None or "company" not in message.lower():
        return primary

    fallback_payload = dict(payload)
    fallback_payload["companyId"] = company_id
    fallback = post_json(base_url, REAL_ENDPOINTS["submit_new"], token, fallback_payload)
    fallback["fallback_from"] = primary
    return fallback


def submit_existing_confirm(base_url: str, token: str, company_id: int, confirm_id: int) -> Dict[str, Any]:
    payload = {
        "id": int(confirm_id),
        "companyId": company_id,
    }
    return post_json(base_url, REAL_ENDPOINTS["submit_existing"], token, payload)


def update_existing_confirm(
    base_url: str,
    token: str,
    company_id: int,
    payload_path: str,
) -> Dict[str, Any]:
    with open(payload_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload["companyId"] = company_id
    return post_json(base_url, REAL_ENDPOINTS["update"], token, payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slip", default="reconciliation_slip.json")
    parser.add_argument("--auto-login", action="store_true")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--company-name")
    parser.add_argument(
        "--create-matched",
        action="store_true",
        help="按确认单 submit 接口，把 slip.details.matchedPairs 里的匹配结果新增为确认单",
    )
    parser.add_argument(
        "--create-exceptions",
        action="store_true",
        help="按确认单 submit 接口，把 slip.details.unmatchedBankTransactions 里的候选写入异常池",
    )
    parser.add_argument(
        "--confirm-status",
        type=int,
        default=1,
        choices=[0, 1, 2, 3, 4],
        help="新增确认单时使用的状态，默认 1=待确认",
    )
    parser.add_argument(
        "--max-create",
        type=int,
        default=0,
        help="新增确认单时最多创建多少条；0 表示不限制",
    )
    parser.add_argument("--confirm-id", type=int, help="已有确认单 ID；传入后调用 submitExpenses")
    parser.add_argument("--update-payload", help="已有确认单更新 payload JSON；传入后调用 update")
    parser.add_argument("--output", default="submit_to_cst_result.json")
    args = parser.parse_args()

    slip = load_slip(args.slip)

    try:
        from browser_session import get_auth

        if args.auto_login:
            username = args.username or os.environ.get("CST_USERNAME")
            password = args.password or os.environ.get("CST_PASSWORD")
            token, company_id, _, browser_name = get_auth(
                auto_login=True,
                username=username,
                password=password,
                company_name=args.company_name,
            )
        else:
            token, company_id, _, browser_name = get_auth(auto_login=False)
        print(f"✅ 已登录：{browser_name} (companyId={company_id})")
    except Exception as exc:
        print(f"❌ 登录失败：{exc}")
        return

    base_url = os.environ.get("CST_BASE_URL", "https://cstuat.uf-tree.com").rstrip("/")

    result: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "slip_title": slip.get("title"),
        "company_id": company_id,
        "base_url": base_url,
        "page_route": REAL_ENDPOINTS["page_route"],
        "real_endpoints": REAL_ENDPOINTS,
    }

    if slip.get("summary", {}).get("bankTransactionCount", 0) == 0 and slip.get("summary", {}).get("inputInvoiceCount", 0) == 0 and slip.get("summary", {}).get("outputInvoiceCount", 0) == 0:
        result["success"] = False
        result["skipped"] = True
        result["message"] = "当前期间无银企流水和发票数据，无需写入确认单管理。"
    elif args.create_matched:
        matched_pairs = extract_matched_pairs(slip)
        creation_items = []
        for pair in matched_pairs:
            subject_bundle = build_account_subjects(
                base_url,
                token,
                company_id,
                bank_txn=pair.get("bank_txn") or {},
                invoice=pair.get("invoice") or {},
                merchant_no=(pair.get("bank_txn") or {}).get("merchantNo"),
            )
            creation_items.append(
                {
                    "pair": pair,
                    "subject_bundle": subject_bundle,
                    "payload": build_create_payload_from_pair(
                        pair,
                        confirm_status=args.confirm_status,
                        subject_bundle=subject_bundle,
                    ),
                }
            )
        if args.max_create > 0:
            creation_items = creation_items[: args.max_create]

        result["action"] = "create_matched"
        result["planned_create_count"] = len(creation_items)
        result["create_results"] = []

        seen_trans_nos = set()
        success_count = 0
        skipped_count = 0
        for item in creation_items:
            pair = item.get("pair") or {}
            payload = item.get("payload") or {}
            trans_no = payload.get("transNo")
            if not trans_no:
                result["create_results"].append(
                    {
                        "ok": False,
                        "skipped": True,
                        "reason": "payload 缺少 transNo",
                        "payload": payload,
                    }
                )
                skipped_count += 1
                continue
            if trans_no in seen_trans_nos:
                result["create_results"].append(
                    {
                        "ok": False,
                        "skipped": True,
                        "reason": "本次批次内 transNo 重复，按 transNo 去重后跳过",
                        "payload": payload,
                    }
                )
                skipped_count += 1
                continue
            seen_trans_nos.add(trans_no)

            existing = query_confirm_bill_page(
                base_url,
                token,
                company_id,
                trans_no=trans_no,
                confirm_order_type=int(payload.get("confirmOrderType") or 1001),
                page_size=20,
            )
            existing_rows = (((existing.get("response") or {}).get("result") or {}).get("data") or [])
            if existing.get("ok") and existing_rows:
                result["create_results"].append(
                    {
                        "ok": False,
                        "skipped": True,
                        "reason": "系统中已存在相同 transNo 的确认单记录",
                        "payload": payload,
                        "existing_rows": existing_rows,
                    }
                )
                skipped_count += 1
                continue

            create_result = submit_new_confirm(
                base_url,
                token,
                payload,
                company_id=company_id,
            )
            if create_result.get("ok"):
                created_rows = (((query_confirm_bill_page(
                    base_url,
                    token,
                    company_id,
                    trans_no=trans_no,
                    confirm_order_type=int(payload.get("confirmOrderType") or 1001),
                    page_size=20,
                ).get("response") or {}).get("result") or {}).get("data") or [])
                if created_rows:
                    created_rows.sort(key=lambda row: row.get("createdTime") or "", reverse=True)
                    create_result["created_rows"] = created_rows
                    create_result["post_update_result"] = enrich_confirm_with_subjects(
                        base_url,
                        token,
                        company_id,
                        confirm_id=int(created_rows[0].get("id")),
                        bank_txn=pair.get("bank_txn") or {},
                        invoice=pair.get("invoice") or {},
                    )
            result["create_results"].append(create_result)
            if create_result.get("ok"):
                success_count += 1

        result["success"] = success_count > 0
        result["created_count"] = success_count
        result["skipped_count"] = skipped_count
        if success_count:
            result["message"] = f"已新增 {success_count} 条确认单"
        else:
            result["message"] = "没有新增确认单；请查看 create_results 中的跳过或失败原因。"
    elif args.create_exceptions:
        unmatched_bank = dedupe_exception_candidates(extract_unmatched_bank_entries(slip))
        creation_payloads = [
            build_create_payload_from_unmatched_bank(item, confirm_status=4)
            for item in unmatched_bank
        ]
        if args.max_create > 0:
            creation_payloads = creation_payloads[: args.max_create]

        result["action"] = "create_exceptions"
        result["planned_create_count"] = len(creation_payloads)
        result["create_results"] = []

        success_count = 0
        skipped_count = 0
        for payload in creation_payloads:
            trans_no = payload.get("transNo")
            if not trans_no:
                result["create_results"].append(
                    {
                        "ok": False,
                        "skipped": True,
                        "reason": "payload 缺少 transNo",
                        "payload": payload,
                    }
                )
                skipped_count += 1
                continue

            existing = query_confirm_bill_page(
                base_url,
                token,
                company_id,
                trans_no=trans_no,
                confirm_order_type=int(payload.get("confirmOrderType") or 1001),
                page_size=20,
            )
            existing_rows = (((existing.get("response") or {}).get("result") or {}).get("data") or [])
            if existing.get("ok") and existing_rows:
                result["create_results"].append(
                    {
                        "ok": False,
                        "skipped": True,
                        "reason": "系统中已存在相同 transNo 的确认单记录",
                        "payload": payload,
                        "existing_rows": existing_rows,
                    }
                )
                skipped_count += 1
                continue

            create_result = submit_new_confirm(
                base_url,
                token,
                payload,
                company_id=company_id,
            )
            result["create_results"].append(create_result)
            if create_result.get("ok"):
                success_count += 1

        result["success"] = success_count > 0
        result["created_count"] = success_count
        result["skipped_count"] = skipped_count
        if success_count:
            result["message"] = f"已新增 {success_count} 条异常池确认单"
        else:
            result["message"] = "没有新增异常池确认单；请查看 create_results 中的跳过或失败原因。"
    elif args.confirm_id is not None:
        result["action"] = "submit_existing"
        result["submit_result"] = submit_existing_confirm(base_url, token, company_id, args.confirm_id)
        result["success"] = bool(result["submit_result"].get("ok"))
    elif args.update_payload:
        result["action"] = "update_existing"
        result["update_result"] = update_existing_confirm(base_url, token, company_id, args.update_payload)
        result["success"] = bool(result["update_result"].get("ok"))
    else:
        result["action"] = "probe_only"
        result["query_result"] = query_confirm_bill_page(base_url, token, company_id)
        result["success"] = False
        result["message"] = (
            "确认单管理当前只暴露列表查询、更新、提交已有记录的接口。"
            " 页面未发现可直接新增‘流水与发票对账确认单’的通用入口。"
        )

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)

    print(f"\n📋 结果已保存：{args.output}")
    if result.get("success"):
        print("✅ 已完成确认单管理动作")
    else:
        print(f"⚠️  {result.get('message')}")


if __name__ == "__main__":
    main()
