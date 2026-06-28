#!/usr/bin/env python3
"""Probe Jin10 MCP news, flash, and calendar tools for selected futures products."""

import argparse
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


def count_items(structured):
    data = (structured or {}).get("data")
    if isinstance(data, dict):
        items = data.get("items") or []
        return len(items), data.get("has_more"), data.get("next_cursor")
    if isinstance(data, list):
        return len(data), None, None
    return 0, None, None


def safe_tool(client, name, arguments):
    try:
        structured = client.tool(name, arguments)
        count, has_more, next_cursor = count_items(structured)
        return {
            "ok": True,
            "count": count,
            "has_more": has_more,
            "next_cursor_present": bool(next_cursor),
            "category": "reachable",
            "detail": f"{count} items",
        }
    except Exception as exc:
        return {
            "ok": False,
            "count": 0,
            "has_more": None,
            "next_cursor_present": False,
            "category": "source_error",
            "detail": str(exc),
        }


def safe_list_method(client, name, method_name, key):
    try:
        payload = getattr(client, method_name)()
        items = payload.get(key) or []
        return {
            "instrument": "*",
            "product_code": "*",
            "tool": name,
            "keyword": "",
            "ok": True,
            "count": len(items),
            "has_more": payload.get("has_more"),
            "next_cursor_present": bool(payload.get("next_cursor")),
            "category": "reachable",
            "detail": f"{len(items)} items",
        }
    except Exception as exc:
        return {
            "instrument": "*",
            "product_code": "*",
            "tool": name,
            "keyword": "",
            "ok": False,
            "count": 0,
            "has_more": None,
            "next_cursor_present": False,
            "category": "source_error",
            "detail": str(exc),
        }


def main():
    parser = argparse.ArgumentParser(description="Probe Jin10 MCP news/flash/calendar tools.")
    parser.add_argument("instruments", nargs="*", default=["FG", "JM", "AO"], help="Product names or codes.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--full", action="store_true", help="Probe list_news and list_calendar too; default stays fast for daily diagnostics.")
    args = parser.parse_args()

    fetch = load_fetch_module()
    token = os.getenv("JIN10_MCP_TOKEN")
    rows = []
    if not token:
        for instrument in args.instruments:
            normalized = fetch.normalize_instrument(instrument)
            rows.append(
                {
                    "instrument": instrument,
                    "product_code": normalized.get("product_code"),
                    "tool": "jin10_mcp",
                    "keyword": "",
                    "ok": False,
                    "count": 0,
                    "category": "missing_token",
                    "detail": "JIN10_MCP_TOKEN not set",
                }
            )
    else:
        try:
            client = fetch.Jin10McpClient(token, timeout=int(os.getenv("JIN10_MCP_PROBE_TIMEOUT_SECONDS") or 8), retries=2)
            client.initialize()
        except Exception as exc:
            client = None
            init_error = str(exc)
        else:
            init_error = None
        if client is None:
            rows.append(
                {
                    "instrument": "",
                    "product_code": "",
                    "tool": "initialize",
                    "keyword": "",
                    "ok": False,
                    "count": 0,
                    "category": "source_error",
                    "detail": init_error,
                }
            )
        else:
            rows.append(safe_list_method(client, "tools/list", "list_tools", "tools"))
            rows.append(safe_list_method(client, "resources/list", "list_resources", "resources"))
            for instrument in args.instruments:
                normalized = fetch.normalize_instrument(instrument)
                keywords = fetch.jin10_keywords_for(normalized)
                for keyword in keywords[:1]:
                    for tool_name in ("search_flash", "search_news"):
                        result = safe_tool(client, tool_name, {"keyword": keyword})
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
            if args.full:
                list_tools.extend([("list_news", {}), ("list_calendar", {})])
            for tool_name, tool_args in list_tools:
                result = safe_tool(client, tool_name, tool_args)
                result.update(
                    {
                        "instrument": "*",
                        "product_code": "*",
                        "tool": tool_name,
                        "keyword": "",
                    }
                )
                rows.append(result)

    if args.json:
        print(json.dumps({"rows": rows}, ensure_ascii=False, indent=2))
    else:
        print("| 品种 | 工具 | 关键词 | 可用 | 条数 | has_more | 分类 | 说明 |")
        print("|---|---|---|---|---|---|---|---|")
        for row in rows:
            print(
                "| {product} | {tool} | {keyword} | {ok} | {count} | {has_more} | {category} | {detail} |".format(
                    product=row.get("product_code") or row.get("instrument"),
                    tool=row.get("tool"),
                    keyword=row.get("keyword") or "",
                    ok="Y" if row.get("ok") else "N",
                    count=row.get("count"),
                    has_more="" if row.get("has_more") is None else row.get("has_more"),
                    category=row.get("category"),
                    detail=str(row.get("detail") or "").replace("|", "/")[:100],
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
