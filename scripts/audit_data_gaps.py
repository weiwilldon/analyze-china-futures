#!/usr/bin/env python3
"""Audit data-gap coverage for one or more China futures instruments."""

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT = ROOT / "scripts" / "fetch_china_futures_snapshot.py"


def load_fetch_module():
    spec = importlib.util.spec_from_file_location("fetch_china_futures_snapshot", FETCH_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_of(fundamentals, key):
    value = fundamentals.get(key)
    if not isinstance(value, dict):
        return None
    return value.get("source")


def compact_errors(snapshot):
    out = []
    for item in snapshot.get("supplement_errors") or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "field": item.get("field"),
                "source": item.get("source"),
                "category": item.get("category"),
                "message": item.get("message"),
            }
        )
    return out


def first_error(snapshot, field):
    for item in snapshot.get("supplement_errors") or []:
        if not isinstance(item, dict):
            continue
        if item.get("field") == field:
            return {
                "source": item.get("source"),
                "category": item.get("category"),
                "message": item.get("message"),
            }
    return None


def missing_required_fields(completeness):
    rows = completeness.get("fields") or []
    return [
        item.get("field")
        for item in rows
        if item.get("required", True) and not item.get("ok")
    ]


def resource_plan_for(snapshot, field):
    normalized = snapshot.get("normalized") or {}
    exchange = normalized.get("exchange") or "交易所"
    error = first_error(snapshot, field) or {}
    category = error.get("category")
    if field == "spot_basis":
        return {
            "field": field,
            "priority": [
                "AKShare futures_spot_price / futures_spot_price_daily",
                "SMM H5 spot pages for AO/CU/AL/ZN/PB/NI/SN/LC/SI",
                "100ppi daily page or manual-data basis file",
                "vendor export: Mysteel/SMM/Baiinfo/Lonzhong/Wind/Choice",
            ],
            "recommended_next": "导出产业现货/基差到 manual-data，或接入供应商 API；脚本不会编造基差。",
            "last_error": error,
        }
    if field == "warehouse_receipt":
        if category == "blocked_by_exchange_waf":
            next_step = "交易所公开入口被 WAF 拦截，优先配置 TUSHARE_TOKEN，或从交易所网页下载仓单日报放入 manual-data。"
        elif category == "no_data_for_date":
            next_step = "该交易日仓单文件尚无数据或不含该品种，先确认最新有效交易日，再用手工文件兜底。"
        else:
            next_step = "先重跑交易所探针；仍缺失时配置 TUSHARE_TOKEN 或导入交易所仓单日报。"
        return {
            "field": field,
            "priority": [
                "Tushare Pro fut_wsr when TUSHARE_TOKEN is configured",
                f"{exchange} official/public warehouse endpoint",
                "AKShare exchange warehouse functions",
                "AKShare futures_inventory_em aggregate inventory/warehouse fallback",
                "manual-data warehouse_receipt CSV/JSON/XLS/XLSX",
            ],
            "recommended_next": next_step,
            "last_error": error,
        }
    if field == "position_rank":
        if category == "blocked_by_exchange_waf":
            next_step = "交易所公开入口被 WAF 拦截，优先配置 TUSHARE_TOKEN，或手工下载成交持仓排名放入 manual-data。"
        elif category == "no_data_for_date":
            next_step = "该交易日席位文件尚无数据或不含该品种，先确认最新有效交易日，再用手工文件兜底。"
        else:
            next_step = "先重跑交易所探针；仍缺失时配置 TUSHARE_TOKEN 或导入交易所持仓排名。"
        return {
            "field": field,
            "priority": [
                "Tushare Pro fut_holding when TUSHARE_TOKEN is configured",
                f"{exchange} official/public member-position endpoint",
                "AKShare exchange ranking functions",
                "EastMoney qhhqzl futures dragon-and-tiger board",
                "manual-data position_rank CSV/JSON/XLS/XLSX",
            ],
            "recommended_next": next_step,
            "last_error": error,
        }
    if field == "news":
        return {
            "field": field,
            "priority": [
                "Jin10 MCP search_flash / search_news",
                "Jin10 MCP list_flash / list_news with cursor pagination",
                "Jin10 MCP get_news for article details",
            ],
            "recommended_next": "确认 JIN10_MCP_TOKEN 可用；诊断脚本会优先使用 structuredContent 和 MCP 分页字段。",
            "last_error": error,
        }
    return {
        "field": field,
        "priority": ["configured data sources", "manual-data fallback"],
        "recommended_next": "检查缺口明细里的 source/category，再补充对应数据。",
        "last_error": error,
    }


def audit_one(fetch_module, instrument, date, args):
    class FetchArgs:
        pass

    fetch_args = FetchArgs()
    fetch_args.instrument = instrument
    fetch_args.date = date
    fetch_args.out = None
    fetch_args.no_tqsdk = args.no_tqsdk
    fetch_args.no_tushare = args.no_tushare
    fetch_args.no_jin10 = args.no_jin10
    snapshot = fetch_module.build_snapshot(fetch_args)
    fundamentals = snapshot.get("fundamentals") or {}
    quote = snapshot.get("quote") or {}
    meta = snapshot.get("metadata") or {}
    completeness = snapshot.get("data_completeness") or {}
    missing_required = missing_required_fields(completeness)
    return {
        "instrument": instrument,
        "normalized": snapshot.get("normalized"),
        "analysis_date": meta.get("analysis_date"),
        "effective_market_date": meta.get("effective_market_date"),
        "data_completeness": completeness,
        "missing_required_fields": missing_required,
        "resource_plan": [resource_plan_for(snapshot, field) for field in missing_required],
        "quote": {
            "ok": quote.get("last") is not None,
            "source": quote.get("source"),
            "contract": quote.get("contract"),
        },
        "basis": {"ok": "spot_basis" in fundamentals, "source": source_of(fundamentals, "spot_basis")},
        "inventory": {"ok": "inventory" in fundamentals, "source": source_of(fundamentals, "inventory")},
        "warehouse_receipt": {
            "ok": "warehouse_receipt" in fundamentals,
            "source": source_of(fundamentals, "warehouse_receipt"),
        },
        "position_rank": {"ok": "position_rank" in fundamentals, "source": source_of(fundamentals, "position_rank")},
        "news": {"ok": bool(snapshot.get("news")), "count": len(snapshot.get("news") or [])},
        "macro_calendar": {"ok": bool(snapshot.get("macro_calendar")), "count": len(snapshot.get("macro_calendar") or [])},
        "missing_reasons": snapshot.get("missing_reasons") or [],
        "supplement_errors": compact_errors(snapshot),
        "warnings": snapshot.get("warnings") or [],
        "data_source_status": snapshot.get("data_source_status") or {},
    }


def markdown_table(rows):
    lines = [
        "| 品种 | 有效行情日 | 完整度 | 行情 | 基差 | 库存 | 仓单 | 席位 | 新闻 | 主要缺口 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        def mark(key):
            item = row.get(key) or {}
            if item.get("ok"):
                return "Y" + (f" ({item.get('source')})" if item.get("source") else "")
            return "N"

        missing = "; ".join(row.get("missing_reasons") or [])
        if len(missing) > 120:
            missing = missing[:117] + "..."
        completeness = row.get("data_completeness") or {}
        score = "{}/{}".format(completeness.get("required_ok", 0), completeness.get("required_total", 0))
        lines.append(
            "| {instrument} | {date} | {score} | {quote} | {basis} | {inventory} | {warehouse} | {position} | {news} | {missing} |".format(
                instrument=row.get("instrument"),
                date=row.get("effective_market_date") or "",
                score=score,
                quote=mark("quote"),
                basis=mark("basis"),
                inventory=mark("inventory"),
                warehouse=mark("warehouse_receipt"),
                position=mark("position_rank"),
                news="Y ({})".format((row.get("news") or {}).get("count")) if (row.get("news") or {}).get("ok") else "N",
                missing=missing,
            )
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Audit China futures data-gap coverage.")
    parser.add_argument("instruments", nargs="*", default=["FG", "JM", "AO"], help="Instrument names or product codes.")
    parser.add_argument("--date", default=None, help="Analysis date, YYYY-MM-DD. Defaults to Asia/Shanghai today.")
    parser.add_argument("--json", action="store_true", help="Print full JSON instead of a Markdown summary table.")
    parser.add_argument("--no-tqsdk", action="store_true", help="Skip TqSdk.")
    parser.add_argument("--no-tushare", action="store_true", help="Skip Tushare Pro.")
    parser.add_argument("--no-jin10", action="store_true", help="Skip Jin10 MCP.")
    parser.add_argument("--verbose", action="store_true", help="Show underlying data-source warnings/logs.")
    args = parser.parse_args()

    fetch_module = load_fetch_module()
    date = args.date or fetch_module.today_shanghai()
    if args.verbose:
        rows = [audit_one(fetch_module, instrument, date, args) for instrument in args.instruments]
    else:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
                rows = [audit_one(fetch_module, instrument, date, args) for instrument in args.instruments]
    if args.json:
        print(json.dumps({"date": date, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print(markdown_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
