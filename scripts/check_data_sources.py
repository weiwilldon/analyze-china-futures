#!/usr/bin/env python3
"""Check optional data-source readiness for analyze-china-futures.

The script never prints secrets. It reports whether packages and environment
variables are present, and can perform a lightweight Jin10 MCP handshake.
"""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


def has_module(name):
    return importlib.util.find_spec(name) is not None


def env_present(name):
    return bool(os.getenv(name))


def status(name, ok, detail=None):
    return {"name": name, "ok": bool(ok), "detail": detail or ("ok" if ok else "missing")}


def manual_data_detail():
    dirs = []
    raw = os.getenv("CHINA_FUTURES_MANUAL_DATA_DIR")
    if raw:
        dirs.extend(Path(item) for item in raw.split(os.pathsep) if item)
    skill_dir = Path(__file__).resolve().parents[1]
    dirs.extend([Path.cwd() / "manual-data", skill_dir / "manual-data"])
    existing = []
    seen = set()
    for directory in dirs:
        try:
            resolved = directory.expanduser().resolve()
        except Exception:
            resolved = directory
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            template_count = len(list((resolved / "templates").glob("*"))) if (resolved / "templates").exists() else 0
            data_count = len([p for p in resolved.rglob("*") if p.is_file() and "templates" not in p.parts and p.name.lower() != "readme.md"])
            existing.append(f"{resolved} (files={data_count}, templates={template_count})")
    if existing:
        return True, "existing: " + "; ".join(existing[:3])
    return False, "no manual-data directory found"


def try_jin10_ping():
    token = os.getenv("JIN10_MCP_TOKEN")
    if not token:
        return status("jin10_mcp_ping", False, "JIN10_MCP_TOKEN not set")
    skill_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from fetch_china_futures_snapshot import Jin10McpClient

        client = Jin10McpClient(token)
        client.initialize()
        result = client.call_rpc("tools/list", {})
        tools = [item.get("name") for item in ((result or {}).get("result") or {}).get("tools", [])]
        return status("jin10_mcp_ping", bool(tools), f"tools: {', '.join(tools[:8])}")
    except Exception as exc:
        return status("jin10_mcp_ping", False, str(exc))


def build_report(include_network=False):
    manual_ok, manual_detail = manual_data_detail()
    checks = [
        status("python", True, sys.version.split()[0]),
        status("akshare_module", has_module("akshare"), "importable" if has_module("akshare") else "not installed"),
        status("tqsdk_module", has_module("tqsdk"), "importable" if has_module("tqsdk") else "not installed"),
        status("tqsdk_env", env_present("TQSDK_USER") and env_present("TQSDK_PASSWORD"), "TQSDK_USER/TQSDK_PASSWORD present" if env_present("TQSDK_USER") and env_present("TQSDK_PASSWORD") else "missing TQSDK_USER or TQSDK_PASSWORD"),
        status("tushare_module", has_module("tushare"), "importable" if has_module("tushare") else "not installed"),
        status("tushare_env", env_present("TUSHARE_TOKEN"), "TUSHARE_TOKEN present" if env_present("TUSHARE_TOKEN") else "TUSHARE_TOKEN not set"),
        status("jin10_env", env_present("JIN10_MCP_TOKEN"), "JIN10_MCP_TOKEN present" if env_present("JIN10_MCP_TOKEN") else "JIN10_MCP_TOKEN not set"),
        status("bs4_module", has_module("bs4"), "importable" if has_module("bs4") else "not installed"),
        status("pandas_module", has_module("pandas"), "importable" if has_module("pandas") else "not installed"),
        status("excel_modules", has_module("openpyxl") and has_module("xlrd"), "openpyxl/xlrd importable" if has_module("openpyxl") and has_module("xlrd") else "missing openpyxl or xlrd"),
        status("manual_data_dir", manual_ok, manual_detail),
    ]
    if include_network:
        checks.append(try_jin10_ping())
    return {
        "summary": {
            "ready_core_public": has_module("akshare") and has_module("bs4"),
            "ready_tqsdk": has_module("tqsdk") and env_present("TQSDK_USER") and env_present("TQSDK_PASSWORD"),
            "ready_tushare": has_module("tushare") and env_present("TUSHARE_TOKEN"),
            "ready_jin10": env_present("JIN10_MCP_TOKEN"),
        },
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description="Check China futures data-source readiness.")
    parser.add_argument("--network", action="store_true", help="Also test Jin10 MCP tools/list handshake.")
    parser.add_argument("--pretty", action="store_true", help="Print human-readable lines instead of JSON.")
    args = parser.parse_args()
    report = build_report(include_network=args.network)
    if args.pretty:
        for item in report["checks"]:
            marker = "OK" if item["ok"] else "MISS"
            print(f"{marker} {item['name']}: {item['detail']}")
        print("summary:", json.dumps(report["summary"], ensure_ascii=False))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
