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
}


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
    page_size: int = 10,
) -> Dict[str, Any]:
    payload = {
        "merchantNos": [],
        "transNo": trans_no,
        "confirmOrderType": confirm_order_type,
        "invoiceNumber": None,
        "toAccountNo": None,
        "payAccountNo": None,
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


def build_voucher_diest(bank_txn: Dict[str, Any]) -> Optional[str]:
    return first_text(
        bank_txn.get("abstracts"),
        bank_txn.get("purpose"),
        bank_txn.get("bankRemarks"),
        bank_txn.get("orderNo"),
    )


def build_create_payload_from_pair(pair: Dict[str, Any], *, confirm_status: int) -> Dict[str, Any]:
    bank_txn = pair.get("bank_txn") or {}
    invoice = pair.get("invoice") or {}
    payload: Dict[str, Any] = {
        "confirmOrderType": 1001,
        "transNo": first_text(bank_txn.get("orderNo")),
        "detailNo": first_text(bank_txn.get("detailNo")),
        "invoiceNumber": first_text(invoice.get("invoiceNumber")),
        "confirmStatus": int(confirm_status),
    }
    voucher_diest = build_voucher_diest(bank_txn)
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

    return payload


def extract_matched_pairs(slip: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((((slip or {}).get("details") or {}).get("matchedPairs") or []))


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
        creation_payloads = [
            build_create_payload_from_pair(pair, confirm_status=args.confirm_status)
            for pair in matched_pairs
        ]
        if args.max_create > 0:
            creation_payloads = creation_payloads[: args.max_create]

        result["action"] = "create_matched"
        result["planned_create_count"] = len(creation_payloads)
        result["create_results"] = []

        seen_trans_nos = set()
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
