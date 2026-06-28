#!/usr/bin/env python3
"""Generate a consolidated data-readiness diagnosis for China futures analysis."""

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def quiet_call(fn, *args, quiet=True, **kwargs):
    if not quiet:
        return fn(*args, **kwargs)
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            return fn(*args, **kwargs)


class Args:
    pass


def run_audit(instruments, date, include_jin10, quiet):
    audit = load_module("audit_data_gaps", SCRIPTS / "audit_data_gaps.py")
    fetch = audit.load_fetch_module()
    args = Args()
    args.no_tqsdk = False
    args.no_tushare = False
    args.no_jin10 = not include_jin10
    date = date or fetch.today_shanghai()
    return [
        quiet_call(audit.audit_one, fetch, instrument, date, args, quiet=quiet)
        for instrument in instruments
    ]


def run_exchange_probe(instruments, date):
    probe = load_module("probe_exchange_sources", SCRIPTS / "probe_exchange_sources.py")
    fetch = probe.load_fetch_module()
    compact = probe.compact_date(date or fetch.today_shanghai())
    rows = []
    saved_proxy = {key: os.environ.get(key) for key in probe.os.environ.keys() if key.lower().endswith("proxy")}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    try:
        for instrument in instruments:
            normalized = fetch.normalize_instrument(instrument)
            for field, method, url, params, data in probe.probes_for(normalized, compact):
                result = probe.request_probe(field, method, url, params=params, data=data, timeout=8)
                result.update(
                    {
                        "instrument": instrument,
                        "product_code": normalized.get("product_code"),
                        "exchange": normalized.get("exchange"),
                        "date": fetch.iso_date(compact),
                    }
                )
                rows.append(result)
    finally:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy"):
            value = saved_proxy.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return rows


def run_tushare_probe(instruments, date):
    probe = load_module("probe_tushare_sources", SCRIPTS / "probe_tushare_sources.py")
    fetch = probe.load_fetch_module()
    compact = probe.compact_date(fetch, date)
    token = os.getenv("TUSHARE_TOKEN")
    rows = []
    if token:
        try:
            import tushare as ts

            pro = ts.pro_api(token)
            import_error = None
        except Exception as exc:
            pro = None
            import_error = str(exc)
    else:
        pro = None
        import_error = "TUSHARE_TOKEN not set"
    for instrument in instruments:
        normalized = fetch.normalize_instrument(instrument)
        symbol = normalized.get("product_code")
        for method, field in (("fut_wsr", "warehouse_receipt"), ("fut_holding", "position_rank")):
            if not token:
                result = {"ok": False, "rows": 0, "category": "missing_token", "detail": import_error}
            elif pro is None:
                result = {"ok": False, "rows": 0, "category": "source_error", "detail": import_error}
            else:
                result = probe.call_tushare(pro, method, compact, symbol)
            result.update(
                {
                    "instrument": instrument,
                    "product_code": symbol,
                    "exchange": normalized.get("exchange"),
                    "date": fetch.iso_date(compact),
                    "field": field,
                    "method": method,
                }
            )
            rows.append(result)
    return rows


def run_jin10_probe(instruments, full=False):
    probe = load_module("probe_jin10_sources", SCRIPTS / "probe_jin10_sources.py")
    fetch = probe.load_fetch_module()
    token = os.getenv("JIN10_MCP_TOKEN")
    rows = []
    if not token:
        return [
            {
                "instrument": instrument,
                "product_code": fetch.normalize_instrument(instrument).get("product_code"),
                "tool": "jin10_mcp",
                "keyword": "",
                "ok": False,
                "count": 0,
                "has_more": None,
                "category": "missing_token",
                "detail": "JIN10_MCP_TOKEN not set",
            }
            for instrument in instruments
        ]
    try:
        client = fetch.Jin10McpClient(token, timeout=int(os.getenv("JIN10_MCP_PROBE_TIMEOUT_SECONDS") or 8), retries=2)
        client.initialize()
    except Exception as exc:
        return [
            {
                "instrument": "",
                "product_code": "",
                "tool": "initialize",
                "keyword": "",
                "ok": False,
                "count": 0,
                "has_more": None,
                "category": "source_error",
                "detail": str(exc),
            }
        ]
    rows.append(probe.safe_list_method(client, "tools/list", "list_tools", "tools"))
    rows.append(probe.safe_list_method(client, "resources/list", "list_resources", "resources"))
    for instrument in instruments:
        normalized = fetch.normalize_instrument(instrument)
        for keyword in fetch.jin10_keywords_for(normalized)[:1]:
            for tool_name in ("search_flash", "search_news"):
                result = probe.safe_tool(client, tool_name, {"keyword": keyword})
                result.update(
                    {
                        "instrument": instrument,
                        "product_code": normalized.get("product_code"),
                        "tool": tool_name,
                        "keyword": keyword,
                    }
                )
                rows.append(result)
    list_tools = [("list_flash", {})]
    if full:
        list_tools.extend([("list_news", {}), ("list_calendar", {})])
    for tool_name, tool_args in list_tools:
        result = probe.safe_tool(client, tool_name, tool_args)
        result.update({"instrument": "*", "product_code": "*", "tool": tool_name, "keyword": ""})
        rows.append(result)
    return rows


def run_manual_requests(instruments, date):
    prepare = load_module("prepare_manual_data_requests", SCRIPTS / "prepare_manual_data_requests.py")
    return prepare.build_requests(instruments, date).get("requests") or []


def apply_jin10_probe_to_audit(audit_rows, jin10_rows):
    by_product = {}
    latest_ok = any(row.get("tool") == "list_flash" and row.get("ok") and row.get("count", 0) > 0 for row in jin10_rows)
    for row in jin10_rows:
        product = row.get("product_code")
        if not product or product == "*":
            continue
        if row.get("ok") and row.get("count", 0) > 0:
            by_product[product] = by_product.get(product, 0) + int(row.get("count") or 0)
    for row in audit_rows:
        product = ((row.get("normalized") or {}).get("product_code") or "").upper()
        count = by_product.get(product, 0)
        if count or latest_ok:
            row["news"] = {"ok": True, "count": count, "source": "Jin10 MCP probe"}
            row["missing_reasons"] = [
                item for item in (row.get("missing_reasons") or [])
                if not str(item).startswith("news:")
            ]
            completeness = row.get("data_completeness") or {}
            fields = completeness.get("fields") or []
            for field_row in fields:
                if field_row.get("field") == "news":
                    field_row["ok"] = True
                    field_row["source"] = "Jin10 MCP probe"
                    field_row.pop("category", None)
                    field_row.pop("message", None)
            required_rows = [item for item in fields if item.get("required", True)]
            completeness["required_total"] = len(required_rows)
            completeness["required_ok"] = sum(1 for item in required_rows if item.get("ok"))
            if completeness["required_total"]:
                completeness["required_ratio"] = round(completeness["required_ok"] / completeness["required_total"], 4)
            row["missing_required_fields"] = [
                item.get("field")
                for item in required_rows
                if not item.get("ok")
            ]
            row["resource_plan"] = [
                item
                for item in (row.get("resource_plan") or [])
                if item.get("field") != "news"
            ]


def mark(value):
    return "Y" if value else "N"


def cell(value, limit=120):
    text = str(value or "").replace("|", "/").replace("\n", " ")
    return text[:limit]


def first_source_hint(row):
    hints = row.get("source_hints") or []
    if not hints:
        return row.get("source_hint") or ""
    hint = hints[0]
    name = hint.get("name") or ""
    url = hint.get("url") or ""
    method = hint.get("method")
    method_text = f" ({method})" if method else ""
    return f"{name}{method_text}: {url}" if url else name


def render_markdown(report):
    lines = []
    lines.append("# 中国期货数据源诊断")
    lines.append("")
    lines.append(f"- 日期：{report['date']}")
    lines.append(f"- 品种：{', '.join(report['instruments'])}")
    lines.append("")
    lines.append("## 配置状态")
    summary = report["source_checks"]["summary"]
    lines.append("")
    lines.append("| 项目 | 状态 |")
    lines.append("|---|---|")
    for key in ("ready_core_public", "ready_tqsdk", "ready_tushare", "ready_jin10"):
        lines.append(f"| {key} | {mark(summary.get(key))} |")
    lines.append("")
    lines.append("## 数据覆盖")
    lines.append("")
    lines.append("| 品种 | 有效行情日 | 完整度 | 行情 | 基差 | 库存 | 仓单 | 席位 | 新闻 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in report["audit"]:
        completeness = row.get("data_completeness") or {}
        score = "{}/{}".format(completeness.get("required_ok", 0), completeness.get("required_total", 0))
        lines.append(
            "| {instrument} | {date} | {score} | {quote} | {basis} | {inventory} | {warehouse} | {position} | {news} |".format(
                instrument=row.get("instrument"),
                date=row.get("effective_market_date") or "",
                score=score,
                quote=mark((row.get("quote") or {}).get("ok")),
                basis=mark((row.get("basis") or {}).get("ok")),
                inventory=mark((row.get("inventory") or {}).get("ok")),
                warehouse=mark((row.get("warehouse_receipt") or {}).get("ok")),
                position=mark((row.get("position_rank") or {}).get("ok")),
                news=mark((row.get("news") or {}).get("ok")),
            )
        )
    lines.append("")
    issue_rows = []
    for row in report["audit"]:
        instrument = row.get("instrument")
        for item in row.get("supplement_errors") or []:
            issue_rows.append(
                {
                    "instrument": instrument,
                    "field": item.get("field"),
                    "source": item.get("source"),
                    "category": item.get("category"),
                    "message": item.get("message"),
                }
            )
        for reason in row.get("missing_reasons") or []:
            issue_rows.append(
                {
                    "instrument": instrument,
                    "field": str(reason).split(":", 1)[0],
                    "source": "snapshot",
                    "category": "missing",
                    "message": reason,
                }
            )
    if issue_rows:
        lines.append("## 缺口明细")
        lines.append("")
        lines.append("| 品种 | 字段 | 来源 | 分类 | 说明 |")
        lines.append("|---|---|---|---|---|")
        for row in issue_rows:
            lines.append(
                "| {instrument} | {field} | {source} | {category} | {message} |".format(
                    instrument=cell(row.get("instrument")),
                    field=cell(row.get("field"), 60),
                    source=cell(row.get("source"), 80),
                    category=cell(row.get("category"), 40),
                    message=cell(row.get("message"), 160),
                )
            )
        lines.append("")
    plan_rows = []
    for row in report["audit"]:
        for item in row.get("resource_plan") or []:
            plan_rows.append(
                {
                    "instrument": row.get("instrument"),
                    "field": item.get("field"),
                    "recommended_next": item.get("recommended_next"),
                    "priority": "；".join(item.get("priority") or []),
                    "last_error": item.get("last_error") or {},
                }
            )
    if plan_rows:
        lines.append("## 现成资源补齐建议")
        lines.append("")
        lines.append("| 品种 | 字段 | 优先资源 | 建议动作 | 最近错误 |")
        lines.append("|---|---|---|---|---|")
        for row in plan_rows:
            last_error = row.get("last_error") or {}
            error_text = " / ".join(
                str(value)
                for value in (last_error.get("source"), last_error.get("category"), last_error.get("message"))
                if value
            )
            lines.append(
                "| {instrument} | {field} | {priority} | {next} | {error} |".format(
                    instrument=cell(row.get("instrument")),
                    field=cell(row.get("field"), 60),
                    priority=cell(row.get("priority"), 220),
                    next=cell(row.get("recommended_next"), 180),
                    error=cell(error_text, 180),
                )
            )
        lines.append("")
    lines.append("## 交易所公开入口")
    lines.append("")
    lines.append("| 品种 | 交易所 | 字段 | 分类 | 说明 |")
    lines.append("|---|---|---|---|---|")
    for row in report["exchange_probe"]:
        lines.append(
            "| {product} | {exchange} | {field} | {category} | {detail} |".format(
                product=row.get("product_code"),
                exchange=row.get("exchange"),
                field=row.get("name"),
                category=row.get("category"),
                detail=str(row.get("detail") or "").replace("|", "/")[:80],
            )
        )
    lines.append("")
    lines.append("## Tushare Pro")
    lines.append("")
    lines.append("| 品种 | 字段 | 方法 | 可用 | 分类 |")
    lines.append("|---|---|---|---|---|")
    for row in report["tushare_probe"]:
        lines.append(
            "| {product} | {field} | {method} | {ok} | {category} |".format(
                product=row.get("product_code"),
                field=row.get("field"),
                method=row.get("method"),
                ok=mark(row.get("ok")),
                category=row.get("category"),
            )
        )
    lines.append("")
    if report.get("jin10_probe"):
        lines.append("## 金十 MCP")
        lines.append("")
        lines.append("| 品种 | 工具 | 关键词 | 可用 | 条数 | 分类 |")
        lines.append("|---|---|---|---|---|---|")
        for row in report["jin10_probe"]:
            lines.append(
                "| {product} | {tool} | {keyword} | {ok} | {count} | {category} |".format(
                    product=cell(row.get("product_code") or row.get("instrument")),
                    tool=cell(row.get("tool")),
                    keyword=cell(row.get("keyword")),
                    ok=mark(row.get("ok")),
                    count=row.get("count"),
                    category=cell(row.get("category")),
                )
            )
        lines.append("")
    if report.get("manual_requests"):
        lines.append("## 手动数据补充清单")
        lines.append("")
        lines.append("| 品种 | 字段 | 建议文件 | 首选入口 | 模板 | 关键列 |")
        lines.append("|---|---|---|---|---|---|")
        for row in report["manual_requests"]:
            lines.append(
                "| {product} | {field} | {file} | {source} | {template} | {columns} |".format(
                    product=cell(row.get("product_code")),
                    field=cell(row.get("field")),
                    file=cell(row.get("suggested_file"), 120),
                    source=cell(first_source_hint(row), 180),
                    template=cell(row.get("template"), 120),
                    columns=cell(row.get("required_columns"), 160),
                )
            )
        lines.append("")
    lines.append("## 下一步")
    actions = []
    if not summary.get("ready_tushare"):
        actions.append("配置 `TUSHARE_TOKEN` 后重新运行 Tushare 探针，以验证仓单和席位持仓补齐。")
    if any(row.get("category") == "blocked_by_exchange_waf" for row in report["exchange_probe"]):
        actions.append("交易所公开入口出现 WAF 拦截时，优先使用 Tushare Pro 或手动下载文件放入 `manual-data/`。")
    if any(not (row.get("basis") or {}).get("ok") for row in report["audit"]):
        actions.append("基差缺口品种需要接入产业数据库导出，或放入 `manual-data/*basis*` 文件。")
    if not actions:
        actions.append("主要数据源已就绪，可直接生成日报；报告仍需保留风险提示。")
    for item in actions:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Diagnose data readiness for China futures analysis.")
    parser.add_argument("instruments", nargs="*", default=["FG", "JM", "AO"], help="Product names or codes.")
    parser.add_argument("--date", default=None, help="Analysis date, YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--with-jin10", action="store_true", help="Include Jin10 news in audit. Kept for compatibility; Jin10 is used by default when configured.")
    parser.add_argument("--with-jin10-full", action="store_true", help="Probe Jin10 list_news and list_calendar in addition to the fast default checks.")
    parser.add_argument("--no-jin10", action="store_true", help="Skip Jin10 MCP probes for a faster/offline diagnosis.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args()

    check = load_module("check_data_sources", SCRIPTS / "check_data_sources.py")
    fetch = load_module("fetch_china_futures_snapshot", SCRIPTS / "fetch_china_futures_snapshot.py")
    date = args.date or fetch.today_shanghai()
    include_jin10 = not args.no_jin10 and bool(os.getenv("JIN10_MCP_TOKEN"))
    probe_jin10 = include_jin10
    audit_rows = run_audit(args.instruments, date, include_jin10=False, quiet=True)
    jin10_rows = run_jin10_probe(args.instruments, full=args.with_jin10_full) if probe_jin10 else []
    if jin10_rows:
        apply_jin10_probe_to_audit(audit_rows, jin10_rows)
    report = {
        "date": date,
        "instruments": args.instruments,
        "source_checks": check.build_report(include_network=probe_jin10),
        "audit": audit_rows,
        "exchange_probe": run_exchange_probe(args.instruments, date),
        "tushare_probe": run_tushare_probe(args.instruments, date),
        "jin10_probe": jin10_rows,
        "manual_requests": run_manual_requests(args.instruments, date),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
