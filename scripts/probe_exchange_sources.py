#!/usr/bin/env python3
"""Probe official exchange endpoints used for warehouse receipts and position ranks."""

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT = ROOT / "scripts" / "fetch_china_futures_snapshot.py"


def load_fetch_module():
    spec = importlib.util.spec_from_file_location("fetch_china_futures_snapshot", FETCH_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact_date(value):
    text = str(value or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text.replace("-", "")
    if re.match(r"^\d{8}$", text):
        return text
    return dt.date.today().strftime("%Y%m%d")


def classify_error(status=None, error=None, body=b""):
    text = f"{status or ''} {error or ''} {body[:4096]!r}"
    lower_text = text.lower()
    if status == 200 and (
        "html challenge" in lower_text
        or "$_ts" in text
        or "document.createelement" in lower_text
        or "document.cookie" in lower_text
        or "content=\"0;" in lower_text
        or "settimeout(" in lower_text
        or "waf" in lower_text
        or "precondition failed" in lower_text
    ):
        return "blocked_by_exchange_waf"
    if status == 200:
        return "reachable"
    if status == 404 or "HTTP Error 404" in text:
        return "no_data_for_date"
    if status == 412 or "Precondition Failed" in text or "HTTP Error 412" in text:
        return "blocked_by_exchange_waf"
    if "NameResolutionError" in text or "getaddrinfo failed" in text or "Failed to resolve" in text:
        return "dns_or_network_failure"
    if "timed out" in text or "timeout" in text.lower():
        return "timeout"
    return "source_error"


def request_probe(name, method, url, params=None, data=None, timeout=12):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data else None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
        "Accept": "*/*",
    }
    if encoded:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=encoded, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096)
            status = response.status
            content_type = response.headers.get("content-type")
    except urllib.error.HTTPError as exc:
        body = exc.read(4096)
        status = exc.code
        content_type = exc.headers.get("content-type") if exc.headers else None
        return {
            "name": name,
            "url": url,
            "status": status,
            "content_type": content_type,
            "category": classify_error(status=status, body=body),
            "detail": str(exc),
        }
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "status": None,
            "content_type": None,
            "category": classify_error(error=exc),
            "detail": str(exc),
        }
    category = classify_error(status=status, body=body)
    detail = f"{len(body)} sample bytes"
    if status == 200 and category == "blocked_by_exchange_waf":
        detail = "HTML challenge page returned"
    if (
        status == 200
        and name.startswith("position_rank")
        and "export" in url.lower()
        and content_type
        and "text/html" in content_type.lower()
    ):
        category = "blocked_by_exchange_waf"
        detail = "position export returned HTML instead of a download payload"
    return {
        "name": name,
        "url": url,
        "status": status,
        "content_type": content_type,
        "category": category,
        "detail": detail,
    }


def probes_for(normalized, date):
    code = (normalized.get("product_code") or "").upper()
    exchange = normalized.get("exchange")
    lower = code.lower()
    year = date[:4]
    month_zero = str(int(date[4:6]) - 1)
    day = date[6:]
    if exchange == "CZCE":
        base = f"http://www.czce.com.cn/cn/DFSStaticFiles/Future/{year}/{date}"
        return [
            ("warehouse_receipt", "GET", f"{base}/FutureDataWhsheet.xls", None, None),
            ("position_rank", "GET", f"{base}/FutureDataHolding.xls", None, None),
        ]
    if exchange == "DCE":
        return [
            (
                "warehouse_receipt",
                "GET",
                "http://www.dce.com.cn/publicweb/quotesdata/wbillWeeklyQuotes.html",
                {"wbillWeeklyQuotes.variety": "all", "year": year, "month": month_zero, "day": day},
                None,
            ),
            (
                "warehouse_receipt_mirror",
                "GET",
                "http://www.dlspjys.cn/publicweb/quotesdata/wbillWeeklyQuotes.html",
                {"wbillWeeklyQuotes.variety": "all", "year": year, "month": month_zero, "day": day},
                None,
            ),
            (
                "position_rank",
                "POST",
                "http://www.dce.com.cn/publicweb/quotesdata/exportMemberDealPosiQuotesBatchData.html",
                None,
                {
                    "memberDealPosiQuotes.variety": lower,
                    "memberDealPosiQuotes.trade_type": "0",
                    "contract.contract_id": "all",
                    "contract.variety_id": lower,
                    "year": year,
                    "month": month_zero,
                    "day": day,
                    "batchExportFlag": "batch",
                },
            ),
            (
                "position_rank_mirror",
                "POST",
                "http://www.dlspjys.cn/publicweb/quotesdata/exportMemberDealPosiQuotesBatchData.html",
                None,
                {
                    "memberDealPosiQuotes.variety": lower,
                    "memberDealPosiQuotes.trade_type": "0",
                    "contract.contract_id": "all",
                    "contract.variety_id": lower,
                    "year": year,
                    "month": month_zero,
                    "day": day,
                    "batchExportFlag": "batch",
                },
            ),
        ]
    if exchange == "SHFE":
        return [
            ("warehouse_receipt", "GET", f"https://tsite.shfe.com.cn/data/dailydata/{date}dailystock.dat", None, None),
            ("warehouse_receipt_direct", "GET", f"https://www.shfe.com.cn/data/tradedata/future/dailydata/{date}dailystock.dat", None, None),
            ("position_rank", "GET", f"https://tsite.shfe.com.cn/data/dailydata/kx/pm{date}.dat", None, None),
            ("position_rank_direct", "GET", f"https://www.shfe.com.cn/data/tradedata/future/dailydata/pm{date}.dat", None, None),
        ]
    if exchange == "GFEX":
        return [
            (
                "warehouse_receipt",
                "POST",
                "http://www.gfex.com.cn/u/interfacesWebTdWbillWeeklyQuotes/loadList",
                None,
                {"gen_date": date},
            ),
            (
                "position_rank",
                "GET",
                "http://www.gfex.com.cn/gfex/rcjccpm/hqsj_tjsj.shtml",
                None,
                None,
            ),
            (
                "position_rank_contracts",
                "POST",
                "http://www.gfex.com.cn/u/interfacesWebTiMemberDealPosiQuotes/loadListContract_id",
                None,
                {"variety": lower, "trade_date": date},
            ),
            (
                "position_rank_api",
                "POST",
                "http://www.gfex.com.cn/u/interfacesWebTiMemberDealPosiQuotes/loadList",
                None,
                {
                    "trade_date": date,
                    "trade_type": "0",
                    "variety": lower,
                    "contract_id": f"{lower}{date[2:4]}08",
                    "data_type": "1",
                },
            ),
        ]
    return []


def main():
    parser = argparse.ArgumentParser(description="Probe exchange public endpoints for data-gap fields.")
    parser.add_argument("instruments", nargs="*", default=["FG", "JM", "AO"], help="Product names or codes.")
    parser.add_argument("--date", default=None, help="Date, YYYY-MM-DD or YYYYMMDD. Defaults to today.")
    parser.add_argument("--timeout", type=int, default=12, help="Per-request timeout seconds.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args()

    saved_proxy = {key: os.environ.get(key) for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy")}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"

    try:
        fetch = load_fetch_module()
        date = compact_date(args.date or fetch.today_shanghai())
        rows = []
        for instrument in args.instruments:
            normalized = fetch.normalize_instrument(instrument)
            for field, method, url, params, data in probes_for(normalized, date):
                result = request_probe(field, method, url, params=params, data=data, timeout=args.timeout)
                result.update(
                    {
                        "instrument": instrument,
                        "product_code": normalized.get("product_code"),
                        "exchange": normalized.get("exchange"),
                        "date": fetch.iso_date(date),
                    }
                )
                rows.append(result)
    finally:
        for key, value in saved_proxy.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    if args.json:
        print(json.dumps({"date": date, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print("| 品种 | 交易所 | 字段 | 状态 | 分类 | 说明 |")
        print("|---|---|---|---|---|---|")
        for row in rows:
            print(
                "| {product} | {exchange} | {field} | {status} | {category} | {detail} |".format(
                    product=row.get("product_code"),
                    exchange=row.get("exchange"),
                    field=row.get("name"),
                    status=row.get("status") or "",
                    category=row.get("category"),
                    detail=str(row.get("detail") or "").replace("|", "/")[:80],
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
