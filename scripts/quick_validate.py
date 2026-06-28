#!/usr/bin/env python3
"""Quick validation for the analyze-china-futures skill."""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(cmd, timeout=120):
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return {
        "cmd": " ".join(str(part) for part in cmd),
        "returncode": proc.returncode,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
    }


def manual_supplement_check():
    spec = importlib.util.spec_from_file_location("fetch_snapshot", SCRIPTS / "fetch_china_futures_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        (data_dir / "20260626_AO_warehouse_receipt.json").write_text(
            json.dumps({"rows": [{"var": "AO", "date": "2026-06-26", "warehouse": "sample", "receipt": 123}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (data_dir / "20260626_AO_position_rank.json").write_text(
            json.dumps({"rows": [{"var": "AO", "rank": 1, "vol": 1000, "long_open_interest": 600, "short_open_interest": 550}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        old = os.environ.get("CHINA_FUTURES_MANUAL_DATA_DIR")
        os.environ["CHINA_FUTURES_MANUAL_DATA_DIR"] = str(data_dir)
        try:
            snapshot = {"metadata": {"analysis_date": "2026-06-26"}, "fundamentals": {}, "data_source_status": {}}
            normalized = {"product_code": "AO", "ak_symbol": "AO", "input": "氧化铝"}
            module.fetch_manual_supplements(snapshot, normalized)
        finally:
            if old is None:
                os.environ.pop("CHINA_FUTURES_MANUAL_DATA_DIR", None)
            else:
                os.environ["CHINA_FUTURES_MANUAL_DATA_DIR"] = old
    fundamentals = snapshot.get("fundamentals") or {}
    ok = "warehouse_receipt" in fundamentals and "position_rank" in fundamentals
    return {
        "cmd": "manual_supplement_check",
        "returncode": 0 if ok else 1,
        "stdout": json.dumps(
            {
                "fundamental_keys": sorted(fundamentals.keys()),
                "manual_status": (snapshot.get("data_source_status") or {}).get("manual_supplements"),
            },
            ensure_ascii=False,
        ),
        "stderr": "" if ok else "manual supplements did not fill warehouse_receipt and position_rank",
    }


def manual_effective_date_check():
    spec = importlib.util.spec_from_file_location("fetch_snapshot", SCRIPTS / "fetch_china_futures_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        (data_dir / "20260626_FG_warehouse_receipt.csv").write_text(
            "date,product,warehouse,receipt,change\n2026-06-26,FG,sample,321,0\n",
            encoding="utf-8",
        )
        (data_dir / "20260626_FG_position_rank.csv").write_text(
            "date,product,rank,vol,long_open_interest,short_open_interest\n2026-06-26,FG,1,1000,700,650\n",
            encoding="utf-8",
        )
        old = os.environ.get("CHINA_FUTURES_MANUAL_DATA_DIR")
        os.environ["CHINA_FUTURES_MANUAL_DATA_DIR"] = str(data_dir)
        try:
            snapshot = {
                "metadata": {
                    "analysis_date": "2026-06-28",
                    "effective_market_date": "2026-06-26",
                },
                "fundamentals": {},
                "data_source_status": {},
            }
            normalized = {"product_code": "FG", "ak_symbol": "FG", "input": "玻璃"}
            module.fetch_manual_supplements(snapshot, normalized)
        finally:
            if old is None:
                os.environ.pop("CHINA_FUTURES_MANUAL_DATA_DIR", None)
            else:
                os.environ["CHINA_FUTURES_MANUAL_DATA_DIR"] = old
    fundamentals = snapshot.get("fundamentals") or {}
    ok = "warehouse_receipt" in fundamentals and "position_rank" in fundamentals
    return {
        "cmd": "manual_effective_date_check",
        "returncode": 0 if ok else 1,
        "stdout": json.dumps(
            {
                "analysis_date": snapshot["metadata"]["analysis_date"],
                "effective_market_date": snapshot["metadata"]["effective_market_date"],
                "fundamental_keys": sorted(fundamentals.keys()),
                "manual_status": (snapshot.get("data_source_status") or {}).get("manual_supplements"),
            },
            ensure_ascii=False,
        ),
        "stderr": "" if ok else "manual files named by effective_market_date were not loaded",
    }


def manual_request_source_hint_check():
    spec = importlib.util.spec_from_file_location("prepare_manual_data_requests", SCRIPTS / "prepare_manual_data_requests.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.build_requests(["FG", "JM", "AO"], "2026-06-28")
    requests = report.get("requests") or []
    if requests:
        ok = all(
            item.get("exchange")
            and item.get("effective_market_date")
            and item.get("suggested_file")
            and item.get("source_hints")
            for item in requests
        )
        sample = requests[0]
    else:
        warehouse_hints = module.source_hints({"product_code": "AO", "exchange": "SHFE"}, "warehouse_receipt", "2026-06-26")
        position_hints = module.source_hints({"product_code": "JM", "exchange": "DCE"}, "position_rank", "2026-06-26")
        ok = any("futures_inventory_em" in (item.get("name") or "") for item in warehouse_hints) and any(
            "EastMoney" in (item.get("name") or "") for item in position_hints
        )
        sample = {
            "warehouse_hints": warehouse_hints[:2],
            "position_hints": position_hints[:2],
        }
    return {
        "cmd": "manual_request_source_hint_check",
        "returncode": 0 if ok else 1,
        "stdout": json.dumps(
            {
                "request_count": len(requests),
                "sample": sample,
            },
            ensure_ascii=False,
        ),
        "stderr": "" if ok else "manual data requests/source_hints are missing required metadata",
    }


def manual_chinese_export_check():
    spec = importlib.util.spec_from_file_location("fetch_snapshot", SCRIPTS / "fetch_china_futures_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        (data_dir / "20260626_JM_position_rank.csv").write_text(
            "日期,品种,名次,会员简称,成交量,成交量增减,持买单量,持买单量增减,持卖单量,持卖单量增减\n"
            "2026-06-26,焦煤,1,示例期货,1000,10,600,5,550,-3\n",
            encoding="gbk",
        )
        old = os.environ.get("CHINA_FUTURES_MANUAL_DATA_DIR")
        os.environ["CHINA_FUTURES_MANUAL_DATA_DIR"] = str(data_dir)
        try:
            snapshot = {
                "metadata": {
                    "analysis_date": "2026-06-28",
                    "effective_market_date": "2026-06-26",
                },
                "fundamentals": {},
                "data_source_status": {},
            }
            normalized = {"product_code": "JM", "ak_symbol": "JM", "input": "焦煤"}
            module.fetch_manual_supplements(snapshot, normalized)
        finally:
            if old is None:
                os.environ.pop("CHINA_FUTURES_MANUAL_DATA_DIR", None)
            else:
                os.environ["CHINA_FUTURES_MANUAL_DATA_DIR"] = old
    position = (snapshot.get("fundamentals") or {}).get("position_rank") or {}
    matched_rows = ((position.get("matched") or {}).get("rows") or {})
    summary = matched_rows.get("summary") or {}
    ok = (
        summary.get("top_volume") == 1000
        and summary.get("top_long_open_interest") == 600
        and summary.get("top_short_open_interest") == 550
    )
    return {
        "cmd": "manual_chinese_export_check",
        "returncode": 0 if ok else 1,
        "stdout": json.dumps({"summary": summary, "source": position.get("source")}, ensure_ascii=False),
        "stderr": "" if ok else "GBK Chinese manual position export was not parsed/summarized correctly",
    }


def exchange_probe_challenge_check():
    spec = importlib.util.spec_from_file_location("probe_exchange_sources", SCRIPTS / "probe_exchange_sources.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    body = b'<!DOCTYPE html><html><script>$_ts={};document.createElement("section")</script></html>'
    category = module.classify_error(status=200, body=body)
    ok = category == "blocked_by_exchange_waf"
    return {
        "cmd": "exchange_probe_challenge_check",
        "returncode": 0 if ok else 1,
        "stdout": json.dumps({"category": category}, ensure_ascii=False),
        "stderr": "" if ok else "HTTP 200 challenge HTML was not classified as blocked_by_exchange_waf",
    }


def main():
    parser = argparse.ArgumentParser(description="Run a quick skill validation.")
    parser.add_argument("--instrument", default="FG", help="Instrument/code for snapshot smoke test.")
    parser.add_argument("--date", default="2026-06-26", help="Date for snapshot smoke test.")
    parser.add_argument("--with-network-news", action="store_true", help="Include Jin10 network enrichment in smoke test.")
    args = parser.parse_args()

    checks = []
    for script in (
        "fetch_china_futures_snapshot.py",
        "render_daily_report.py",
        "check_data_sources.py",
        "audit_data_gaps.py",
        "probe_exchange_sources.py",
        "probe_tushare_sources.py",
        "probe_jin10_sources.py",
        "diagnose_data_readiness.py",
        "prepare_manual_data_requests.py",
        "audit_completion_status.py",
    ):
        checks.append(run([sys.executable, "-m", "py_compile", str(SCRIPTS / script)], timeout=30))

    checks.append(run([sys.executable, str(SCRIPTS / "check_data_sources.py")], timeout=60))
    checks.append(manual_supplement_check())
    checks.append(manual_effective_date_check())
    checks.append(manual_request_source_hint_check())
    checks.append(manual_chinese_export_check())
    checks.append(exchange_probe_challenge_check())
    checks.append(run([sys.executable, str(SCRIPTS / "audit_completion_status.py"), "FG", "JM", "AO", "--date", "2026-06-28", "--no-jin10", "--json"], timeout=180))

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "snapshot.json"
        report = Path(tmp) / "report.md"
        fetch_cmd = [
            sys.executable,
            str(SCRIPTS / "fetch_china_futures_snapshot.py"),
            args.instrument,
            "--date",
            args.date,
            "--out",
            str(snapshot),
            "--no-tqsdk",
            "--no-tushare",
        ]
        if not args.with_network_news:
            fetch_cmd.append("--no-jin10")
        checks.append(run(fetch_cmd, timeout=180))
        if snapshot.exists():
            checks.append(run([sys.executable, str(SCRIPTS / "render_daily_report.py"), str(snapshot), "--out", str(report)], timeout=60))
            data = json.loads(snapshot.read_text(encoding="utf-8"))
            completeness = data.get("data_completeness") or {}
            content_ok = bool(data.get("quote") and data.get("data_source_status") and completeness.get("required_total"))
            checks.append(
                {
                    "cmd": "snapshot_content_check",
                    "returncode": 0 if content_ok else 1,
                    "stdout": json.dumps(
                        {
                            "quote_source": (data.get("quote") or {}).get("source"),
                            "fundamental_keys": sorted((data.get("fundamentals") or {}).keys()),
                            "missing_count": len(data.get("missing_reasons") or []),
                            "data_completeness": completeness,
                            "supplement_errors": data.get("supplement_errors") or [],
                        },
                        ensure_ascii=False,
                    ),
                    "stderr": "" if content_ok else "snapshot missing quote, status, or data_completeness",
                }
            )

    ok = all(item["returncode"] == 0 for item in checks)
    output = {"ok": ok, "checks": checks}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
