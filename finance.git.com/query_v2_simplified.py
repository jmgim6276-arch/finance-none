#!/usr/bin/env python3
"""
简化对账查询脚本。

用于“银企直连 + 进项发票 + 销项发票”对账前的数据拉取，
输出统一的 records 结构，避免下游脚本重复适配财税通原始返回。
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

import requests

sys.path.insert(0, "/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/scripts")

BASE_URL = os.environ.get("CST_BASE_URL", "https://cst.uf-tree.com").rstrip("/")
HEADERS_TEMPLATE = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "X-Platform": "cst-pc",
}


def build_headers(token: str) -> Dict[str, str]:
    headers = HEADERS_TEMPLATE.copy()
    headers["x-token"] = token
    return headers


def response_to_records(
    endpoint: str,
    payload: Dict[str, Any],
    resp: requests.Response,
) -> Dict[str, Any]:
    data = resp.json()
    result = data.get("result") or {}
    records = list(result.get("data") or [])
    total_count = int(result.get("totalCount") or len(records) or 0)
    page_number = int(result.get("pageNumber") or payload.get("pageNumber") or 1)
    page_size = int(result.get("pageSize") or payload.get("pageSize") or len(records) or 0)
    ok = resp.ok and data.get("code") == 200
    return {
        "ok": ok,
        "endpoint": endpoint,
        "status_code": resp.status_code,
        "payload": payload,
        "data": {
            "pageNumber": page_number,
            "pageSize": page_size,
            "totalCount": total_count,
            "records": records,
        },
        "error": None if ok else data.get("message") or data.get("msg"),
        "raw_message": data.get("message"),
    }


def query_bank(token: str, company_id: int, start_date: str, end_date: str, page_size: int) -> Dict[str, Any]:
    url = f"{BASE_URL}/api/pay/transactionRecord/queryPage"
    payload = {
        "companyId": company_id,
        "merchantNos": [],
        "startOrderDate": start_date,
        "endOrderDate": end_date,
        "pageNumber": 1,
        "pageSize": page_size,
    }
    try:
        resp = requests.post(url, json=payload, headers=build_headers(token), timeout=20)
        return response_to_records("/api/pay/transactionRecord/queryPage", payload, resp)
    except Exception as exc:
        return {
            "ok": False,
            "endpoint": "/api/pay/transactionRecord/queryPage",
            "payload": payload,
            "data": {"records": [], "totalCount": 0, "pageNumber": 1, "pageSize": page_size},
            "error": str(exc),
        }


def query_input_fetch(token: str, company_id: int, start_date: str, end_date: str, page_size: int) -> Dict[str, Any]:
    url = f"{BASE_URL}/api/invoice/inputinvoice/queryInputInvoicePage"
    payload = {
        "pageSize": page_size,
        "pageNumber": 1,
        "invoiceClass": None,
        "invoiceNumber": None,
        "invoiceCode": None,
        "buyerName": None,
        "buyerTaxNo": None,
        "sellerName": None,
        "sellerTaxNo": None,
        "bizDate": [],
        "bizDateStart": start_date,
        "bizDateEnd": end_date,
        "companyId": company_id,
    }
    try:
        resp = requests.post(url, json=payload, headers=build_headers(token), timeout=20)
        base = response_to_records("/api/invoice/inputinvoice/queryInputInvoicePage", payload, resp)
        if base.get("ok"):
            return base
        if "缺少请求体" not in str(base.get("error") or ""):
            return base

        fallback_payload = {
            "pageSize": page_size,
            "pageNumber": 1,
            "invoiceClass": None,
            "invoiceNumber": None,
            "invoiceCode": None,
            "buyerName": None,
            "buyerTaxNo": None,
            "sellerName": None,
            "sellerTaxNo": None,
            "bizDate": [],
            "bizDateStart": None,
            "bizDateEnd": None,
            "companyId": company_id,
        }
        fallback_resp = requests.post(
            url,
            json=fallback_payload,
            headers=build_headers(token),
            timeout=20,
        )
        fallback = response_to_records(
            "/api/invoice/inputinvoice/queryInputInvoicePage",
            fallback_payload,
            fallback_resp,
        )
        base["unfiltered_probe"] = fallback
        if not fallback.get("ok"):
            return base

        all_records = list((fallback.get("data") or {}).get("records") or [])
        filtered = filter_by_date(all_records, start_date, end_date, "bizDate")
        base["ok"] = True
        base["error"] = None
        base["resolved_via_client_side_filter"] = True
        base["note"] = "进项发票(发票获取)按无筛选全量列表拉取后，再按 bizDate 本地过滤"
        base["data"] = {
            "records_total_count": len(all_records),
            "records_filtered_count": len(filtered),
            "records": filtered,
        }
        return base
    except Exception as exc:
        return {
            "ok": False,
            "endpoint": "/api/invoice/inputinvoice/queryInputInvoicePage",
            "payload": payload,
            "data": {"records": [], "totalCount": 0, "pageNumber": 1, "pageSize": page_size},
            "error": str(exc),
        }


def normalize_date_text(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def filter_by_date(records: List[Dict[str, Any]], start_date: str, end_date: str, date_field: str) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for record in records:
        date_text = normalize_date_text(record.get(date_field))
        if date_text and start_date <= date_text <= end_date:
            filtered.append(record)
    return filtered


def query_output(token: str, company_id: int, start_date: str, end_date: str, page_size: int) -> Dict[str, Any]:
    url = f"{BASE_URL}/api/invoice/salesInvoice/queryInvoiceDetailPage"
    payload = {
        "pageSize": page_size,
        "pageNumber": 1,
        "invoiceApplyType": None,
        "invoiceRedStatus": None,
        "orderNo": None,
        "merchantNo": None,
        "invoiceType": None,
        "invoiceNumber": None,
        "invoiceMakeDateStart": None,
        "invoiceMakeDateEnd": None,
        "invoiceMakeDate": [],
        "companyId": company_id,
    }
    try:
        resp = requests.post(url, json=payload, headers=build_headers(token), timeout=20)
        base = response_to_records("/api/invoice/salesInvoice/queryInvoiceDetailPage", payload, resp)
        all_records = list((base.get("data") or {}).get("records") or [])
        filtered = filter_by_date(all_records, start_date, end_date, "invoiceMakeDate")
        base["data"] = {
            "records_total_count": len(all_records),
            "records_filtered_count": len(filtered),
            "records": filtered,
        }
        base["note"] = "销项发票按无筛选全量列表拉取后，再按 invoiceMakeDate 本地过滤"
        return base
    except Exception as exc:
        return {
            "ok": False,
            "endpoint": "/api/invoice/salesInvoice/queryInvoiceDetailPage",
            "payload": payload,
            "data": {
                "records_total_count": 0,
                "records_filtered_count": 0,
                "records": [],
            },
            "error": str(exc),
        }


def count_records(section: Dict[str, Any]) -> int:
    data = section.get("data") or {}
    if "records_filtered_count" in data:
        return int(data.get("records_filtered_count") or 0)
    return len(data.get("records") or [])


def main() -> None:
    from browser_session import get_auth

    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="2026-05-01")
    parser.add_argument("--end-date", default="2026-05-31")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--auto-login", action="store_true")
    parser.add_argument("--username", help="登录手机号")
    parser.add_argument("--password", help="登录密码")
    parser.add_argument("--company-name", help="集团名称")
    parser.add_argument("--output", default="query_result_simplified.json")
    args = parser.parse_args()

    try:
        if args.auto_login:
            username = args.username or os.environ.get("CST_USERNAME")
            password = args.password or os.environ.get("CST_PASSWORD")
            token, company_id, user_id, browser_name = get_auth(
                auto_login=True,
                username=username,
                password=password,
                company_name=args.company_name,
            )
        else:
            token, company_id, user_id, browser_name = get_auth(auto_login=False)

        print(f"\n✅ 已登录：{browser_name} (companyId={company_id})")
    except Exception as exc:
        print(f"❌ 登录失败: {exc}")
        return

    print(f"\n🔍 开始查询数据 ({args.start_date} ~ {args.end_date})...")

    bank_result = query_bank(token, company_id, args.start_date, args.end_date, args.page_size)
    input_fetch_result = query_input_fetch(token, company_id, args.start_date, args.end_date, args.page_size)
    output_result = query_output(token, company_id, args.start_date, args.end_date, args.page_size)

    result = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "company_id": company_id,
        "user_id": user_id,
        "browser": browser_name,
        "query_period": {
            "start_date": args.start_date,
            "end_date": args.end_date,
        },
        "bank_transactions": bank_result,
        "input_fetch_invoices": input_fetch_result,
        "output_invoices": output_result,
    }

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)

    print(f"✅ 数据查询完成，已保存到 {args.output}")
    print("\n结果摘要：")
    print(f"  银企直连：{'✓' if bank_result.get('ok') else '✗'} ({count_records(bank_result)} 条)")
    print(f"  进项发票：{'✓' if input_fetch_result.get('ok') else '✗'} ({count_records(input_fetch_result)} 条)")
    print(f"  销项发票：{'✓' if output_result.get('ok') else '✗'} ({count_records(output_result)} 条)")


if __name__ == "__main__":
    main()
