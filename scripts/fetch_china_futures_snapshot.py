#!/usr/bin/env python3
"""Fetch a best-effort China futures snapshot.

The script is intentionally conservative: it returns partial data with explicit
missing reasons rather than fabricating market values.
"""

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import time
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None


PRODUCTS = {
    "螺纹钢": ("RB", "SHFE", "rb"),
    "螺纹": ("RB", "SHFE", "rb"),
    "rb": ("RB", "SHFE", "rb"),
    "热卷": ("HC", "SHFE", "hc"),
    "沪铜": ("CU", "SHFE", "cu"),
    "铜": ("CU", "SHFE", "cu"),
    "cu": ("CU", "SHFE", "cu"),
    "沪铝": ("AL", "SHFE", "al"),
    "铝": ("AL", "SHFE", "al"),
    "沪锌": ("ZN", "SHFE", "zn"),
    "沪镍": ("NI", "SHFE", "ni"),
    "沪锡": ("SN", "SHFE", "sn"),
    "黄金": ("AU", "SHFE", "au"),
    "白银": ("AG", "SHFE", "ag"),
    "原油": ("SC", "INE", "sc"),
    "燃油": ("FU", "SHFE", "fu"),
    "橡胶": ("RU", "SHFE", "ru"),
    "铁矿": ("I", "DCE", "i"),
    "铁矿石": ("I", "DCE", "i"),
    "i": ("I", "DCE", "i"),
    "焦炭": ("J", "DCE", "j"),
    "焦煤": ("JM", "DCE", "jm"),
    "豆粕": ("M", "DCE", "m"),
    "m": ("M", "DCE", "m"),
    "豆油": ("Y", "DCE", "y"),
    "棕榈油": ("P", "DCE", "p"),
    "玉米": ("C", "DCE", "c"),
    "鸡蛋": ("JD", "DCE", "jd"),
    "玻璃": ("FG", "CZCE", "fg"),
    "纯碱": ("SA", "CZCE", "sa"),
    "白糖": ("SR", "CZCE", "sr"),
    "棉花": ("CF", "CZCE", "cf"),
    "甲醇": ("MA", "CZCE", "ma"),
    "pta": ("TA", "CZCE", "ta"),
    "pta期货": ("TA", "CZCE", "ta"),
    "中证1000": ("IM", "CFFEX", "im"),
    "沪深300": ("IF", "CFFEX", "if"),
    "上证50": ("IH", "CFFEX", "ih"),
    "中证500": ("IC", "CFFEX", "ic"),
}


def disable_proxy_for_public_sources(snapshot):
    if os.getenv("CHINA_FUTURES_USE_PROXY"):
        snapshot["data_source_status"]["proxy"] = "kept: CHINA_FUTURES_USE_PROXY is set"
        return
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("no_proxy", "*")
    snapshot["data_source_status"]["proxy"] = "disabled for public market data requests"


def today_shanghai():
    if ZoneInfo:
        return dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    return dt.datetime.utcnow().date().isoformat()


def normalize_instrument(raw):
    value = raw.strip()
    key = value.lower()
    exact = re.match(r"^([A-Za-z]+)(\d{3,4})$", value)
    if exact:
        prefix = exact.group(1).upper()
        product = PRODUCTS.get(prefix.lower(), (prefix, None, prefix.lower()))
        return {
            "input": raw,
            "product_code": prefix,
            "exchange": product[1],
            "ak_symbol": prefix,
            "tq_symbol": f"{product[1]}.{prefix.lower()}{exact.group(2)}" if product[1] else None,
            "is_exact_contract": True,
        }
    product = PRODUCTS.get(key) or PRODUCTS.get(value)
    if product:
        code, exchange, lower = product
        return {
            "input": raw,
            "product_code": code,
            "exchange": exchange,
            "ak_symbol": code,
            "tq_symbol": f"KQ.m@{exchange}.{lower}" if exchange else None,
            "is_exact_contract": False,
        }
    prefix = re.sub(r"[^A-Za-z]", "", value).upper() or value.upper()
    return {
        "input": raw,
        "product_code": prefix,
        "exchange": None,
        "ak_symbol": prefix,
        "tq_symbol": None,
        "is_exact_contract": False,
    }


def as_float(value):
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
            if value in {"", "-", "--", "nan", "None"}:
                return None
        out = float(value)
        if math.isnan(out):
            return None
        return out
    except Exception:
        return None


def frame_records(obj, limit=None):
    try:
        records = obj.to_dict(orient="records")
    except Exception:
        if isinstance(obj, list):
            records = obj
        else:
            return []
    cleaned = []
    for row in records[-limit:] if limit else records:
        item = {}
        for key, value in row.items():
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif isinstance(value, float) and math.isnan(value):
                value = None
            else:
                value = str(value) if not isinstance(value, (int, float, str, bool, type(None))) else value
            item[str(key)] = value
        cleaned.append(item)
    return cleaned


def update_quote_from_row(snapshot, row, source):
    quote = snapshot["quote"]
    aliases = {
        "contract": ["symbol", "合约", "合约代码", "代码", "品种"],
        "last": ["最新价", "last", "price", "现价", "最新"],
        "change_pct": ["涨跌幅", "changepercent", "涨幅", "涨跌幅度"],
        "change": ["涨跌", "change", "涨跌额"],
        "volume": ["成交量", "volume", "成交"],
        "open_interest": ["持仓量", "open_interest", "持仓"],
        "settlement": ["结算价", "settlement", "昨结算"],
    }
    for target, names in aliases.items():
        for name in names:
            if name in row and row[name] not in (None, ""):
                quote[target] = row[name] if target == "contract" else as_float(row[name])
                break
    quote["source"] = source


def fetch_with_tqsdk(snapshot, normalized, want_tq=True):
    if not want_tq:
        snapshot["data_source_status"]["tqsdk"] = "skipped by flag"
        return
    symbol = normalized.get("tq_symbol")
    if not symbol:
        snapshot["data_source_status"]["tqsdk"] = "skipped: no TqSdk symbol mapping"
        return
    if not (os.getenv("TQSDK_USER") and os.getenv("TQSDK_PASSWORD")):
        snapshot["data_source_status"]["tqsdk"] = "skipped: TQSDK_USER/TQSDK_PASSWORD not set"
        return
    try:
        from tqsdk import TqApi, TqAuth
    except Exception as exc:
        snapshot["data_source_status"]["tqsdk"] = f"unavailable: {exc}"
        return
    api = None
    try:
        api = TqApi(auth=TqAuth(os.getenv("TQSDK_USER"), os.getenv("TQSDK_PASSWORD")))
        quote = api.get_quote(symbol)
        api.wait_update(deadline=time.time() + 5)
        snapshot["quote"].update(
            {
                "contract": getattr(quote, "instrument_id", None) or symbol,
                "last": as_float(getattr(quote, "last_price", None)),
                "change": as_float(getattr(quote, "change", None)),
                "change_pct": as_float(getattr(quote, "change_percent", None)),
                "volume": as_float(getattr(quote, "volume", None)),
                "open_interest": as_float(getattr(quote, "open_interest", None)),
                "settlement": as_float(getattr(quote, "settlement", None)),
                "source": "TqSdk",
            }
        )
        snapshot["data_source_status"]["tqsdk"] = "ok"
    except Exception as exc:
        snapshot["data_source_status"]["tqsdk"] = f"failed: {exc}"
    finally:
        if api is not None:
            try:
                api.close()
            except Exception:
                pass


def latest_bar_values(snapshot):
    bars = snapshot.get("daily_bars") or []
    if not bars:
        return None, None
    latest = bars[-1]
    previous = bars[-2] if len(bars) >= 2 else {}
    close = as_float(latest.get("close") or latest.get("收盘价") or latest.get("收盘"))
    prev_close = as_float(previous.get("close") or previous.get("收盘价") or previous.get("收盘"))
    volume = as_float(latest.get("volume") or latest.get("成交量") or latest.get("成交"))
    hold = as_float(latest.get("hold") or latest.get("open_interest") or latest.get("持仓量") or latest.get("持仓"))
    settle = as_float(latest.get("settle") or latest.get("settlement") or latest.get("结算价"))
    high = as_float(latest.get("high") or latest.get("最高价") or latest.get("最高"))
    low = as_float(latest.get("low") or latest.get("最低价") or latest.get("最低"))
    open_ = as_float(latest.get("open") or latest.get("开盘价") or latest.get("开盘"))
    date = latest.get("date") or latest.get("日期")
    return latest, {
        "date": date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "prev_close": prev_close,
        "volume": volume,
        "open_interest": hold,
        "settlement": settle,
        "change": close - prev_close if close is not None and prev_close is not None else None,
        "change_pct": ((close - prev_close) / prev_close * 100) if close is not None and prev_close else None,
    }


def try_call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs), None
    except Exception as exc:
        return None, str(exc)


def fetch_with_akshare(snapshot, normalized):
    disable_proxy_for_public_sources(snapshot)
    try:
        import akshare as ak
    except Exception as exc:
        snapshot["data_source_status"]["akshare"] = f"unavailable: {exc}"
        return

    errors = []
    symbol = normalized["ak_symbol"]

    candidates = [
        ("futures_zh_spot", {"symbol": symbol, "market": "CF", "adjust": "0"}),
        ("futures_zh_realtime", {"symbol": symbol}),
        ("futures_main_sina", {"symbol": symbol}),
    ]
    for name, kwargs in candidates:
        func = getattr(ak, name, None)
        if not func:
            continue
        data, err = try_call(func, **kwargs)
        if err:
            errors.append(f"{name}: {err}")
            continue
        records = frame_records(data, limit=5)
        if records:
            update_quote_from_row(snapshot, records[-1], f"AKShare.{name}")
            snapshot["raw_samples"][name] = records
            snapshot["data_source_status"]["akshare"] = "ok"
            break

    daily_candidates = [
        ("futures_zh_daily_sina", {"symbol": symbol.lower() + "0"}),
        ("futures_zh_daily_sina", {"symbol": symbol.upper() + "0"}),
    ]
    for name, kwargs in daily_candidates:
        func = getattr(ak, name, None)
        if not func:
            continue
        data, err = try_call(func, **kwargs)
        if err:
            errors.append(f"{name}: {err}")
            continue
        records = frame_records(data, limit=80)
        if records:
            snapshot["daily_bars"] = records
            snapshot["data_source_status"]["akshare_daily"] = "ok"
            break

    if "akshare" not in snapshot["data_source_status"]:
        snapshot["data_source_status"]["akshare"] = "no quote returned" if not errors else "; ".join(errors[:3])
    if "akshare_daily" not in snapshot["data_source_status"]:
        snapshot["data_source_status"]["akshare_daily"] = "no daily bars returned"


def compute_technical(snapshot):
    bars = snapshot.get("daily_bars") or []
    closes = []
    highs = []
    lows = []
    for row in bars:
        close = None
        high = None
        low = None
        for key in ["close", "收盘价", "收盘", "Close"]:
            close = as_float(row.get(key))
            if close is not None:
                break
        for key in ["high", "最高价", "最高", "High"]:
            high = as_float(row.get(key))
            if high is not None:
                break
        for key in ["low", "最低价", "最低", "Low"]:
            low = as_float(row.get(key))
            if low is not None:
                break
        if close is not None:
            closes.append(close)
        if high is not None:
            highs.append(high)
        if low is not None:
            lows.append(low)
    tech = snapshot["technical"]
    if closes:
        tech["last_close"] = closes[-1]
        tech["ma5"] = sum(closes[-5:]) / min(5, len(closes))
        tech["ma20"] = sum(closes[-20:]) / min(20, len(closes))
        tech["trend"] = "above_ma20" if len(closes) >= 20 and closes[-1] >= tech["ma20"] else "below_or_insufficient_ma20"
    if highs:
        tech["resistance_20d"] = max(highs[-20:])
    if lows:
        tech["support_20d"] = min(lows[-20:])
    if len(closes) < 20:
        snapshot["missing_reasons"].append("daily_bars: fewer than 20 usable closes for robust technical context")


def enrich_quote_from_daily_bars(snapshot):
    quote = snapshot["quote"]
    _, values = latest_bar_values(snapshot)
    if not values:
        return
    quote["daily_bar_date"] = values["date"]
    quote["open"] = values["open"]
    quote["high"] = values["high"]
    quote["low"] = values["low"]
    if quote.get("change") is None:
        quote["change"] = values["change"]
    if quote.get("change_pct") is None:
        quote["change_pct"] = values["change_pct"]
    if quote.get("volume") is None:
        quote["volume"] = values["volume"]
    if quote.get("open_interest") is None:
        quote["open_interest"] = values["open_interest"]
    if quote.get("settlement") is None:
        quote["settlement"] = values["settlement"]
    if quote.get("source") == "TqSdk":
        quote["source_detail"] = "TqSdk quote enriched with latest daily bar"


def fill_quote_from_daily_bars(snapshot):
    quote = snapshot["quote"]
    if quote.get("last") is not None:
        return
    _, values = latest_bar_values(snapshot)
    if not values:
        return
    normalized = snapshot.get("normalized") or {}
    quote.update(
        {
            "contract": normalized.get("product_code") + " main/daily" if normalized.get("product_code") else None,
            "last": values["close"],
            "change": values["change"],
            "change_pct": values["change_pct"],
            "volume": values["volume"],
            "open_interest": values["open_interest"],
            "settlement": values["settlement"],
            "open": values["open"],
            "high": values["high"],
            "low": values["low"],
            "daily_bar_date": values["date"],
            "source": "AKShare.daily_bars_fallback",
        }
    )


def finalize_missing(snapshot):
    quote = snapshot["quote"]
    for field in ["contract", "last", "change_pct", "volume", "open_interest"]:
        if quote.get(field) in (None, ""):
            snapshot["missing_reasons"].append(f"quote.{field}: unavailable from configured data sources")
    if not snapshot.get("daily_bars"):
        snapshot["missing_reasons"].append("daily_bars: unavailable from configured data sources")
    if not snapshot["fundamentals"]:
        snapshot["missing_reasons"].append("fundamentals: not fetched by local script; use exchange/current web sources if needed")
    if not snapshot["news"]:
        snapshot["missing_reasons"].append("news: not fetched by local script; use current source-backed web search if needed")


def build_snapshot(args):
    normalized = normalize_instrument(args.instrument)
    snapshot = {
        "metadata": {
            "generated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "analysis_date": args.date or today_shanghai(),
            "timezone": "Asia/Shanghai",
        },
        "input": {"instrument": args.instrument},
        "normalized": normalized,
        "data_source_status": {},
        "quote": {
            "contract": None,
            "last": None,
            "change": None,
            "change_pct": None,
            "open": None,
            "high": None,
            "low": None,
            "daily_bar_date": None,
            "volume": None,
            "open_interest": None,
            "settlement": None,
            "source": None,
            "source_detail": None,
        },
        "daily_bars": [],
        "technical": {},
        "fundamentals": {},
        "news": [],
        "raw_samples": {},
        "missing_reasons": [],
        "warnings": [],
    }
    disable_proxy_for_public_sources(snapshot)
    fetch_with_tqsdk(snapshot, normalized, want_tq=not args.no_tqsdk)
    if snapshot["quote"].get("last") is None or not snapshot.get("daily_bars"):
        fetch_with_akshare(snapshot, normalized)
    compute_technical(snapshot)
    enrich_quote_from_daily_bars(snapshot)
    fill_quote_from_daily_bars(snapshot)
    finalize_missing(snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Fetch a China futures market snapshot.")
    parser.add_argument("instrument", help="Chinese futures variety name or contract code, e.g. 螺纹钢, 沪铜, RB2410")
    parser.add_argument("--date", default=None, help="Analysis date, YYYY-MM-DD. Defaults to Asia/Shanghai today.")
    parser.add_argument("--out", default=None, help="Write JSON to this file instead of stdout.")
    parser.add_argument("--no-tqsdk", action="store_true", help="Skip TqSdk even if configured.")
    args = parser.parse_args()
    snapshot = build_snapshot(args)
    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
