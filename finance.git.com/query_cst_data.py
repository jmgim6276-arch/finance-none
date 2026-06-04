#!/usr/bin/env python3
"""
财税通查询脚本：
1. 查询银企直连明细数据
2. 查询进项发票（费用发票查询 / 发票获取）
3. 查询销项发票

说明：
- 本脚本已对齐 UAT 前端真实请求体，不再猜测旧接口或旧字段名。
- “进项发票”在前端里有两套查询：
  1. 发票查询：/api/bill/feeInvoice/queryInvoicePage
  2. 发票获取：/api/invoice/inputinvoice/queryInputInvoicePage
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

import requests

sys.path.insert(0, "/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/scripts")

BASE_URL = os.environ.get("CST_BASE_URL", "https://cst.uf-tree.com").rstrip("/")
HEADERS_TEMPLATE = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "X-Platform": "cst-pc",
}


def is_ok(resp: Dict[str, Any]) -> bool:
    return resp.get("code") == 200 or resp.get("success") is True


def build_headers(token: str) -> Dict[str, str]:
    headers = HEADERS_TEMPLATE.copy()
    headers["x-token"] = token
    return headers


def post_query(
    token: str,
    endpoint: str,
    payload: Dict[str, Any],
    *,
    page_route: str,
    ui_date_field: str,
    request_date_fields: Dict[str, str],
    timeout: int = 20,
) -> Dict[str, Any]:
    url = f"{BASE_URL}{endpoint}"
    result: Dict[str, Any] = {
        "endpoint": endpoint,
        "page_route": page_route,
        "ui_date_field": ui_date_field,
        "request_date_fields": request_date_fields,
        "payload": payload,
        "base_url": BASE_URL,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=build_headers(token),
            timeout=timeout,
        )
        result["status_code"] = response.status_code
        result["raw_resp"] = response.text[:1000]
        try:
            data = response.json()
        except ValueError:
            data = None

        result["data"] = data
        if data is None:
            result["ok"] = False
            result["error"] = "响应不是合法 JSON"
            return result

        result["ok"] = response.ok and is_ok(data)
        if not result["ok"]:
            result["error"] = (
                data.get("msg")
                or data.get("message")
                or f"接口返回非成功状态（HTTP {response.status_code}）"
            )
        if result["ok"]:
            return result

        error_text = f"{result.get('error') or ''}{result.get('raw_resp') or ''}"
        if "缺少请求体" in error_text:
            browser_result = post_query_via_page_vm(
                token,
                endpoint,
                payload,
                page_route=page_route,
            )
            if not browser_result.get("ok"):
                browser_result = post_query_in_browser(
                    token,
                    endpoint,
                    payload,
                    page_route=page_route,
                )
            browser_result.update(
                {
                    "page_route": page_route,
                    "ui_date_field": ui_date_field,
                    "request_date_fields": request_date_fields,
                    "payload": payload,
                    "base_url": BASE_URL,
                    "transport": "browser-fetch",
                    "fallback_reason": "requests 返回 缺少请求体，改用页面上下文 fetch",
                }
            )
            return browser_result

        return result
    except requests.exceptions.RequestException as exc:
        result["ok"] = False
        result["error"] = f"{exc.__class__.__name__}: {exc}"
        return result


def ensure_query_page(page_route: str) -> Dict[str, Any]:
    from browser_session import find_browser, get_page_by_url, open_target

    browser = find_browser(require_cst=True)
    if not browser:
        raise RuntimeError("未找到已登录的财税通浏览器，无法执行页面上下文查询")

    full_url = f"{BASE_URL}{page_route}"
    page = get_page_by_url(browser, page_route)
    if page:
        return page
    return open_target(browser, full_url)


def parse_cdp_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {"raw": raw}
    return {"raw": raw}


def post_query_in_browser(
    token: str,
    endpoint: str,
    payload: Dict[str, Any],
    *,
    page_route: str,
) -> Dict[str, Any]:
    from browser_session import cdp_eval

    page = ensure_query_page(page_route)
    expression = f"""
    (async () => {{
      const response = await fetch({json.dumps(endpoint)}, {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "Accept": "application/json, text/plain, */*",
          "X-Platform": "cst-pc",
          "X-Token": {json.dumps(token)}
        }},
        body: JSON.stringify({json.dumps(payload, ensure_ascii=False)})
      }});
      const text = await response.text();
      let data = null;
      try {{
        data = JSON.parse(text);
      }} catch (e) {{
        data = null;
      }}
      return JSON.stringify({{
        status_code: response.status,
        raw_resp: text.slice(0, 1000),
        data
      }});
    }})()
    """
    raw = cdp_eval(page, expression, await_promise=True)
    info = parse_cdp_json(raw)
    data = info.get("data")
    result: Dict[str, Any] = {
        "status_code": info.get("status_code"),
        "raw_resp": info.get("raw_resp"),
        "data": data,
        "ok": isinstance(data, dict) and is_ok(data),
    }
    if not result["ok"]:
        result["error"] = (
            (data or {}).get("msg")
            or (data or {}).get("message")
            or "页面上下文查询返回非成功状态"
        )
    return result


def post_query_via_page_vm(
    token: str,
    endpoint: str,
    payload: Dict[str, Any],
    *,
    page_route: str,
) -> Dict[str, Any]:
    del token
    from browser_session import cdp_eval

    page = ensure_query_page(page_route)
    expression = f"""
    (async () => {{
      function findVm(vm, predicate) {{
        if (!vm) return null;
        if (predicate(vm)) return vm;
        for (const child of (vm.$children || [])) {{
          const found = findVm(child, predicate);
          if (found) return found;
        }}
        return null;
      }}

      const root = document.querySelector('#app') && document.querySelector('#app').__vue__;
      const endpoint = {json.dumps(endpoint)};
      const payload = {json.dumps(payload, ensure_ascii=False)};
      const pageNumber = payload.pageNumber || 1;
      const pageSize = payload.pageSize || 10;
      const formValues = Object.assign({{}}, payload);
      delete formValues.pageNumber;
      delete formValues.pageSize;
      delete formValues.companyId;

      let vm = null;
      if (endpoint === "/api/invoice/inputinvoice/queryInputInvoicePage") {{
        vm = findVm(root, item =>
          item &&
          item.$options &&
          item.$options.name === "income-manager" &&
          item.queryForm &&
          Object.prototype.hasOwnProperty.call(item.queryForm, "bizDate")
        );
      }} else if (endpoint === "/api/invoice/salesInvoice/queryInvoiceDetailPage") {{
        vm = findVm(root, item =>
          item &&
          item.$options &&
          item.$options.name === "output-income-manager"
        );
      }} else if (endpoint === "/api/bill/feeInvoice/queryInvoicePage") {{
        vm = findVm(root, item =>
          item &&
          item.$options &&
          item.$options.name === "income-manager" &&
          item.queryForm &&
          Object.prototype.hasOwnProperty.call(item.queryForm, "expensesNo")
        );
      }} else if (endpoint === "/api/pay/transactionRecord/queryPage") {{
        vm = findVm(root, item =>
          item &&
          item.$options &&
          item.$options.name === "transaction-record"
        );
      }}

      if (!vm || typeof vm.queryTable !== "function") {{
        return JSON.stringify({{
          ok: false,
          error: "vm-not-found-or-queryTable-missing",
          endpoint
        }});
      }}

      Object.assign(vm.queryForm || vm.oQueryOptions || {{}}, formValues);
      const res = await vm.queryTable(pageNumber, pageSize);
      return JSON.stringify({{
        ok: true,
        data: res
      }});
    }})()
    """
    raw = cdp_eval(page, expression, await_promise=True)
    info = parse_cdp_json(raw)
    data = info.get("data")
    result: Dict[str, Any] = {
        "status_code": 200 if isinstance(data, dict) else None,
        "raw_resp": json.dumps(data, ensure_ascii=False)[:1000] if data is not None else raw,
        "data": data,
        "ok": isinstance(data, dict) and is_ok(data),
    }
    if not result["ok"]:
        result["error"] = (
            info.get("error")
            or (data or {}).get("msg")
            or (data or {}).get("message")
            or "页面组件查询返回非成功状态"
        )
    return result


def query_bank_transactions(
    token: str,
    company_id: int,
    start_date: str,
    end_date: str,
    *,
    page_size: int,
    page_number: int,
) -> Dict[str, Any]:
    payload = {
        "companyId": company_id,
        "merchantNos": [],
        "startOrderDate": start_date,
        "endOrderDate": end_date,
        "pageNumber": page_number,
        "pageSize": page_size,
    }
    return post_query(
        token,
        "/api/pay/transactionRecord/queryPage",
        payload,
        page_route="/transaction/transaction-record",
        ui_date_field="orderDate",
        request_date_fields={
            "start": "startOrderDate",
            "end": "endOrderDate",
        },
    )


def query_input_fee_invoices(
    token: str,
    company_id: int,
    start_date: str,
    end_date: str,
    *,
    page_size: int,
    page_number: int,
) -> Dict[str, Any]:
    payload = {
        "pageSize": page_size,
        "pageNumber": page_number,
        "invoiceStatus": None,
        "status": None,
        "expensesNo": None,
        "projectId": None,
        "expensesTitle": None,
        "invoiceCode": None,
        "invoiceNumber": None,
        "submitName": None,
        "merchantNo": None,
        "submitDate": [],
        "expensesStartTime": start_date,
        "expensesEndTime": end_date,
        "submitInvoiceDate": [],
        "invoiceStartTime": start_date,
        "invoiceEndTime": end_date,
        "feeTypeId": None,
        "companyId": company_id,
    }
    return post_query(
        token,
        "/api/bill/feeInvoice/queryInvoicePage",
        payload,
        page_route="/invoice/input-invoice",
        ui_date_field="submitDate + submitInvoiceDate",
        request_date_fields={
            "submit_start": "expensesStartTime",
            "submit_end": "expensesEndTime",
            "invoice_start": "invoiceStartTime",
            "invoice_end": "invoiceEndTime",
        },
    )


def query_input_fetch_invoices(
    token: str,
    company_id: int,
    start_date: str,
    end_date: str,
    *,
    page_size: int,
    page_number: int,
) -> Dict[str, Any]:
    payload = {
        "pageSize": page_size,
        "pageNumber": page_number,
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
    result = post_query(
        token,
        "/api/invoice/inputinvoice/queryInputInvoicePage",
        payload,
        page_route="/invoice/input-invoice",
        ui_date_field="bizDate",
        request_date_fields={
            "start": "bizDateStart",
            "end": "bizDateEnd",
        },
    )
    if not result.get("ok") and "缺少请求体" in str(result.get("error") or ""):
        probe_result = fetch_full_input_fetch_invoices(
            token,
            company_id,
            page_size=max(1000, page_size),
        )
        result["unfiltered_probe"] = probe_result
        if probe_result.get("ok"):
            client_side_filtered = filter_input_fetch_invoices_locally(
                probe_result,
                start_date=start_date,
                end_date=end_date,
            )
            result["client_side_filtered"] = client_side_filtered
            result["diagnosis"] = (
                "发票获取接口本身可访问，但当前 UAT 在带 bizDateStart/"
                "bizDateEnd/bizDate 的日期筛选时返回 缺少请求体。"
                " 这更像后端日期筛选链路问题，不是账号权限不足。"
            )
            if client_side_filtered.get("ok") and client_side_filtered.get("complete_dataset"):
                filtered_records = client_side_filtered.get("filtered_records") or []
                result["upstream_error"] = result.get("error")
                result["upstream_ok"] = False
                result["resolved_via_client_side_filter"] = True
                result["ok"] = True
                result["error"] = None
                result["message"] = (
                    "已通过无筛选全量进项发票获取列表完成本地日期过滤"
                    if filtered_records
                    else "该时间段无进项发票"
                )
                result["data"] = {
                    "success": True,
                    "message": result["message"],
                    "code": 200,
                    "result": {
                        "pageNumber": 1,
                        "pageSize": len(filtered_records),
                        "totalPages": 1,
                        "totalCount": len(filtered_records),
                        "data": filtered_records,
                        "extInfos": {
                            "filterMode": "client-side-bizDate",
                            "sourceTotalCount": client_side_filtered.get("source_total_count"),
                        },
                    },
                }
    return result


def fetch_full_input_fetch_invoices(
    token: str,
    company_id: int,
    *,
    page_size: int = 1000,
) -> Dict[str, Any]:
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
        "bizDateStart": None,
        "bizDateEnd": None,
        "companyId": company_id,
    }
    return post_query(
        token,
        "/api/invoice/inputinvoice/queryInputInvoicePage",
        payload,
        page_route="/invoice/input-invoice",
        ui_date_field="bizDate",
        request_date_fields={
            "start": "bizDateStart",
            "end": "bizDateEnd",
        },
    )


def filter_input_fetch_invoices_locally(
    probe_result: Dict[str, Any],
    *,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    result_data = ((probe_result or {}).get("data") or {}).get("result") or {}
    records = list(result_data.get("data") or [])
    total_count = int(result_data.get("totalCount") or len(records) or 0)
    page_size = int(result_data.get("pageSize") or len(records) or 10)

    filtered = []
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    for item in records:
        raw = (item or {}).get("bizDate")
        if not raw:
            continue
        date_text = str(raw).strip()[:10]
        try:
            current = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue
        if start_dt <= current <= end_dt:
            filtered.append(item)

    complete = len(records) >= total_count or page_size >= total_count
    return {
        "ok": True,
        "filter_mode": "client_side_bizDate",
        "complete_dataset": complete,
        "source_total_count": total_count,
        "filtered_count": len(filtered),
        "filtered_records": filtered,
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "note": (
            "由于 UAT 后端日期筛选返回 缺少请求体，当前结果基于无筛选进项发票获取列表做本地 bizDate 过滤。"
        ),
    }


def query_output_invoices(
    token: str,
    company_id: int,
    start_date: str,
    end_date: str,
    *,
    page_size: int,
    page_number: int,
) -> Dict[str, Any]:
    payload = {
        "pageSize": page_size,
        "pageNumber": page_number,
        "invoiceApplyType": None,
        "invoiceRedStatus": None,
        "orderNo": None,
        "merchantNo": None,
        "invoiceType": None,
        "invoiceNumber": None,
        "invoiceMakeDateEnd": end_date,
        "invoiceMakeDateStart": start_date,
        "invoiceMakeDate": [],
        "companyId": company_id,
    }
    result = post_query(
        token,
        "/api/invoice/salesInvoice/queryInvoiceDetailPage",
        payload,
        page_route="/invoice/output-invoice",
        ui_date_field="invoiceMakeDate",
        request_date_fields={
            "start": "invoiceMakeDateStart",
            "end": "invoiceMakeDateEnd",
        },
    )
    if not result.get("ok") and "缺少请求体" in str(result.get("error") or ""):
        probe_payload = {
            "pageSize": page_size,
            "pageNumber": page_number,
            "invoiceApplyType": None,
            "invoiceRedStatus": None,
            "orderNo": None,
            "merchantNo": None,
            "invoiceType": None,
            "invoiceNumber": None,
            "invoiceMakeDateEnd": None,
            "invoiceMakeDateStart": None,
            "invoiceMakeDate": [],
            "companyId": company_id,
        }
        probe_result = post_query(
            token,
            "/api/invoice/salesInvoice/queryInvoiceDetailPage",
            probe_payload,
            page_route="/invoice/output-invoice",
            ui_date_field="invoiceMakeDate",
            request_date_fields={
                "start": "invoiceMakeDateStart",
                "end": "invoiceMakeDateEnd",
            },
        )
        result["unfiltered_probe"] = probe_result
        if probe_result.get("ok"):
            full_unfiltered = fetch_full_output_invoices(
                token,
                company_id,
                page_size=max(1000, page_size),
            )
            result["full_unfiltered"] = full_unfiltered
            client_side_filtered = filter_output_invoices_locally(
                full_unfiltered if full_unfiltered.get("ok") else probe_result,
                start_date=start_date,
                end_date=end_date,
            )
            result["client_side_filtered"] = client_side_filtered
            result["diagnosis"] = (
                "销项发票接口本身可访问，但当前 UAT 在带 invoiceMakeDateStart/"
                "invoiceMakeDateEnd/invoiceMakeDate 的日期筛选时返回 缺少请求体。"
                " 这更像后端日期筛选链路问题，不是账号权限不足。"
            )
            if client_side_filtered.get("ok") and client_side_filtered.get("complete_dataset"):
                filtered_records = client_side_filtered.get("filtered_records") or []
                result["upstream_error"] = result.get("error")
                result["upstream_ok"] = False
                result["resolved_via_client_side_filter"] = True
                result["ok"] = True
                result["error"] = None
                result["message"] = (
                    "已通过无筛选全量销项列表完成本地日期过滤"
                    if filtered_records
                    else "该时间段无销项发票"
                )
                result["data"] = {
                    "success": True,
                    "message": result["message"],
                    "code": 200,
                    "result": {
                        "pageNumber": 1,
                        "pageSize": len(filtered_records),
                        "totalPages": 1,
                        "totalCount": len(filtered_records),
                        "data": filtered_records,
                        "extInfos": {
                            "filterMode": "client-side-invoiceMakeDate",
                            "sourceTotalCount": client_side_filtered.get("source_total_count"),
                        },
                    },
                }
    return result


def fetch_full_output_invoices(
    token: str,
    company_id: int,
    *,
    page_size: int = 1000,
) -> Dict[str, Any]:
    payload = {
        "pageSize": page_size,
        "pageNumber": 1,
        "invoiceApplyType": None,
        "invoiceRedStatus": None,
        "orderNo": None,
        "merchantNo": None,
        "invoiceType": None,
        "invoiceNumber": None,
        "invoiceMakeDateEnd": None,
        "invoiceMakeDateStart": None,
        "invoiceMakeDate": [],
        "companyId": company_id,
    }
    return post_query(
        token,
        "/api/invoice/salesInvoice/queryInvoiceDetailPage",
        payload,
        page_route="/invoice/output-invoice",
        ui_date_field="invoiceMakeDate",
        request_date_fields={
            "start": "invoiceMakeDateStart",
            "end": "invoiceMakeDateEnd",
        },
    )


def filter_output_invoices_locally(
    probe_result: Dict[str, Any],
    *,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    result_data = ((probe_result or {}).get("data") or {}).get("result") or {}
    records = list(result_data.get("data") or [])
    total_count = int(result_data.get("totalCount") or len(records) or 0)
    page_size = int(result_data.get("pageSize") or len(records) or 10)
    page_number = int(result_data.get("pageNumber") or 1)

    filtered = []
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    for item in records:
        raw = (item or {}).get("invoiceMakeDate")
        if not raw:
            continue
        date_text = str(raw).strip()[:10]
        try:
            current = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue
        if start_dt <= current <= end_dt:
            filtered.append(item)

    complete = len(records) >= total_count or page_size >= total_count
    return {
        "ok": True,
        "filter_mode": "client_side_invoiceMakeDate",
        "complete_dataset": complete,
        "source_total_count": total_count,
        "filtered_count": len(filtered),
        "filtered_records": filtered,
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "note": (
            "由于 UAT 后端日期筛选返回 缺少请求体，当前结果基于无筛选销项列表做本地 invoiceMakeDate 过滤。"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按财税通前端真实参数读取交易/发票数据")
    parser.add_argument("--start-date", default="2026-05-01", help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-05-31", help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument(
        "--input-mode",
        choices=["fee", "fetch", "both"],
        default="both",
        help="进项发票查询模式：费用发票查询 / 发票获取 / 两者都查",
    )
    parser.add_argument("--page-size", type=int, default=1000, help="每页条数")
    parser.add_argument("--page-number", type=int, default=1, help="页码")
    parser.add_argument(
        "--output",
        default="/Users/kaixuanchuangzhi/.openclaw/workspace/finance.git.com/query_result.json",
        help="输出 JSON 路径",
    )
    parser.add_argument(
        "--auto-login",
        action="store_true",
        help="自动登录财税通（使用环境变量或参数中的账号密码）",
    )
    parser.add_argument(
        "--username",
        help="登录手机号（不传则用 CST_USERNAME 环境变量）",
    )
    parser.add_argument(
        "--password",
        help="登录密码（不传则用 CST_PASSWORD 环境变量）",
    )
    parser.add_argument(
        "--company-name",
        help="期望进入的集团/公司名称（可选）",
    )
    return parser.parse_args()


def main() -> None:
    from browser_session import get_auth

    args = parse_args()

    try:
        # 根据 --auto-login 标志决定是否自动登录
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
        
        print("\n✅ 从浏览器获取登录信息：")
        print(f"   Token 前12位: {token[:12]}...")
        print(f"   Company ID: {company_id}")
        print(f"   Browser: {browser_name}\n")
    except Exception as exc:
        print(f"❌ 无法获取登录信息: {exc}")
        return

    bank_result = query_bank_transactions(
        token,
        company_id,
        args.start_date,
        args.end_date,
        page_size=args.page_size,
        page_number=args.page_number,
    )

    input_fee_result = None
    input_fetch_result = None
    if args.input_mode in {"fee", "both"}:
        input_fee_result = query_input_fee_invoices(
            token,
            company_id,
            args.start_date,
            args.end_date,
            page_size=args.page_size,
            page_number=args.page_number,
        )
    if args.input_mode in {"fetch", "both"}:
        input_fetch_result = query_input_fetch_invoices(
            token,
            company_id,
            args.start_date,
            args.end_date,
            page_size=args.page_size,
            page_number=args.page_number,
        )

    output_result = query_output_invoices(
        token,
        company_id,
        args.start_date,
        args.end_date,
        page_size=args.page_size,
        page_number=args.page_number,
    )

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
        "input_fee_invoices": input_fee_result,
        "input_fetch_invoices": input_fetch_result,
        "output_invoices": output_result,
    }

    print("=" * 60)
    print("银企直连查询结果：")
    print("=" * 60)
    print(json.dumps(bank_result, indent=2, ensure_ascii=False))

    if input_fee_result is not None:
        print("\n" + "=" * 60)
        print("进项发票（发票查询）结果：")
        print("=" * 60)
        print(json.dumps(input_fee_result, indent=2, ensure_ascii=False))

    if input_fetch_result is not None:
        print("\n" + "=" * 60)
        print("进项发票（发票获取）结果：")
        print("=" * 60)
        print(json.dumps(input_fetch_result, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("销项发票查询结果：")
    print("=" * 60)
    print(json.dumps(output_result, indent=2, ensure_ascii=False))

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 查询结果已保存到: {args.output}")


if __name__ == "__main__":
    main()
