#!/usr/bin/env python3
"""Fast intraday quote watcher for China futures.

This script is intentionally narrow: it fetches batch TqSdk quotes for live
watching and skips slow daily-report enrichments such as basis, warehouse
receipts, position ranks, AKShare public fallbacks, and Jin10 news.
"""

import argparse
import contextlib
import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fetch_china_futures_snapshot import (  # noqa: E402
    as_float,
    disable_proxy_for_public_sources,
    normalize_instrument,
    restore_proxy_env,
)


def now_shanghai():
    if ZoneInfo:
        return dt.datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat()
    return dt.datetime.now().replace(microsecond=0).isoformat()


def quote_to_dict(symbol, quote):
    return {
        "contract": getattr(quote, "instrument_id", None) or symbol,
        "last": as_float(getattr(quote, "last_price", None)),
        "change": as_float(getattr(quote, "change", None)),
        "change_pct": as_float(getattr(quote, "change_percent", None)),
        "open": as_float(getattr(quote, "open", None)),
        "high": as_float(getattr(quote, "highest", None)),
        "low": as_float(getattr(quote, "lowest", None)),
        "bid_price1": as_float(getattr(quote, "bid_price1", None)),
        "ask_price1": as_float(getattr(quote, "ask_price1", None)),
        "volume": as_float(getattr(quote, "volume", None)),
        "open_interest": as_float(getattr(quote, "open_interest", None)),
        "datetime": getattr(quote, "datetime", None),
        "source": "TqSdk",
    }


def fetch_tqsdk_quotes(symbols, wait_seconds=3.0):
    logging.disable(logging.INFO)
    from tqsdk import TqApi, TqAuth

    user = os.getenv("TQSDK_USER")
    password = os.getenv("TQSDK_PASSWORD")
    quotes = {}
    api = None
    proxy_snapshot = {"data_source_status": {}}
    proxy_env = disable_proxy_for_public_sources(proxy_snapshot)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            api = TqApi(auth=TqAuth(user, password))
            quote_objects = {symbol: api.get_quote(symbol) for symbol in symbols}
            api.wait_update(deadline=time.time() + wait_seconds)
            for symbol, quote in quote_objects.items():
                quotes[symbol] = quote_to_dict(symbol, quote)
    finally:
        if api is not None:
            with contextlib.redirect_stdout(sys.stderr):
                api.close()
        restore_proxy_env(proxy_env)
    return quotes


def compact_missing_reason(quote, error=None):
    if error:
        return f"tqsdk: {error}"
    missing = [field for field in ("last", "volume", "open_interest") if quote.get(field) in (None, "")]
    if missing:
        return "quote." + ",".join(missing) + ": unavailable from TqSdk watch mode"
    return None


def build_watch_snapshot(instruments, wait_seconds=3.0, fetcher=None):
    normalized_items = []
    symbols = []
    for raw in instruments:
        normalized = normalize_instrument(raw)
        symbol = normalized.get("tq_symbol")
        normalized_items.append((raw, normalized, symbol))
        if symbol:
            symbols.append(symbol)

    fetcher = fetcher or fetch_tqsdk_quotes
    quote_map = {}
    fetch_error = None
    if symbols:
        try:
            quote_map = fetcher(symbols, wait_seconds)
        except Exception as exc:
            fetch_error = str(exc)

    rows = []
    for raw, normalized, symbol in normalized_items:
        quote = quote_map.get(symbol) or {
            "contract": symbol,
            "last": None,
            "change": None,
            "change_pct": None,
            "open": None,
            "high": None,
            "low": None,
            "bid_price1": None,
            "ask_price1": None,
            "volume": None,
            "open_interest": None,
            "datetime": None,
            "source": "TqSdk",
        }
        reason = compact_missing_reason(quote, fetch_error)
        rows.append(
            {
                "input": raw,
                "normalized": normalized,
                "quote": quote,
                "missing_reasons": [reason] if reason else [],
            }
        )

    return {
        "metadata": {
            "mode": "intraday_watch",
            "generated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "generated_at_shanghai": now_shanghai(),
            "timezone": "Asia/Shanghai",
            "wait_seconds": wait_seconds,
            "source_policy": "TqSdk batch quotes only; skips AKShare, Jin10, basis, warehouse receipts, and position ranks.",
        },
        "instruments": rows,
    }


def render_text(snapshot):
    lines = []
    for item in snapshot.get("instruments") or []:
        quote = item.get("quote") or {}
        normalized = item.get("normalized") or {}
        name = item.get("input")
        code = normalized.get("product_code")
        lines.append(
            "{name}({code}) last={last} high={high} low={low} vol={volume} oi={open_interest} source={source}".format(
                name=name,
                code=code,
                last=quote.get("last"),
                high=quote.get("high"),
                low=quote.get("low"),
                volume=quote.get("volume"),
                open_interest=quote.get("open_interest"),
                source=quote.get("source"),
            )
        )
        for reason in item.get("missing_reasons") or []:
            lines.append(f"  missing: {reason}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Fetch fast batch TqSdk quotes for intraday China futures watching.")
    parser.add_argument("instruments", nargs="+", help="Chinese variety names or contract codes, e.g. 焦煤 玻璃 JM2609")
    parser.add_argument("--wait-seconds", type=float, default=3.0, help="Seconds to wait for the first TqSdk update.")
    parser.add_argument("--format", choices=("json", "text"), default="json", help="Output format.")
    parser.add_argument("--out", default=None, help="Write output to this file instead of stdout.")
    args = parser.parse_args()

    snapshot = build_watch_snapshot(args.instruments, wait_seconds=max(args.wait_seconds, 0.0))
    if args.format == "text":
        text = render_text(snapshot) + "\n"
    else:
        text = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
