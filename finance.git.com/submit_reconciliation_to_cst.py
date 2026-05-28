#!/usr/bin/env python3
"""
确认单管理探针 / 提交脚本。

说明：
- 财税通 UAT 当前“确认单管理”真实页面为 `/bill/query/confirmBill`
- 已确认接口：
  - 查询列表：`/api/bill/order-confirmation/queryOrderConfirmPage`
  - 更新记录：`/api/bill/order-confirmation/update`
  - 提交已有记录：`/api/bill/order-confirmation/submitExpenses`
- 当前未发现通用“新增总结确认单”入口，因此这里不再盲猜 `/api/document/*`
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

import requests

sys.path.insert(0, "/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/scripts")

REAL_ENDPOINTS = {
    "page_route": "/bill/query/confirmBill",
    "query": "/api/bill/order-confirmation/queryOrderConfirmPage",
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
        "response": data,
    }


def query_confirm_bill_page(base_url: str, token: str, company_id: int) -> Dict[str, Any]:
    payload = {
        "merchantNos": [],
        "transNo": None,
        "confirmOrderType": None,
        "invoiceNumber": None,
        "toAccountNo": None,
        "payAccountNo": None,
        "pageSize": 10,
        "pageNumber": 1,
        "confirmOrderTypes": ["1001", "1002", "1003", "1004", "1005", "1006", "2001", "2002", "2003", "2004", "2005"],
        "companyId": company_id,
    }
    return post_json(base_url, REAL_ENDPOINTS["query"], token, payload)


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
