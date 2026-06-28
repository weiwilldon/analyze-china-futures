#!/usr/bin/env python3
"""Audit completion status for the data-gap remediation goal."""

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

CORE_FIELDS = ("spot_basis", "warehouse_receipt", "position_rank", "news")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Args:
    pass


def run_audit(instruments, date, include_jin10):
    audit = load_module("audit_data_gaps", SCRIPTS / "audit_data_gaps.py")
    fetch = audit.load_fetch_module()
    args = Args()
    args.no_tqsdk = False
    args.no_tushare = False
    args.no_jin10 = not include_jin10
    date = date or fetch.today_shanghai()
    rows = []
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            for instrument in instruments:
                rows.append(audit.audit_one(fetch, instrument, date, args))
    return date, rows


def run_jin10_probe(instruments, full=False):
    diagnose = load_module("diagnose_data_readiness", SCRIPTS / "diagnose_data_readiness.py")
    return diagnose.run_jin10_probe(instruments, full=full)


def apply_jin10(audit_rows, jin10_rows):
    diagnose = load_module("diagnose_data_readiness", SCRIPTS / "diagnose_data_readiness.py")
    diagnose.apply_jin10_probe_to_audit(audit_rows, jin10_rows)


def run_manual_requests(instruments, date):
    prepare = load_module("prepare_manual_data_requests", SCRIPTS / "prepare_manual_data_requests.py")
    return prepare.build_requests(instruments, date).get("requests") or []


def field_status(row, field):
    if field == "spot_basis":
        return row.get("basis") or {}
    return row.get(field) or {}


def first_resource_plan(row, field):
    for item in row.get("resource_plan") or []:
        if item.get("field") == field:
            return item
    return {}


def manual_request_index(requests):
    index = {}
    for item in requests:
        key = ((item.get("product_code") or "").upper(), item.get("field"))
        index.setdefault(key, item)
    return index


def classify_missing(row, field, request):
    plan = first_resource_plan(row, field)
    last_error = plan.get("last_error") or {}
    category = last_error.get("category")
    if field == "news":
        return "jin10_token_or_probe_required"
    if field == "spot_basis":
        return "vendor_or_manual_basis_required"
    if category == "blocked_by_exchange_waf":
        return "tushare_or_manual_required"
    if category == "no_data_for_date":
        return "date_availability_or_manual_required"
    if request:
        return "manual_or_optional_source_required"
    return category or "missing"


def build_report(instruments, date, include_jin10, jin10_full):
    date, audit_rows = run_audit(instruments, date, include_jin10=False)
    jin10_rows = run_jin10_probe(instruments, full=jin10_full) if include_jin10 else []
    if jin10_rows:
        apply_jin10(audit_rows, jin10_rows)
    requests = run_manual_requests(instruments, date)
    request_by_key = manual_request_index(requests)
    field_rows = []
    for row in audit_rows:
        normalized = row.get("normalized") or {}
        product = (normalized.get("product_code") or row.get("instrument") or "").upper()
        for field in CORE_FIELDS:
            status = field_status(row, field)
            request = request_by_key.get((product, field))
            ok = bool(status.get("ok"))
            plan = first_resource_plan(row, field)
            field_rows.append(
                {
                    "instrument": row.get("instrument"),
                    "product_code": product,
                    "exchange": normalized.get("exchange"),
                    "field": field,
                    "ok": ok,
                    "source": status.get("source"),
                    "status": "auto_filled" if ok else classify_missing(row, field, request),
                    "effective_market_date": row.get("effective_market_date"),
                    "recommended_next": "" if ok else plan.get("recommended_next") or (request or {}).get("source_hint") or "",
                    "manual_file": "" if ok else (request or {}).get("suggested_file") or "",
                    "source_hints": [] if ok else (request or {}).get("source_hints") or [],
                    "last_error": {} if ok else plan.get("last_error") or {},
                }
            )
    totals = {}
    for field in CORE_FIELDS:
        rows = [item for item in field_rows if item["field"] == field]
        ok_count = sum(1 for item in rows if item["ok"])
        totals[field] = {
            "ok": ok_count,
            "total": len(rows),
            "ratio": round(ok_count / len(rows), 4) if rows else None,
        }
    unresolved = [item for item in field_rows if not item["ok"]]
    source_checks = load_module("check_data_sources", SCRIPTS / "check_data_sources.py").build_report(include_network=False)
    return {
        "date": date,
        "instruments": instruments,
        "source_summary": source_checks.get("summary") or {},
        "field_totals": totals,
        "fields": field_rows,
        "unresolved_count": len(unresolved),
        "manual_requests": requests,
        "jin10_probe": jin10_rows,
        "completion_status": "complete" if not unresolved else "partial",
    }


def cell(value, limit=140):
    text = str(value or "").replace("|", "/").replace("\n", " ")
    return text[:limit]


def mark(value):
    return "Y" if value else "N"


def render_markdown(report):
    lines = ["# 数据缺口补齐完成度审计", ""]
    lines.append(f"- 日期：{report['date']}")
    lines.append(f"- 品种：{', '.join(report['instruments'])}")
    lines.append(f"- 状态：{report['completion_status']}")
    lines.append("")
    lines.append("## 四类核心缺口覆盖率")
    lines.append("")
    lines.append("| 字段 | 自动可用 | 总数 | 覆盖率 |")
    lines.append("|---|---|---|---|")
    for field in CORE_FIELDS:
        item = report["field_totals"][field]
        ratio = "" if item["ratio"] is None else "{:.0%}".format(item["ratio"])
        lines.append(f"| {field} | {item['ok']} | {item['total']} | {ratio} |")
    lines.append("")
    lines.append("## 逐品种状态")
    lines.append("")
    lines.append("| 品种 | 交易所 | 字段 | 可用 | 来源/状态 | 有效行情日 | 建议动作 | 手工文件 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in report["fields"]:
        source_or_status = row.get("source") if row.get("ok") else row.get("status")
        lines.append(
            "| {product} | {exchange} | {field} | {ok} | {source} | {date} | {next} | {file} |".format(
                product=cell(row.get("product_code")),
                exchange=cell(row.get("exchange")),
                field=cell(row.get("field")),
                ok=mark(row.get("ok")),
                source=cell(source_or_status),
                date=cell(row.get("effective_market_date")),
                next=cell(row.get("recommended_next"), 180),
                file=cell(row.get("manual_file"), 120),
            )
        )
    lines.append("")
    if report["unresolved_count"]:
        lines.append("## 仍需外部动作")
        lines.append("")
        if not report["source_summary"].get("ready_tushare"):
            lines.append("- `TUSHARE_TOKEN` 未配置；仓单/席位在公开入口被拦截或日期无文件时，Tushare Pro 仍是最稳的现成账号源。")
        lines.append("- 对仍缺的仓单、席位或基差，可按上表文件名把交易所/供应商导出放入 `manual-data/`。")
        lines.append("- 新闻流已由 Jin10 MCP 覆盖时，报告仍应按品种相关性过滤，不把无关快讯当作基本面。")
    else:
        lines.append("## 结论")
        lines.append("")
        lines.append("四类核心缺口在本次审计品种中均已自动补齐；仍建议保留缺失字段保护，不把未来源失败写成 0。")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Audit completion status for data-gap remediation.")
    parser.add_argument("instruments", nargs="*", default=["FG", "JM", "AO", "LC", "SI"], help="Product names or codes.")
    parser.add_argument("--date", default=None, help="Analysis date, YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--no-jin10", action="store_true", help="Skip Jin10 probe.")
    parser.add_argument("--with-jin10-full", action="store_true", help="Probe Jin10 list_news/list_calendar too.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    report = build_report(args.instruments, args.date, include_jin10=not args.no_jin10, jin10_full=args.with_jin10_full)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
