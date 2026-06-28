#!/usr/bin/env python3
"""Probe optional Tushare Pro futures warehouse and holding endpoints."""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT = ROOT / "scripts" / "fetch_china_futures_snapshot.py"


def load_fetch_module():
    spec = importlib.util.spec_from_file_location("fetch_china_futures_snapshot", FETCH_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact_date(fetch, value):
    text = str(value or fetch.today_shanghai())
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text.replace("-", "")
    if re.match(r"^\d{8}$", text):
        return text
    return fetch.today_shanghai().replace("-", "")


def classify_tushare_error(message):
    text = str(message or "")
    lowered = text.lower()
    if "token" in lowered or "权限" in text or "积分" in text or "permission" in lowered:
        return "auth_or_permission"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "network" in lowered or "connection" in lowered:
        return "network_failure"
    return "source_error"


def call_tushare(pro, method, trade_date, symbol):
    try:
        data = getattr(pro, method)(trade_date=trade_date, symbol=symbol)
    except Exception as exc:
        return {
            "ok": False,
            "rows": 0,
            "category": classify_tushare_error(exc),
            "detail": str(exc),
        }
    rows = 0
    try:
        rows = int(len(data))
    except Exception:
        rows = 0
    return {
        "ok": rows > 0,
        "rows": rows,
        "category": "reachable" if rows > 0 else "no_rows_returned",
        "detail": f"{rows} rows",
    }


def main():
    parser = argparse.ArgumentParser(description="Probe Tushare Pro futures warehouse and holding endpoints.")
    parser.add_argument("instruments", nargs="*", default=["FG", "JM", "AO"], help="Product names or codes.")
    parser.add_argument("--date", default=None, help="Date, YYYY-MM-DD or YYYYMMDD. Defaults to today.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args()

    fetch = load_fetch_module()
    trade_date = compact_date(fetch, args.date)
    token = os.getenv("TUSHARE_TOKEN")
    rows = []
    if not token:
        for instrument in args.instruments:
            normalized = fetch.normalize_instrument(instrument)
            for method, field in (("fut_wsr", "warehouse_receipt"), ("fut_holding", "position_rank")):
                rows.append(
                    {
                        "instrument": instrument,
                        "product_code": normalized.get("product_code"),
                        "exchange": normalized.get("exchange"),
                        "date": fetch.iso_date(trade_date),
                        "field": field,
                        "method": method,
                        "ok": False,
                        "rows": 0,
                        "category": "missing_token",
                        "detail": "TUSHARE_TOKEN not set",
                    }
                )
    else:
        try:
            import tushare as ts

            pro = ts.pro_api(token)
        except Exception as exc:
            pro = None
            import_error = str(exc)
        else:
            import_error = None
        for instrument in args.instruments:
            normalized = fetch.normalize_instrument(instrument)
            symbol = normalized.get("product_code")
            for method, field in (("fut_wsr", "warehouse_receipt"), ("fut_holding", "position_rank")):
                if pro is None:
                    result = {
                        "ok": False,
                        "rows": 0,
                        "category": "source_error",
                        "detail": import_error or "tushare unavailable",
                    }
                else:
                    result = call_tushare(pro, method, trade_date, symbol)
                result.update(
                    {
                        "instrument": instrument,
                        "product_code": symbol,
                        "exchange": normalized.get("exchange"),
                        "date": fetch.iso_date(trade_date),
                        "field": field,
                        "method": method,
                    }
                )
                rows.append(result)

    if args.json:
        print(json.dumps({"date": trade_date, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print("| 品种 | 交易所 | 字段 | Tushare 方法 | 可用 | 行数 | 分类 | 说明 |")
        print("|---|---|---|---|---|---|---|---|")
        for row in rows:
            print(
                "| {product} | {exchange} | {field} | {method} | {ok} | {rows} | {category} | {detail} |".format(
                    product=row.get("product_code"),
                    exchange=row.get("exchange"),
                    field=row.get("field"),
                    method=row.get("method"),
                    ok="Y" if row.get("ok") else "N",
                    rows=row.get("rows"),
                    category=row.get("category"),
                    detail=str(row.get("detail") or "").replace("|", "/")[:80],
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
