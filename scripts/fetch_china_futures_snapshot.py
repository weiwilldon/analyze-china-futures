#!/usr/bin/env python3
"""Fetch a best-effort China futures snapshot.

The script is intentionally conservative: it returns partial data with explicit
missing reasons rather than fabricating market values.
"""

import argparse
import gzip
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
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
    "生猪": ("LH", "DCE", "lh"),
    "玻璃": ("FG", "CZCE", "fg"),
    "纯碱": ("SA", "CZCE", "sa"),
    "白糖": ("SR", "CZCE", "sr"),
    "棉花": ("CF", "CZCE", "cf"),
    "甲醇": ("MA", "CZCE", "ma"),
    "pta": ("TA", "CZCE", "ta"),
    "pta期货": ("TA", "CZCE", "ta"),
    "工业硅": ("SI", "GFEX", "si"),
    "硅": ("SI", "GFEX", "si"),
    "碳酸锂": ("LC", "GFEX", "lc"),
    "锂": ("LC", "GFEX", "lc"),
    "中证1000": ("IM", "CFFEX", "im"),
    "沪深300": ("IF", "CFFEX", "if"),
    "上证50": ("IH", "CFFEX", "ih"),
    "中证500": ("IC", "CFFEX", "ic"),
}

PRODUCTS.update(
    {
        "fg": ("FG", "CZCE", "fg"),
        "sa": ("SA", "CZCE", "sa"),
        "ta": ("TA", "CZCE", "ta"),
        "ma": ("MA", "CZCE", "ma"),
        "sr": ("SR", "CZCE", "sr"),
        "cf": ("CF", "CZCE", "cf"),
        "rm": ("RM", "CZCE", "rm"),
        "oi": ("OI", "CZCE", "oi"),
        "jm": ("JM", "DCE", "jm"),
        "j": ("J", "DCE", "j"),
        "lh": ("LH", "DCE", "lh"),
        "rb": ("RB", "SHFE", "rb"),
        "hc": ("HC", "SHFE", "hc"),
        "cu": ("CU", "SHFE", "cu"),
        "al": ("AL", "SHFE", "al"),
        "zn": ("ZN", "SHFE", "zn"),
        "pb": ("PB", "SHFE", "pb"),
        "ni": ("NI", "SHFE", "ni"),
        "sn": ("SN", "SHFE", "sn"),
        "au": ("AU", "SHFE", "au"),
        "ag": ("AG", "SHFE", "ag"),
        "ru": ("RU", "SHFE", "ru"),
        "bu": ("BU", "SHFE", "bu"),
        "fu": ("FU", "SHFE", "fu"),
        "ao": ("AO", "SHFE", "ao"),
        "氧化铝": ("AO", "SHFE", "ao"),
        "si": ("SI", "GFEX", "si"),
        "lc": ("LC", "GFEX", "lc"),
    }
)

BASIS_PRODUCT_NAMES = {
    "RB": ["螺纹钢"],
    "HC": ["热轧板卷", "热卷"],
    "CU": ["铜"],
    "AL": ["铝"],
    "ZN": ["锌"],
    "PB": ["铅"],
    "NI": ["镍"],
    "SN": ["锡"],
    "AU": ["黄金"],
    "AG": ["白银"],
    "RU": ["天然橡胶", "橡胶"],
    "BU": ["沥青"],
    "FU": ["燃料油"],
    "FG": ["玻璃"],
    "SA": ["纯碱"],
    "MA": ["甲醇"],
    "TA": ["PTA"],
    "SR": ["白糖"],
    "CF": ["棉花"],
    "RM": ["菜粕"],
    "OI": ["菜籽油", "菜油"],
    "I": ["铁矿石"],
    "J": ["焦炭"],
    "JM": ["焦煤"],
    "M": ["豆粕"],
    "Y": ["豆油"],
    "P": ["棕榈油"],
    "C": ["玉米"],
    "JD": ["鸡蛋"],
    "AO": ["氧化铝"],
    "SI": ["工业硅"],
    "LC": ["碳酸锂"],
}

SMM_SPOT_SOURCES = {
    "AO": {
        "url": "https://hq.smm.cn/h5/SMM-alumina-price",
        "names": ["SMM氧化铝价格", "SMM氧化铝指数", "氧化铝全国加权平均指数价"],
        "product_ids": ["201106140030"],
    },
    "CU": {
        "url": "https://hq.smm.cn/h5/cu",
        "names": ["上海今日铜价", "长江现货铜价", "华东今日铜价"],
        "product_ids": ["201102250376"],
    },
    "AL": {
        "url": "https://hq.smm.cn/h5/alu",
        "names": ["上海铝锭价格", "无锡铝锭价格", "佛山铝锭价格"],
        "product_ids": ["201102250311"],
    },
    "ZN": {
        "url": "https://hq.smm.cn/h5/zn",
        "names": ["上海现货锌锭价格0#", "长江现货锌锭价格0#"],
        "product_ids": ["201102250173"],
    },
    "PB": {
        "url": "https://hq.smm.cn/h5/pb",
        "names": ["上海现货铅锭价格", "长江现货铅锭价格"],
        "product_ids": ["201102250211"],
    },
    "NI": {
        "url": "https://hq.smm.cn/h5/ni",
        "names": ["上海镍价格", "长江镍价格"],
        "product_ids": ["201102250239"],
    },
    "SN": {
        "url": "https://hq.smm.cn/h5/sn",
        "names": ["上海锡锭价格", "长江锡锭价格"],
        "product_ids": ["201102250140"],
    },
    "LC": {
        "url": "https://hq.smm.cn/h5/Li2CO3",
        "names": ["SMM电池级碳酸锂指数", "电池级碳酸锂价格指数", "电池级碳酸锂"],
        "product_ids": ["202212050001"],
    },
    "SI": {
        "url": "https://hq.smm.cn/h5/si",
        "names": ["553#硅华东金属硅价格", "553#硅上海金属硅价格"],
        "product_ids": ["201812270001"],
    },
}


EASTMONEY_LHB_MARKETS = {
    "SHFE": "113",
    "DCE": "114",
    "CZCE": "115",
    "GFEX": "225",
    "INE": "142",
    "CFFEX": "220",
}


PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy")


def tq_product_symbol(exchange, lower):
    if exchange in {"CZCE", "CFFEX"}:
        return lower.upper()
    return lower.lower()


def disable_proxy_for_public_sources(snapshot):
    saved = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
    if os.getenv("CHINA_FUTURES_USE_PROXY"):
        snapshot["data_source_status"]["proxy"] = "kept: CHINA_FUTURES_USE_PROXY is set"
        return saved
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("no_proxy", "*")
    snapshot["data_source_status"]["proxy"] = "disabled for public market data requests"
    return saved


def restore_proxy_env(saved):
    if not isinstance(saved, dict):
        return
    for key in PROXY_ENV_KEYS:
        value = saved.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def today_shanghai():
    if ZoneInfo:
        return dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    return dt.datetime.utcnow().date().isoformat()


def date_candidates(analysis_date, days=7):
    try:
        start = dt.datetime.strptime(analysis_date, "%Y-%m-%d").date()
    except Exception:
        start = dt.date.today()
    return [(start - dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]


def snapshot_date_candidates(snapshot, days=7):
    metadata = snapshot.get("metadata") or {}
    analysis_date = metadata.get("analysis_date") or today_shanghai()
    seeds = []
    effective_date = metadata.get("effective_market_date")
    if effective_date:
        seeds.append(effective_date)
    seeds.append(analysis_date)
    out = []
    seen = set()
    for seed in seeds:
        for item in date_candidates(seed, days=days):
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def supplement_lookback_days(default=3):
    try:
        return max(1, min(10, int(os.getenv("CHINA_FUTURES_SUPPLEMENT_LOOKBACK_DAYS", str(default)))))
    except Exception:
        return default


def basis_lookback_days(default=3):
    try:
        return max(1, min(10, int(os.getenv("CHINA_FUTURES_BASIS_LOOKBACK_DAYS", str(default)))))
    except Exception:
        return default


def iso_date(compact_date):
    try:
        return dt.datetime.strptime(str(compact_date), "%Y%m%d").date().isoformat()
    except Exception:
        return compact_date


def normalize_date_text(value):
    if value in (None, ""):
        return None
    text = str(value)
    if " " in text:
        text = text.split(" ", 1)[0]
    if re.match(r"^\d{8}$", text):
        text = iso_date(text)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", str(text)):
        return str(text)
    return None


def normalize_instrument(raw):
    value = raw.strip()
    key = value.lower()
    exact = re.match(r"^([A-Za-z]+)(\d{3,4})$", value)
    if exact:
        prefix = exact.group(1).upper()
        product = PRODUCTS.get(prefix.lower(), (prefix, None, prefix.lower()))
        tq_prefix = tq_product_symbol(product[1], product[2]) if product[1] else prefix
        return {
            "input": raw,
            "product_code": prefix,
            "exchange": product[1],
            "ak_symbol": prefix,
            "tq_symbol": f"{product[1]}.{tq_prefix}{exact.group(2)}" if product[1] else None,
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
            "tq_symbol": f"KQ.m@{exchange}.{tq_product_symbol(exchange, lower)}" if exchange else None,
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


def latest_record(records, date_key_candidates=("日期", "date")):
    if not records:
        return None
    return records[-1]


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
        klines = api.get_kline_serial(symbol, 24 * 60 * 60, data_length=80)
        api.wait_update(deadline=time.time() + 5)
        snapshot["quote"].update(
            {
                "contract": getattr(quote, "instrument_id", None) or symbol,
                "last": as_float(getattr(quote, "last_price", None)),
                "change": as_float(getattr(quote, "change", None)),
                "change_pct": as_float(getattr(quote, "change_percent", None)),
                "open": as_float(getattr(quote, "open", None)),
                "high": as_float(getattr(quote, "highest", None)),
                "low": as_float(getattr(quote, "lowest", None)),
                "volume": as_float(getattr(quote, "volume", None)),
                "open_interest": as_float(getattr(quote, "open_interest", None)),
                "settlement": as_float(getattr(quote, "settlement", None)),
                "source": "TqSdk",
            }
        )
        records = tqsdk_kline_records(klines)
        if records:
            snapshot["daily_bars"] = records
        snapshot["data_source_status"]["tqsdk"] = "ok"
    except Exception as exc:
        snapshot["data_source_status"]["tqsdk"] = f"failed: {exc}"
    finally:
        if api is not None:
            try:
                api.close()
            except Exception:
                pass


def tqsdk_datetime_to_date(value):
    numeric = as_float(value)
    if numeric is None:
        return None
    try:
        return dt.datetime.fromtimestamp(numeric / 1_000_000_000).date().isoformat()
    except Exception:
        return None


def tqsdk_kline_records(klines):
    records = frame_records(klines, limit=80)
    out = []
    for row in records:
        close = as_float(row.get("close"))
        if close is None:
            continue
        hold = as_float(row.get("close_oi"))
        if hold is None:
            hold = as_float(row.get("open_oi"))
        item = {
            "date": tqsdk_datetime_to_date(row.get("datetime")),
            "open": as_float(row.get("open")),
            "high": as_float(row.get("high")),
            "low": as_float(row.get("low")),
            "close": close,
            "volume": as_float(row.get("volume")),
            "hold": hold,
        }
        if item["date"]:
            out.append(item)
    return out


def bar_date(row):
    return normalize_date_text(first_existing(row, ["date", "日期", "datetime", "trade_date"]))


def bars_through_analysis_date(snapshot):
    bars = snapshot.get("daily_bars") or []
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date")
    if not analysis_date:
        return bars
    dated = []
    undated = []
    for row in bars:
        date = bar_date(row)
        if date is None:
            undated.append(row)
        elif date <= analysis_date:
            dated.append(row)
    return dated or undated


def latest_bar_values(snapshot):
    bars = bars_through_analysis_date(snapshot)
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


def classify_fetch_error(message):
    text = str(message or "")
    if "HTTP 404" in text or "当日无数据" in text or "no data for date" in text:
        return "no_data_for_date"
    if "401" in text or "无权限" in text or "permission" in text.lower():
        return "auth_or_permission"
    if "412" in text or "Precondition Failed" in text:
        return "blocked_by_exchange_waf"
    if "HTML challenge" in text or "blocked_by_exchange_waf" in text:
        return "blocked_by_exchange_waf"
    if "NameResolutionError" in text or "getaddrinfo failed" in text or "Failed to resolve" in text:
        return "dns_or_network_failure"
    if "timed out" in text or "timeout" in text.lower():
        return "timeout"
    if "SoupStrainer" in text or "Excel file format" in text:
        return "parser_or_format_changed"
    return "source_error"


def fetch_with_akshare(snapshot, normalized):
    try:
        import akshare as ak
    except Exception as exc:
        snapshot["data_source_status"]["akshare"] = f"unavailable: {exc}"
        return

    errors = []
    symbol = normalized["ak_symbol"]
    exact_symbol = None
    if normalized.get("is_exact_contract"):
        exact_symbol = str(normalized.get("input") or "").strip()
    quote_symbols = [symbol]
    if exact_symbol:
        quote_symbols = [exact_symbol, exact_symbol.lower(), exact_symbol.upper(), symbol]

    candidates = []
    for candidate_symbol in quote_symbols:
        candidates.extend(
            [
                ("futures_zh_spot", {"symbol": candidate_symbol, "market": "CF", "adjust": "0"}),
                ("futures_zh_realtime", {"symbol": candidate_symbol}),
                ("futures_main_sina", {"symbol": candidate_symbol}),
            ]
        )
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

    if exact_symbol:
        daily_symbols = [exact_symbol.lower(), exact_symbol.upper()]
    else:
        daily_symbols = [symbol.lower() + "0", symbol.upper() + "0"]
    daily_candidates = [("futures_zh_daily_sina", {"symbol": item}) for item in daily_symbols]
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


def first_existing(row, keys):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def row_text(row):
    try:
        return json.dumps(row, ensure_ascii=False, default=str).upper()
    except Exception:
        return str(row).upper()


def filter_rows_for_product(records, code, name=None):
    code = (code or "").upper()
    out = []
    for row in records:
        text = row_text(row)
        if (code and code in text) or (name and str(name) in str(row)):
            out.append(row)
    return out


def summarize_position_records(records):
    def sum_key(keys):
        total = 0.0
        seen = False
        for row in records:
            value = as_float(first_existing(row, keys))
            if value is not None:
                total += value
                seen = True
        return total if seen else None

    return {
        "top_rows": records[:20],
        "summary": {
            "top_volume": sum_key(["vol", "volume", "成交量", "成交"]),
            "top_volume_change": sum_key(["vol_chg", "volume_chg", "成交量增减", "成交增减", "增减1"]),
            "top_long_open_interest": sum_key(["long_open_interest", "long", "持买单量", "持买", "多头持仓", "持买量"]),
            "top_long_change": sum_key(["long_open_interest_chg", "long_chg", "持买单量增减", "持买增减", "多头增减", "增减2"]),
            "top_short_open_interest": sum_key(["short_open_interest", "short", "持卖单量", "持卖", "空头持仓", "持卖量"]),
            "top_short_change": sum_key(["short_open_interest_chg", "short_chg", "持卖单量增减", "持卖增减", "空头增减", "增减3"]),
        },
    }


def eastmoney_lhb_contract(normalized):
    code = (normalized.get("product_code") or "").upper()
    exchange = normalized.get("exchange")
    if exchange in {"DCE", "GFEX", "INE"}:
        return code.lower()
    return code


def eastmoney_lhb_request(endpoint, params, timeout=20):
    query = urllib.parse.urlencode(params)
    url = f"https://qhhqzl.eastmoney.com/marketFutuWeb/dragonAndTigerInfo/{endpoint}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
            "Accept": "application/json,*/*",
            "Referer": "https://qhweb.eastmoney.com/lhb/",
            "Origin": "https://qhweb.eastmoney.com",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if payload.get("code") != 10000:
        raise RuntimeError(payload.get("msg") or f"EastMoney response code {payload.get('code')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("EastMoney response data is not an object")
    return data


def merge_eastmoney_rank_rows(position_data, volume_data):
    merged = {}

    def item_key(row):
        return (
            str(row.get("futureCompanyCodeNew") or "")
            or str(row.get("futureCompanyCode") or "")
            or str(row.get("futureCompanyName") or "")
        )

    def get_row(source):
        key = item_key(source)
        if not key:
            key = str(len(merged))
        return merged.setdefault(
            key,
            {
                "future_company_code": source.get("futureCompanyCodeNew") or source.get("futureCompanyCode"),
                "future_company_name": source.get("futureCompanyName"),
            },
        )

    for rank, row in enumerate(volume_data.get("vloumeInfoList") or [], start=1):
        item = get_row(row)
        item.update(
            {
                "volume_rank": rank,
                "vol_party_name": row.get("futureCompanyName"),
                "vol": as_float(row.get("vloume")),
                "vol_chg": as_float(row.get("vloumeChange")),
                "volume_rate": as_float(row.get("vloumeRate")),
            }
        )
    for rank, row in enumerate(position_data.get("longInfoList") or [], start=1):
        item = get_row(row)
        item.update(
            {
                "long_rank": rank,
                "long_party_name": row.get("futureCompanyName"),
                "long_open_interest": as_float(row.get("longNum")),
                "long_open_interest_chg": as_float(row.get("longChange")),
                "long_position_rate": as_float(row.get("positionRate")),
            }
        )
    for rank, row in enumerate(position_data.get("shortInfoList") or [], start=1):
        item = get_row(row)
        item.update(
            {
                "short_rank": rank,
                "short_party_name": row.get("futureCompanyName"),
                "short_open_interest": as_float(row.get("shortNum")),
                "short_open_interest_chg": as_float(row.get("shortChange")),
                "short_position_rate": as_float(row.get("positionRate")),
            }
        )

    rows = list(merged.values())

    def sort_key(row):
        ranks = [
            row.get("volume_rank"),
            row.get("long_rank"),
            row.get("short_rank"),
        ]
        ranks = [value for value in ranks if isinstance(value, int)]
        return min(ranks) if ranks else 9999

    return sorted(rows, key=sort_key)


def fetch_eastmoney_position_rank(snapshot, normalized):
    exchange = normalized.get("exchange")
    market = EASTMONEY_LHB_MARKETS.get(exchange)
    contract = eastmoney_lhb_contract(normalized)
    if not (market and contract):
        return None, "no EastMoney market/contract mapping"
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        params = {"contract": contract, "market": market, "date": candidate_date}
        try:
            position_data = eastmoney_lhb_request("getLongAndShortPosition", params)
            volume_data = eastmoney_lhb_request("getVloumeInfo", params)
            trade_date = position_data.get("tradeDate") or volume_data.get("tradeDate") or candidate_date
            rows = merge_eastmoney_rank_rows(position_data, volume_data)
            if rows:
                summary_rows = rows[:100]
                return {
                    "source": "EastMoney.qhhqzl.dragonAndTigerInfo",
                    "date": iso_date(trade_date),
                    "contract": position_data.get("contract") or contract,
                    "market": market,
                    "matched": {"rows": summarize_position_records(summary_rows)},
                    "raw_totals": {
                        "total_long_open_interest": as_float(position_data.get("totalLongPosition")),
                        "total_long_change": as_float(position_data.get("totalLongChange")),
                        "total_short_open_interest": as_float(position_data.get("totalShortPosition")),
                        "total_short_change": as_float(position_data.get("totalShortChange")),
                        "total_volume": as_float(volume_data.get("totalVloume")),
                        "total_volume_change": as_float(volume_data.get("totalVloumeChange")),
                    },
                    "coverage_note": "public EastMoney futures dragon-and-tiger board; exchange official ranking remains preferred when available",
                }, None
            last_error = "no ranking rows returned"
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "no rows returned"


def warehouse_receipt_from_inventory(snapshot, normalized):
    inventory = (snapshot.get("fundamentals") or {}).get("inventory") or {}
    value = inventory.get("value")
    if value in (None, ""):
        return None
    return {
        "source": f"{inventory.get('source', 'inventory')}.aggregate_warehouse_fallback",
        "date": inventory.get("date"),
        "granularity": "aggregate",
        "quality": "aggregate_inventory_or_receipt_series",
        "matched_rows": {
            "rows": [
                {
                    "product_code": (normalized.get("product_code") or "").upper(),
                    "product": normalized.get("input"),
                    "warehouse": "aggregate",
                    "receipt": value,
                    "receipt_chg": inventory.get("change"),
                    "unit": inventory.get("unit"),
                    "raw": inventory.get("raw"),
                }
            ]
        },
        "coverage_note": "Derived from AKShare futures_inventory_em public inventory/warehouse daily series; aggregate only, not warehouse-level receipt rows.",
    }


DCE_PRODUCT_ALIASES = {
    "A": ["\u8c46\u4e00", "\u9ec4\u5927\u8c461\u53f7"],
    "B": ["\u8c46\u4e8c", "\u9ec4\u5927\u8c462\u53f7"],
    "M": ["\u8c46\u7c95"],
    "Y": ["\u8c46\u6cb9"],
    "P": ["\u68d5\u6988\u6cb9"],
    "C": ["\u7389\u7c73"],
    "CS": ["\u7389\u7c73\u6dc0\u7c89"],
    "I": ["\u94c1\u77ff\u77f3"],
    "J": ["\u7126\u70ad"],
    "JM": ["\u7126\u7164"],
    "L": ["\u805a\u4e59\u70ef"],
    "V": ["\u805a\u6c2f\u4e59\u70ef"],
    "PP": ["\u805a\u4e19\u70ef"],
    "EG": ["\u4e59\u4e8c\u9187"],
    "EB": ["\u82ef\u4e59\u70ef"],
    "PG": ["\u6db2\u5316\u77f3\u6cb9\u6c14"],
    "LH": ["\u751f\u732a"],
}


def dce_aliases_for(code, name=None):
    aliases = [code.upper()] if code else []
    aliases.extend(DCE_PRODUCT_ALIASES.get((code or "").upper(), []))
    if name:
        aliases.append(str(name))
    return [item for item in aliases if item]


def row_matches_alias(row, aliases):
    text = row_text(row)
    return any(alias and (str(alias).upper() in text or str(alias) in str(row)) for alias in aliases)


def dce_mirror_request(path, params=None, data=None, timeout=20):
    url = f"http://www.dlspjys.cn/publicweb/quotesdata/{path}"
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data else None
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
        "Accept": "*/*",
        "Referer": "http://www.dlspjys.cn/publicweb/quotesdata/index.html",
    }
    if encoded:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=encoded, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get("content-type") or ""


def is_exchange_challenge_html(text):
    lowered = (text or "").lower()
    return (
        "<!doctype html" in lowered
        or "<html" in lowered
    ) and (
        "$_ts" in text
        or "document.createElement" in text
        or "content=\"0;" in text
        or "precondition" in lowered
    )


def fetch_dce_warehouse_mirror(snapshot, normalized):
    code = (normalized.get("product_code") or "").upper()
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    aliases = dce_aliases_for(code, normalized.get("input"))
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        params = {
            "wbillWeeklyQuotes.variety": "all",
            "year": candidate_date[:4],
            "month": str(int(candidate_date[4:6]) - 1),
            "day": candidate_date[6:],
        }
        try:
            import pandas as pd
            from io import StringIO

            body, _ = dce_mirror_request("wbillWeeklyQuotes.html", params=params)
            html = body.decode("utf-8", errors="replace")
            if is_exchange_challenge_html(html):
                last_error = "blocked_by_exchange_waf: HTML challenge page returned"
                continue
            frames = pd.read_html(StringIO(html))
            if not frames:
                last_error = "no tables returned"
                continue
            records = frame_records(frames[0])
            matched = [row for row in records if row_matches_alias(row, aliases)]
            if matched:
                return {
                    "source": "DCE.mirror.dlspjys.wbillWeeklyQuotes",
                    "date": iso_date(candidate_date),
                    "matched_rows": {"rows": matched[:40]},
                }, None
            last_error = "no matching rows returned"
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "no rows returned"


def fetch_dce_position_mirror(snapshot, normalized):
    code = (normalized.get("product_code") or "").upper()
    lower = code.lower()
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        payload = {
            "memberDealPosiQuotes.variety": lower,
            "memberDealPosiQuotes.trade_type": "0",
            "contract.contract_id": "all",
            "contract.variety_id": lower,
            "year": candidate_date[:4],
            "month": str(int(candidate_date[4:6]) - 1),
            "day": candidate_date[6:],
            "batchExportFlag": "batch",
        }
        try:
            import pandas as pd
            import zipfile
            from io import BytesIO

            body, _ = dce_mirror_request("exportMemberDealPosiQuotesBatchData.html", data=payload, timeout=30)
            if not zipfile.is_zipfile(BytesIO(body)):
                sample = body[:500].decode("utf-8", errors="replace")
                if is_exchange_challenge_html(sample):
                    last_error = "blocked_by_exchange_waf: HTML challenge page returned"
                    continue
                last_error = "response is not a zip file"
                continue
            with zipfile.ZipFile(BytesIO(body), mode="r") as archive:
                matched = []
                for member in archive.namelist():
                    try:
                        file_name = member.encode("cp437").decode("gbk")
                    except Exception:
                        file_name = member
                    if not file_name.startswith(candidate_date):
                        continue
                    symbol = file_name.split("_")[1].upper() if "_" in file_name else ""
                    if not symbol.startswith(code):
                        continue
                    try:
                        data = pd.read_table(archive.open(member), header=None, sep="\t")
                    except UnicodeDecodeError:
                        data = pd.read_table(archive.open(member), header=None, sep=r"\s+", encoding="gb2312", skiprows=3)
                    if data.empty:
                        continue
                    starts = [idx for idx, value in enumerate(data.iloc[:, 0].astype(str)) if value.startswith("\u540d\u6b21")]
                    ends = [
                        idx
                        for idx, value in enumerate(data.iloc[:, 0].astype(str))
                        if re.search(r"(?:\u603b\u8ba1|\u5408\u8ba1)", value)
                    ]
                    if len(starts) < 3 or len(ends) < 3:
                        continue
                    def cell(row_index, col_index):
                        if row_index >= len(data.index) or col_index >= len(data.columns):
                            return None
                        value = data.iat[row_index, col_index]
                        try:
                            if pd.isna(value):
                                return None
                        except Exception:
                            pass
                        return value

                    part_rows = []
                    for offset in range(20):
                        indices = [starts[0] + 1 + offset, starts[1] + 1 + offset, starts[2] + 1 + offset]
                        if any(index >= len(data.index) or index >= ends[i] for i, index in enumerate(indices)):
                            break
                        part_rows.append(
                            {
                                "rank": offset + 1,
                                "vol_party_name": cell(indices[0], 2),
                                "vol": as_float(cell(indices[0], 3)),
                                "vol_chg": as_float(cell(indices[0], 5)),
                                "long_party_name": cell(indices[1], 2),
                                "long_open_interest": as_float(cell(indices[1], 3)),
                                "long_open_interest_chg": as_float(cell(indices[1], 5)),
                                "short_party_name": cell(indices[2], 2),
                                "short_open_interest": as_float(cell(indices[2], 3)),
                                "short_open_interest_chg": as_float(cell(indices[2], 5)),
                                "symbol": symbol,
                                "var": code,
                            }
                        )
                    matched.extend(part_rows)
                if matched:
                    return {
                        "source": "DCE.mirror.dlspjys.exportMemberDealPosiQuotesBatchData",
                        "date": iso_date(candidate_date),
                        "matched": {"rows": summarize_position_records(matched[:80])},
                    }, None
            last_error = "no matching rows returned"
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "no rows returned"


def clean_exchange_text(value):
    if value is None:
        return None
    text = str(value)
    if "$$" in text:
        text = text.split("$$", 1)[0]
    return text.strip()


def fetch_shfe_warehouse_direct(snapshot, normalized):
    code = (normalized.get("product_code") or "").upper()
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        url = f"https://www.shfe.com.cn/data/tradedata/future/dailydata/{candidate_date}dailystock.dat"
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
                    "Accept": "application/json,*/*",
                    "Referer": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/",
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            records = []
            for row in payload.get("o_cursor") or []:
                var_name = clean_exchange_text(row.get("VARNAME"))
                product_code = str(row.get("VARID") or row.get("VARSORT") or row.get("INSTRUMENTID") or "").upper()
                if code and product_code != code:
                    continue
                records.append(
                    {
                        "product": var_name,
                        "product_code": product_code or code,
                        "region": clean_exchange_text(row.get("REGNAME")),
                        "warehouse": clean_exchange_text(row.get("WHABBRNAME")),
                        "receipt": as_float(row.get("WRTWGHTS")),
                        "receipt_chg": as_float(row.get("WRTCHANGE")),
                        "raw": row,
                    }
                )
            if records:
                return {
                    "source": "SHFE.direct.www.dailydata.dailystock",
                    "date": iso_date(candidate_date),
                    "matched_rows": {"rows": records[:80]},
                }, None
            last_error = "no matching rows returned"
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                last_error = "HTTP 404"
            else:
                last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "no rows returned"


def fetch_shfe_position_direct(snapshot, normalized):
    code = (normalized.get("product_code") or "").upper()
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        url = f"https://www.shfe.com.cn/data/tradedata/future/dailydata/pm{candidate_date}.dat"
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
                    "Accept": "application/json,*/*",
                    "Referer": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/",
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            matched = []
            for row in payload.get("o_cursor") or []:
                instrument = str(row.get("INSTRUMENTID") or "").strip()
                instrument_upper = instrument.upper()
                product_code = code if code and instrument_upper.startswith(code) else re.sub(r"[^A-Za-z].*$", "", instrument).upper()
                if code and not instrument_upper.startswith(code):
                    continue
                matched.append(
                    {
                        "contract": instrument,
                        "product": clean_exchange_text(row.get("PRODUCTNAME")),
                        "rank": row.get("RANK"),
                        "volume_member": clean_exchange_text(row.get("PARTICIPANTABBR1")),
                        "volume": as_float(row.get("CJ1")),
                        "volume_chg": as_float(row.get("CJ1_CHG")),
                        "long_member": clean_exchange_text(row.get("PARTICIPANTABBR2")),
                        "long_open_interest": as_float(row.get("CJ2")),
                        "long_open_interest_chg": as_float(row.get("CJ2_CHG")),
                        "short_member": clean_exchange_text(row.get("PARTICIPANTABBR3")),
                        "short_open_interest": as_float(row.get("CJ3")),
                        "short_open_interest_chg": as_float(row.get("CJ3_CHG")),
                        "raw": row,
                    }
                )
            if matched:
                rank_rows = [row for row in matched if isinstance(row.get("rank"), int) and row.get("rank") > 0]
                aggregate_rows = [row for row in matched if not (isinstance(row.get("rank"), int) and row.get("rank") > 0)]
                return {
                    "source": "SHFE.direct.www.dailydata.pm",
                    "date": iso_date(candidate_date),
                    "matched": {
                        "aggregate_rows": aggregate_rows[:5],
                        "rows": summarize_position_records(rank_rows[:80] or matched[:80]),
                    },
                }, None
            last_error = "no matching rows returned"
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                last_error = "HTTP 404"
            else:
                last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "no rows returned"


def gfex_post(path, data, timeout=20):
    url = f"http://www.gfex.com.cn/u/{path}"
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "http://www.gfex.com.cn/gfex/rcjccpm/hqsj_tjsj.shtml",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def fetch_gfex_warehouse_direct(snapshot, normalized):
    code = (normalized.get("product_code") or "").upper()
    lower = code.lower()
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        try:
            payload = gfex_post("interfacesWebTdWbillWeeklyQuotes/loadList", {"gen_date": candidate_date})
            rows = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                last_error = "response data is not a list"
                continue
            matched = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_variety = str(row.get("varietyOrder") or "").upper()
                if lower and row_variety != lower.upper():
                    continue
                matched.append(
                    {
                        "product": clean_exchange_text(row.get("variety")),
                        "product_code": code,
                        "warehouse_code": clean_exchange_text(row.get("whCodeOrder")),
                        "warehouse": clean_exchange_text(row.get("whAbbr")),
                        "receipt": as_float(row.get("wbillQty")),
                        "receipt_chg": as_float(row.get("diff")),
                        "registered": as_float(row.get("regWbillQty")),
                        "cancelled": as_float(row.get("logoutWbillQty")),
                        "previous_receipt": as_float(row.get("lastWbillQty")),
                        "brand": clean_exchange_text(row.get("trademarkName")),
                        "raw": row,
                    }
                )
            if matched:
                return {
                    "source": "GFEX.direct.interfacesWebTdWbillWeeklyQuotes.loadList",
                    "date": iso_date(candidate_date),
                    "matched_rows": {"rows": matched[:80]},
                }, None
            last_error = "no matching rows returned"
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "no rows returned"


def fetch_gfex_position_direct(snapshot, normalized):
    code = (normalized.get("product_code") or "").upper()
    lower = code.lower()
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        try:
            contracts_payload = gfex_post(
                "interfacesWebTiMemberDealPosiQuotes/loadListContract_id",
                {"variety": lower, "trade_date": candidate_date},
            )
            contracts = contracts_payload.get("data") if isinstance(contracts_payload, dict) else None
            if not isinstance(contracts, list) or not contracts:
                last_error = "no contracts returned"
                continue
            exact_contract = str((snapshot.get("quote") or {}).get("contract") or "").lower()
            contract_id = next((item for item in contracts if exact_contract and str(item).lower() in exact_contract), None)
            if not contract_id:
                contract_id = contracts[0]

            parts = {}
            labels = {
                "1": ("volume_member", "volume", "volume_chg"),
                "2": ("long_member", "long_open_interest", "long_open_interest_chg"),
                "3": ("short_member", "short_open_interest", "short_open_interest_chg"),
            }
            for data_type in ("1", "2", "3"):
                payload = gfex_post(
                    "interfacesWebTiMemberDealPosiQuotes/loadList",
                    {
                        "trade_date": candidate_date,
                        "trade_type": "0",
                        "variety": lower,
                        "contract_id": contract_id,
                        "data_type": data_type,
                    },
                )
                rows = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(rows, list) or not rows:
                    continue
                member_key, qty_key, chg_key = labels[data_type]
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    rank = int(as_float(row.get("contractId")) or 0)
                    if rank <= 0:
                        continue
                    part = parts.setdefault(
                        rank,
                        {
                            "rank": rank,
                            "contract": contract_id,
                            "var": code,
                        },
                    )
                    part[member_key] = clean_exchange_text(row.get("abbr"))
                    part[qty_key] = as_float(row.get("todayQty"))
                    part[chg_key] = as_float(row.get("qtySub"))
            matched = [parts[key] for key in sorted(parts)]
            if matched:
                return {
                    "source": "GFEX.direct.interfacesWebTiMemberDealPosiQuotes.loadList",
                    "date": iso_date(candidate_date),
                    "contract": contract_id,
                    "available_contracts": contracts,
                    "matched": {"rows": summarize_position_records(matched[:80])},
                }, None
            last_error = "no ranking rows returned"
        except Exception as exc:
            last_error = str(exc)
    return None, last_error or "no rows returned"


MANUAL_KIND_ALIASES = {
    "spot_basis": ("basis", "spot_basis", "基差", "现货"),
    "warehouse_receipt": ("warehouse", "warehouse_receipt", "仓单", "注册仓单"),
    "position_rank": ("position", "position_rank", "holding", "rank", "席位", "持仓", "排名"),
}


def manual_data_dirs():
    dirs = []
    raw = os.getenv("CHINA_FUTURES_MANUAL_DATA_DIR")
    if raw:
        dirs.extend(Path(item) for item in raw.split(os.pathsep) if item)
    dirs.append(Path.cwd() / "manual-data")
    dirs.append(Path(__file__).resolve().parents[1] / "manual-data")
    out = []
    seen = set()
    for item in dirs:
        try:
            resolved = item.expanduser().resolve()
        except Exception:
            resolved = item
        if str(resolved) not in seen:
            seen.add(str(resolved))
            out.append(resolved)
    return out


def read_manual_records(path):
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if isinstance(data.get("rows"), list):
                return data["rows"]
            if isinstance(data.get("data"), list):
                return data["data"]
            return [data]
        return data if isinstance(data, list) else []
    if suffix in (".csv", ".xls", ".xlsx"):
        try:
            import pandas as pd
        except Exception:
            return []
        if suffix == ".csv":
            last_error = None
            for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
                try:
                    frame = pd.read_csv(path, encoding=encoding)
                    break
                except UnicodeDecodeError as exc:
                    last_error = exc
            else:
                if last_error:
                    raise last_error
                frame = pd.read_csv(path)
        else:
            sheets = pd.read_excel(path, sheet_name=None)
            if isinstance(sheets, dict):
                frames = [item for item in sheets.values() if item is not None and not item.empty]
                frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            else:
                frame = sheets
        return frame.where(frame.notna(), None).to_dict("records")
    return []


def find_manual_records(snapshot, normalized, kind):
    code = (normalized.get("product_code") or normalized.get("ak_symbol") or "").upper()
    name = normalized.get("input")
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    date_tokens = {analysis_date, analysis_date.replace("-", "")}
    effective_date = (snapshot.get("metadata") or {}).get("effective_market_date")
    if effective_date:
        date_tokens.update({effective_date, effective_date.replace("-", "")})
    for candidate in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        date_tokens.update({candidate, iso_date(candidate)})
    kind_tokens = MANUAL_KIND_ALIASES.get(kind, (kind,))
    candidates = []
    for directory in manual_data_dirs():
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in (".json", ".csv", ".xls", ".xlsx"):
                continue
            filename = path.name.lower()
            if not any(token.lower() in filename for token in date_tokens):
                continue
            if code and code.lower() not in filename and name and str(name).lower() not in filename:
                continue
            if not any(str(token).lower() in filename for token in kind_tokens):
                continue
            candidates.append(path)
    for path in sorted(candidates):
        try:
            records = read_manual_records(path)
        except Exception:
            continue
        matched = filter_rows_for_product(records, code, name) or records
        if matched:
            return path, matched
    return None, []


def fetch_manual_supplements(snapshot, normalized):
    fundamentals = snapshot["fundamentals"]
    notes = []
    if not fundamentals.get("spot_basis"):
        path, records = find_manual_records(snapshot, normalized, "spot_basis")
        if records:
            row = records[-1]
            fundamentals["spot_basis"] = {
                "source": f"manual_file:{path.name}",
                "date": first_existing(row, ["date", "日期"]) or (snapshot.get("metadata") or {}).get("analysis_date"),
                "spot": as_float(first_existing(row, ["spot", "spot_price", "现货", "现货价格", "现货价"])),
                "futures": as_float(first_existing(row, ["futures", "futures_price", "期货", "期货价格", "主力合约价格"])),
                "basis": as_float(first_existing(row, ["basis", "基差"])),
                "raw": row,
            }
            notes.append("spot_basis: ok via manual file")
    if not fundamentals.get("warehouse_receipt"):
        path, records = find_manual_records(snapshot, normalized, "warehouse_receipt")
        if records:
            fundamentals["warehouse_receipt"] = {
                "source": f"manual_file:{path.name}",
                "date": first_existing(records[-1], ["date", "日期"]) or (snapshot.get("metadata") or {}).get("analysis_date"),
                "matched_rows": {"rows": records[:80]},
            }
            notes.append("warehouse_receipt: ok via manual file")
    if not fundamentals.get("position_rank"):
        path, records = find_manual_records(snapshot, normalized, "position_rank")
        if records:
            fundamentals["position_rank"] = {
                "source": f"manual_file:{path.name}",
                "date": first_existing(records[-1], ["date", "日期"]) or (snapshot.get("metadata") or {}).get("analysis_date"),
                "matched": {"rows": summarize_position_records(records[:80])},
            }
            notes.append("position_rank: ok via manual file")
    snapshot["data_source_status"]["manual_supplements"] = "; ".join(notes) if notes else "no matching manual files"


def extract_mcp_json(text):
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("{"):
        return json.loads(text)
    data_lines = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if data_lines:
        return json.loads("\n".join(data_lines))
    return None


def fetch_100ppi_html(date_yyyy_mm_dd):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    url = f"https://www.100ppi.com/sf/day-{date_yyyy_mm_dd}.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    html = ""
    for _ in range(2):
        request = urllib.request.Request(url, headers=headers)
        with opener.open(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
        match = re.search(r'var\s+_0x2\s*=\s*"([^"]+)"', html)
        if not match:
            break
        opener.addheaders = [("Cookie", "HW_CHECK=" + match.group(1))]
    return html


def parse_100ppi_basis(html, code):
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return None
    names = BASIS_PRODUCT_NAMES.get((code or "").upper(), [])
    if not names:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True).replace("\xa0", " ") for cell in row.find_all(["td", "th"])]
        cells = [re.sub(r"\s+", " ", cell).strip() for cell in cells if cell is not None]
        if len(cells) < 9 or cells[0] not in names:
            continue
        return {
            "product": cells[0],
            "spot": as_float(cells[1] if len(cells) > 1 else None),
            "near_symbol": cells[2] if len(cells) > 2 else None,
            "near_price": as_float(cells[3] if len(cells) > 3 else None),
            "near_basis": as_float(cells[5] if len(cells) > 5 else None),
            "near_basis_pct": cells[6] if len(cells) > 6 else None,
            "dom_symbol": cells[7] if len(cells) > 7 else None,
            "dom_price": as_float(cells[8] if len(cells) > 8 else None),
            "dom_basis": as_float(cells[10] if len(cells) > 10 else None),
            "dom_basis_pct": cells[11] if len(cells) > 11 else None,
            "raw": cells,
        }
    return None


def fetch_spot_basis_with_100ppi(snapshot, normalized):
    code = normalized.get("ak_symbol")
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    last_error = None
    for compact in snapshot_date_candidates(snapshot, days=basis_lookback_days()):
        yyyy_mm_dd = iso_date(compact)
        try:
            html = fetch_100ppi_html(yyyy_mm_dd)
            row = parse_100ppi_basis(html, code)
        except Exception as exc:
            last_error = str(exc)
            continue
        if row:
            return {
                "source": "100ppi.direct",
                "date": yyyy_mm_dd,
                "spot": row.get("spot"),
                "futures": row.get("dom_price") or row.get("near_price"),
                "basis": row.get("dom_basis") if row.get("dom_basis") is not None else row.get("near_basis"),
                "raw": row,
            }, None
    return None, last_error or "no matching product rows returned"


def fetch_spot_basis_with_99qh(snapshot, normalized):
    if os.getenv("CHINA_FUTURES_SKIP_99QH_BASIS"):
        return None, "skipped: CHINA_FUTURES_SKIP_99QH_BASIS is set"
    code = (normalized.get("ak_symbol") or "").upper()
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    names = BASIS_PRODUCT_NAMES.get(code, []) or [normalized.get("input")]
    try:
        import akshare.spot.spot_price_qh as qh
        import requests
    except Exception as exc:
        return None, f"dependency unavailable: {exc}"
    try:
        products = qh.__get_item_of_spot_price_qh()
        symbol_map = dict(zip(products["name"], products["productId"]))
    except Exception as exc:
        return None, f"99qh product table unavailable: {exc}"
    product_id = None
    product_name = None
    for name in names:
        if name in symbol_map:
            product_id = symbol_map[name]
            product_name = name
            break
    if not product_id:
        return None, "99qh no matching product"
    try:
        token = qh.__get_token_of_spot_price_qh()
        response = requests.get(
            "https://centerapi.fx168api.com/app/qh/api/spot/trend",
            params={
                "productId": product_id,
                "pageNo": "1",
                "pageSize": "50000",
                "startDate": "",
                "endDate": "2050-01-01",
                "appCategory": "web",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "_pcc": token,
                "Origin": "https://www.99qh.com",
                "Referer": "https://www.99qh.com",
            },
            timeout=8,
        )
        data = response.json()
    except Exception as exc:
        return None, f"99qh request failed: {exc}"
    if data.get("code") == 401:
        return None, f"99qh HTTP 401 / {data.get('message') or data.get('data') or 'permission denied'}"
    items = ((data.get("data") or {}).get("list") or []) if isinstance(data.get("data"), dict) else []
    candidates = []
    for item in items:
        date_text = normalize_date_text(item.get("date"))
        if not date_text or date_text > analysis_date:
            continue
        spot = as_float(item.get("sp"))
        futures = as_float(item.get("fp"))
        if spot is None and futures is None:
            continue
        candidates.append((date_text, item, spot, futures))
    if not candidates:
        return None, "99qh no rows on or before analysis date"
    date_text, raw, spot, futures = sorted(candidates, key=lambda item: item[0])[-1]
    return {
        "source": "99qh.spot_price_qh",
        "date": date_text,
        "product": product_name,
        "spot": spot,
        "futures": futures,
        "basis": (spot - futures) if spot is not None and futures is not None else None,
        "raw": raw,
    }, None


def extract_next_data(html):
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.S)
    if not match:
        return None
    return json.loads(match.group(1))


def iter_nested_values(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_nested_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_nested_values(value)


def fetch_smm_spot_basis(snapshot, normalized):
    code = (normalized.get("ak_symbol") or "").upper()
    config = SMM_SPOT_SOURCES.get(code)
    if not config:
        return None, f"SMM spot source not configured for {code or 'unknown'}"
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    url = config["url"]
    preferred_names = config.get("names") or []
    preferred_product_ids = {str(item) for item in (config.get("product_ids") or [])}
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read()
            encoding = (response.headers.get("Content-Encoding") or "").lower()
            if "gzip" in encoding:
                body = gzip.decompress(body)
            html = body.decode("utf-8", errors="replace")
        next_data = extract_next_data(html)
    except Exception as exc:
        return None, f"SMM request failed: {exc}"
    if not next_data:
        return None, "SMM Next.js data not found"

    candidates = []
    for item in iter_nested_values(next_data):
        name = str(item.get("product_name") or item.get("price_declaration") or "")
        product_id = str(item.get("product_id") or "")
        if preferred_product_ids and product_id not in preferred_product_ids:
            continue
        if not preferred_product_ids and preferred_names and not any(preferred in name for preferred in preferred_names):
            continue
        if item.get("renew_date") and item.get("average") is not None:
            date_text = normalize_date_text(item.get("renew_date"))
            if date_text and date_text <= analysis_date:
                candidates.append((date_text, as_float(item.get("average")), item))
        for detail in item.get("price_detail") or []:
            detail_name = str(detail.get("product_name") or detail.get("price_declaration") or name)
            detail_product_id = str(detail.get("product_id") or product_id)
            if preferred_product_ids and detail_product_id not in preferred_product_ids:
                continue
            if not preferred_product_ids and preferred_names and not any(preferred in detail_name for preferred in preferred_names):
                continue
            date_text = normalize_date_text(detail.get("renew_date"))
            if date_text and date_text <= analysis_date and detail.get("average") is not None:
                candidates.append((date_text, as_float(detail.get("average")), detail))
    candidates = [(date_text, price, raw) for date_text, price, raw in candidates if price is not None]
    if not candidates:
        return None, f"SMM no {code} spot rows on or before analysis date"
    spot_date, spot_price, raw_spot = sorted(candidates, key=lambda item: item[0])[-1]

    futures_price = as_float((snapshot.get("quote") or {}).get("last"))
    futures_source = (snapshot.get("quote") or {}).get("source")
    if futures_price is None:
        latest_bar, _ = latest_bar_values(snapshot)
        if latest_bar:
            futures_price = as_float(first_existing(latest_bar, ["close", "收盘", "收盘价"]))
            futures_source = "daily_bars.close"
    if futures_price is None:
        return None, "SMM spot found but futures price unavailable for basis calculation"

    return {
        "source": f"SMM.h5.{code}.spot + futures",
        "date": spot_date,
        "spot": spot_price,
        "futures": futures_price,
        "basis": spot_price - futures_price,
        "unit": "元/吨",
        "spot_source_url": url,
        "futures_source": futures_source,
        "raw": raw_spot,
    }, None


def fetch_czce_excel(date_compact, file_name):
    try:
        import pandas as pd
        import requests
        from io import BytesIO
    except Exception as exc:
        return None, f"dependency unavailable: {exc}"
    year = str(date_compact)[:4]
    url = f"http://www.czce.com.cn/cn/DFSStaticFiles/Future/{year}/{date_compact}/{file_name}"
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if response.status_code != 200:
            return None, f"HTTP {response.status_code}"
        head_text = response.content[:1000].decode("utf-8", errors="ignore")
        if "当日无数据" in head_text:
            return None, "no data for date"
        return pd.read_excel(BytesIO(response.content), header=None), None
    except Exception as exc:
        return None, str(exc)


def czce_section_rows(df, code):
    if df is None or df.empty:
        return []
    code = (code or "").upper()
    start = None
    for idx, value in df.iloc[:, 0].items():
        text = str(value)
        if "品种：" in text and code in text.upper():
            start = idx
            break
    if start is None:
        return []
    end = len(df)
    for idx in range(start + 1, len(df)):
        text = str(df.iloc[idx, 0])
        if "品种：" in text:
            end = idx
            break
    rows = []
    for _, row in df.iloc[start + 1 : end].iterrows():
        values = [None if str(item) == "nan" else item for item in row.tolist()]
        if not any(item is not None for item in values):
            continue
        rows.append(values)
    return rows


def fetch_czce_warehouse_direct(snapshot, normalized):
    code = normalized.get("ak_symbol")
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        df, err = fetch_czce_excel(candidate_date, "FutureDataWhsheet.xls")
        last_error = err
        rows = czce_section_rows(df, code)
        if rows:
            matched = []
            for row in rows[:80]:
                if str(row[0]) == "仓库编号":
                    continue
                matched.append(
                    {
                        "warehouse_code": row[0] if len(row) > 0 else None,
                        "warehouse": row[1] if len(row) > 1 else None,
                        "year": row[2] if len(row) > 2 else None,
                        "grade": row[3] if len(row) > 3 else None,
                        "brand": row[4] if len(row) > 4 else None,
                        "receipt": as_float(row[5] if len(row) > 5 else None),
                        "change": as_float(row[6] if len(row) > 6 else None),
                        "forecast": as_float(row[7] if len(row) > 7 else None),
                        "premium_discount": as_float(row[8] if len(row) > 8 else None),
                    }
                )
            return {
                "source": "CZCE.direct.FutureDataWhsheet.xls",
                "date": iso_date(candidate_date),
                "matched_rows": {"rows": matched},
            }, None
    return None, last_error or "no matching rows returned"


def fetch_czce_position_direct(snapshot, normalized):
    code = normalized.get("ak_symbol")
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    last_error = None
    for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
        df, err = fetch_czce_excel(candidate_date, "FutureDataHolding.xls")
        last_error = err
        rows = czce_section_rows(df, code)
        clean = []
        for row in rows:
            if len(row) < 10 or str(row[0]) in {"名次", "合计"}:
                continue
            rank = as_float(row[0])
            if rank is None:
                continue
            clean.append(
                {
                    "rank": int(rank),
                    "vol_party_name": row[1],
                    "vol": as_float(row[2]),
                    "vol_chg": as_float(row[3]),
                    "long_party_name": row[4],
                    "long_open_interest": as_float(row[5]),
                    "long_open_interest_chg": as_float(row[6]),
                    "short_party_name": row[7],
                    "short_open_interest": as_float(row[8]),
                    "short_open_interest_chg": as_float(row[9]),
                    "var": code,
                }
            )
        if clean:
            return {
                "source": "CZCE.direct.FutureDataHolding.xls",
                "date": iso_date(candidate_date),
                "matched": {"rows": summarize_position_records(clean)},
            }, None
    return None, last_error or "no matching rows returned"


def fetch_with_tushare(snapshot, normalized):
    if os.getenv("CHINA_FUTURES_SKIP_TUSHARE"):
        snapshot["data_source_status"]["tushare"] = "skipped: CHINA_FUTURES_SKIP_TUSHARE is set"
        return
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        snapshot["data_source_status"]["tushare"] = "skipped: TUSHARE_TOKEN not set"
        return
    try:
        import tushare as ts
    except Exception as exc:
        snapshot["data_source_status"]["tushare"] = f"skipped: tushare not installed ({exc})"
        return

    code = normalized.get("ak_symbol")
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    fundamentals = snapshot["fundamentals"]
    notes = []
    errors = []

    try:
        pro = ts.pro_api(token)
    except Exception as exc:
        snapshot["data_source_status"]["tushare"] = f"failed: {exc}"
        return

    if code and not fundamentals.get("warehouse_receipt"):
        last_err = None
        for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
            try:
                data = pro.fut_wsr(trade_date=candidate_date, symbol=code)
                records = frame_records(data)
            except Exception as exc:
                last_err = str(exc)
                records = []
            matched = filter_rows_for_product(records, code, normalized.get("input")) or records
            if matched:
                fundamentals["warehouse_receipt"] = {
                    "source": "TusharePro.fut_wsr",
                    "date": iso_date(candidate_date),
                    "matched_rows": {"rows": matched[:80]},
                }
                notes.append("warehouse_receipt: ok")
                break
        if not fundamentals.get("warehouse_receipt"):
            errors.append(f"warehouse_receipt: {last_err or 'no rows returned'}")

    if code and not fundamentals.get("position_rank"):
        last_err = None
        for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
            try:
                data = pro.fut_holding(trade_date=candidate_date, symbol=code)
                records = frame_records(data)
            except Exception as exc:
                last_err = str(exc)
                records = []
            matched = filter_rows_for_product(records, code, normalized.get("input")) or records
            if matched:
                fundamentals["position_rank"] = {
                    "source": "TusharePro.fut_holding",
                    "date": iso_date(candidate_date),
                    "matched": {"rows": summarize_position_records(matched[:80])},
                }
                notes.append("position_rank: ok")
                break
        if not fundamentals.get("position_rank"):
            errors.append(f"position_rank: {last_err or 'no rows returned'}")

    if errors:
        for item in errors:
            field = item.split(":", 1)[0]
            snapshot.setdefault("supplement_errors", []).append(
                {
                    "field": field,
                    "source": "TusharePro",
                    "category": classify_fetch_error(item),
                    "message": item,
                }
            )
    snapshot["data_source_status"]["tushare"] = "; ".join(notes + errors) if (notes or errors) else "no gaps requested"


class Jin10McpClient:
    def __init__(self, token, protocol_version="2025-11-25", timeout=None, retries=None):
        self.token = token
        self.protocol_version = protocol_version
        self.session_id = None
        self.url = "https://mcp.jin10.com/mcp"
        self.next_id = 1
        self.timeout = int(timeout or os.getenv("JIN10_MCP_TIMEOUT_SECONDS") or 8)
        self.retries = int(retries or os.getenv("JIN10_MCP_RETRIES") or 2)

    def call_rpc(self, method, params=None, expect_response=True):
        attempts = max(1, self.retries)
        last_error = None
        for attempt in range(1, attempts + 1):
            payload = {"jsonrpc": "2.0", "method": method}
            if expect_response:
                payload["id"] = self.next_id
            if params is not None:
                payload["params"] = params
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {self.token}",
                "MCP-Protocol-Version": self.protocol_version,
            }
            if self.session_id:
                headers["Mcp-Session-Id"] = self.session_id
            request = urllib.request.Request(
                self.url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    if not self.session_id:
                        self.session_id = response.headers.get("Mcp-Session-Id")
                    body = response.read().decode("utf-8", errors="replace")
                if expect_response:
                    self.next_id += 1
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                time.sleep(min(2 * attempt, 5))
        else:
            raise RuntimeError(last_error or "Jin10 MCP request failed")
        if not expect_response:
            return None
        result = extract_mcp_json(body)
        if result and result.get("error"):
            raise RuntimeError(result["error"])
        return result

    def initialize(self):
        self.call_rpc(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "analyze-china-futures", "version": "1.0.0"},
            },
        )
        self.call_rpc("notifications/initialized", {}, expect_response=False)

    def tool(self, name, arguments):
        response = self.call_rpc("tools/call", {"name": name, "arguments": arguments})
        result = (response or {}).get("result") or {}
        if result.get("isError"):
            raise RuntimeError(result)
        return result.get("structuredContent") or {}

    def list_tools(self):
        response = self.call_rpc("tools/list", {})
        return (response or {}).get("result") or {}

    def list_resources(self):
        response = self.call_rpc("resources/list", {})
        return (response or {}).get("result") or {}


def jin10_item_text(item):
    if not isinstance(item, dict):
        return ""
    parts = []
    for key in ("title", "content", "introduction", "summary"):
        value = item.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts)


def is_relevant_news_item(item, keywords):
    text = jin10_item_text(item)
    if not text:
        return False
    return any(keyword and keyword in text for keyword in keywords)


def add_jin10_items(target, raw_items, source, keyword=None, keywords=None, require_relevance=False, max_add=None):
    keywords = keywords or []
    seen = {
        str(item.get("id") or item.get("url") or jin10_item_text(item)[:120])
        for item in target
        if isinstance(item, dict)
    }
    added = 0
    for raw in raw_items or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["source"] = source
        if keyword:
            item["keyword"] = keyword
        if require_relevance and not is_relevant_news_item(item, keywords):
            continue
        key = str(item.get("id") or item.get("url") or jin10_item_text(item)[:120])
        if not key or key in seen:
            continue
        seen.add(key)
        target.append(item)
        added += 1
        if max_add is not None and added >= max_add:
            break
    return added


def jin10_keywords_for(normalized):
    code = (normalized.get("product_code") or "").upper()
    return {
        "FG": ["\u73bb\u7483", "\u7eaf\u78b1"],
        "JM": ["\u7126\u7164", "\u7164\u70ad"],
        "J": ["\u7126\u70ad", "\u7164\u70ad"],
        "AO": ["\u6c27\u5316\u94dd", "\u94dd\u571f\u77ff"],
        "RB": ["\u87ba\u7eb9\u94a2", "\u94a2\u6750"],
        "HC": ["\u70ed\u5377", "\u94a2\u6750"],
        "CU": ["\u94dc", "\u6709\u8272"],
        "AL": ["\u94dd", "\u6709\u8272"],
        "I": ["\u94c1\u77ff\u77f3", "\u94c1\u77ff"],
    }.get(code, [normalized.get("input") or code])


def fetch_fundamentals_with_akshare(snapshot, normalized):
    try:
        import akshare as ak
    except Exception as exc:
        snapshot["data_source_status"]["akshare_fundamentals"] = f"unavailable: {exc}"
        return

    code = normalized.get("ak_symbol")
    name = normalized.get("input")
    exchange = normalized.get("exchange")
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    compact_date = analysis_date.replace("-", "")
    fundamentals = snapshot["fundamentals"]
    errors = []

    inventory, err = try_call(ak.futures_inventory_em, symbol=code)
    if err:
        inventory, err = try_call(ak.futures_inventory_em, symbol=name)
    if err:
        errors.append(f"inventory: {err}")
    else:
        records = frame_records(inventory)
        record = latest_record(records)
        if record:
            fundamentals["inventory"] = {
                "source": "AKShare.futures_inventory_em",
                "date": first_existing(record, ["日期", "date"]),
                "value": as_float(first_existing(record, ["库存", "inventory"])),
                "change": as_float(first_existing(record, ["增减", "change"])),
                "unit": "source_unit",
                "raw": record,
            }

    spot = None
    spot_date = None
    err = None
    if os.getenv("CHINA_FUTURES_SKIP_AKSHARE_BASIS"):
        err = "skipped: CHINA_FUTURES_SKIP_AKSHARE_BASIS is set"
    else:
        for candidate_date in snapshot_date_candidates(snapshot, days=basis_lookback_days()):
            spot, err = try_call(ak.futures_spot_price, date=candidate_date, vars_list=[code])
            if not err and frame_records(spot):
                spot_date = candidate_date
                break
            spot, err2 = try_call(ak.futures_spot_price_daily, start_day=candidate_date, end_day=candidate_date, vars_list=[code])
            err = err2 if err2 else err
            if not err and frame_records(spot):
                spot_date = candidate_date
                break
    records = frame_records(spot)
    if records:
        record = records[-1]
        fundamentals["spot_basis"] = {
            "source": "AKShare.futures_spot_price",
            "date": first_existing(record, ["日期", "date"]) or spot_date,
            "spot": as_float(first_existing(record, ["现货价格", "现货价", "spot_price"])),
            "futures": as_float(first_existing(record, ["主力合约价格", "期货价格", "futures_price"])),
            "basis": as_float(first_existing(record, ["基差", "basis"])),
            "raw": record,
        }
    elif err:
        errors.append(f"spot_basis: {err}")
    else:
        errors.append("spot_basis: no rows returned")

    if exchange == "CZCE" and not fundamentals.get("warehouse_receipt"):
        receipt = None
        receipt_date = None
        err = None
        for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
            receipt, err = try_call(ak.futures_czce_warehouse_receipt, date=candidate_date)
            if not err:
                receipt_date = candidate_date
                break
        if not err and receipt is not None:
            receipt_summary = {}
            if isinstance(receipt, dict):
                for key, value in receipt.items():
                    records = frame_records(value)
                    matched = [row for row in records if code in str(row).upper() or str(name) in str(row)]
                    if matched:
                        receipt_summary[str(key)] = matched[:10]
            else:
                records = frame_records(receipt)
                receipt_summary["rows"] = [row for row in records if code in str(row).upper() or str(name) in str(row)][:10]
            if receipt_summary:
                fundamentals["warehouse_receipt"] = {
                    "source": "AKShare.futures_czce_warehouse_receipt",
                    "date": receipt_date,
                    "matched_rows": receipt_summary,
                }
            else:
                errors.append("warehouse_receipt: no matching rows returned")
        elif err:
            errors.append(f"warehouse_receipt: {err}")

    if errors:
        snapshot["data_source_status"]["akshare_fundamentals"] = "; ".join(errors[:4])
    else:
        snapshot["data_source_status"]["akshare_fundamentals"] = "ok"


def fetch_gap_supplements(snapshot, normalized):
    """Supplement gaps with exchange/AKShare sources not covered by the base fetch."""
    try:
        import akshare as ak
    except Exception as exc:
        snapshot["data_source_status"]["gap_supplements"] = f"akshare unavailable: {exc}"
        return

    code = normalized.get("ak_symbol")
    name = normalized.get("input")
    exchange = normalized.get("exchange")
    analysis_date = (snapshot.get("metadata") or {}).get("analysis_date") or today_shanghai()
    fundamentals = snapshot["fundamentals"]
    notes = []
    supplement_errors = snapshot.setdefault("supplement_errors", [])

    def note_error(field, source, message):
        supplement_errors.append(
            {
                "field": field,
                "source": source,
                "category": classify_fetch_error(message),
                "message": str(message),
            }
        )

    def fetch_receipt_with_get_receipt():
        if not code or not hasattr(ak, "get_receipt"):
            return None, "AKShare.get_receipt unavailable"
        last_error = None
        for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
            data, err = try_call(
                ak.get_receipt,
                start_date=candidate_date,
                end_date=candidate_date,
                vars_list=[code],
            )
            last_error = err
            if err or data is None:
                continue
            rows = filter_rows_for_product(frame_records(data), code, name)
            if not rows:
                continue
            return {
                "source": "AKShare.get_receipt",
                "date": iso_date(candidate_date),
                "matched_rows": {"rows": rows[:20]},
            }, None
        return None, last_error or "no matching rows returned"

    if code and not fundamentals.get("inventory"):
        inventory_symbols = []
        for item in (code, code.lower(), name):
            if item and item not in inventory_symbols:
                inventory_symbols.append(item)
        last_err = None
        for symbol in inventory_symbols:
            inventory, err = try_call(ak.futures_inventory_em, symbol=symbol)
            last_err = err
            records = frame_records(inventory)
            if records:
                row = latest_record(records)
                fundamentals["inventory"] = {
                    "source": "AKShare.futures_inventory_em",
                    "date": first_existing(row, ["日期", "date"]),
                    "value": as_float(first_existing(row, ["库存", "inventory"])),
                    "change": as_float(first_existing(row, ["增减", "change"])),
                    "unit": "source_unit",
                    "raw": row,
                }
                notes.append("inventory: ok")
                break
        if not fundamentals.get("inventory"):
            notes.append(f"inventory: {last_err or 'no rows returned'}")

    if code and not fundamentals.get("spot_basis"):
        last_err = None
        if os.getenv("CHINA_FUTURES_SKIP_AKSHARE_BASIS"):
            last_err = "skipped: CHINA_FUTURES_SKIP_AKSHARE_BASIS is set"
        else:
            for candidate_date in snapshot_date_candidates(snapshot, days=basis_lookback_days()):
                spot, err = try_call(ak.futures_spot_price, date=candidate_date, vars_list=[code])
                if err or not frame_records(spot):
                    spot, err = try_call(
                        ak.futures_spot_price_daily,
                        start_day=candidate_date,
                        end_day=candidate_date,
                        vars_list=[code],
                    )
                last_err = err
                records = frame_records(spot)
                if records:
                    row = records[-1]
                    fundamentals["spot_basis"] = {
                        "source": "AKShare.futures_spot_price / 100ppi",
                        "date": first_existing(row, ["date"]) or iso_date(candidate_date),
                        "spot": as_float(first_existing(row, ["spot_price", "sp"])),
                        "futures": as_float(first_existing(row, ["dom_price", "near_price", "futures_price"])),
                        "basis": as_float(first_existing(row, ["dom_basis", "near_basis", "basis"])),
                        "raw": row,
                    }
                    notes.append("spot_basis: ok")
                    break
        if not fundamentals.get("spot_basis"):
            smm_basis, smm_err = fetch_smm_spot_basis(snapshot, normalized)
            if smm_basis:
                fundamentals["spot_basis"] = smm_basis
                notes.append("spot_basis: ok via SMM.h5")
            else:
                direct_basis, direct_err = fetch_spot_basis_with_100ppi(snapshot, normalized)
                if direct_basis:
                    fundamentals["spot_basis"] = direct_basis
                    notes.append("spot_basis: ok via 100ppi.direct")
                else:
                    qh_basis, qh_err = fetch_spot_basis_with_99qh(snapshot, normalized)
                    if qh_basis:
                        fundamentals["spot_basis"] = qh_basis
                        notes.append("spot_basis: ok via 99qh.spot_price_qh")
                    else:
                        msg = qh_err or direct_err or smm_err or last_err or "no rows returned"
                        source = "AKShare/SMM/100ppi/99qh" if qh_err else "AKShare/SMM/100ppi"
                        note_error("spot_basis", source, msg)
                        notes.append(f"spot_basis: {msg}")

    receipt_funcs = {
        "SHFE": "futures_shfe_warehouse_receipt",
        "DCE": "futures_dce_warehouse_receipt",
        "CZCE": "futures_czce_warehouse_receipt",
        "GFEX": "futures_gfex_warehouse_receipt",
    }
    if exchange == "SHFE" and not fundamentals.get("warehouse_receipt"):
        shfe_receipt, shfe_err = fetch_shfe_warehouse_direct(snapshot, normalized)
        if shfe_receipt:
            fundamentals["warehouse_receipt"] = shfe_receipt
            notes.append("warehouse_receipt: ok via SHFE.direct")
        else:
            note_error("warehouse_receipt", "SHFE.direct.www.dailydata.dailystock", shfe_err or "no matching rows returned")
    elif exchange == "GFEX" and not fundamentals.get("warehouse_receipt"):
        gfex_receipt, gfex_err = fetch_gfex_warehouse_direct(snapshot, normalized)
        if gfex_receipt:
            fundamentals["warehouse_receipt"] = gfex_receipt
            notes.append("warehouse_receipt: ok via GFEX.direct")
        else:
            note_error("warehouse_receipt", "GFEX.direct.wbillWeeklyQuotes", gfex_err or "no matching rows returned")

    receipt_func_name = receipt_funcs.get(exchange)
    if receipt_func_name and hasattr(ak, receipt_func_name) and not fundamentals.get("warehouse_receipt"):
        last_err = None
        for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
            receipt, err = try_call(getattr(ak, receipt_func_name), date=candidate_date)
            last_err = err
            if err or receipt is None:
                continue
            matched_by_key = {}
            if isinstance(receipt, dict):
                for key, value in receipt.items():
                    records = frame_records(value)
                    matched = filter_rows_for_product(records, code, name)
                    if matched:
                        matched_by_key[str(key)] = matched[:10]
            else:
                matched = filter_rows_for_product(frame_records(receipt), code, name)
                if matched:
                    matched_by_key["rows"] = matched[:10]
            if matched_by_key:
                fundamentals["warehouse_receipt"] = {
                    "source": f"AKShare.{receipt_func_name}",
                    "date": iso_date(candidate_date),
                    "matched_rows": matched_by_key,
                }
                notes.append("warehouse_receipt: ok")
                break
        if not fundamentals.get("warehouse_receipt"):
            general_receipt, general_err = fetch_receipt_with_get_receipt()
            if general_receipt:
                fundamentals["warehouse_receipt"] = general_receipt
                notes.append("warehouse_receipt: ok via AKShare.get_receipt")
            elif exchange == "SHFE":
                msg = general_err or last_err or "no matching rows returned"
                note_error("warehouse_receipt", f"AKShare.{receipt_func_name}/get_receipt", msg)
                notes.append(f"warehouse_receipt: {msg}")
            elif exchange == "DCE":
                dce_receipt, dce_err = fetch_dce_warehouse_mirror(snapshot, normalized)
                if dce_receipt:
                    fundamentals["warehouse_receipt"] = dce_receipt
                    notes.append("warehouse_receipt: ok via DCE.mirror")
                else:
                    msg = dce_err or general_err or last_err or "no matching rows returned"
                    note_error("warehouse_receipt", "DCE.mirror.dlspjys", msg)
                    notes.append(f"warehouse_receipt: {msg}")
            elif exchange == "CZCE":
                direct_receipt, direct_err = fetch_czce_warehouse_direct(snapshot, normalized)
                if direct_receipt:
                    fundamentals["warehouse_receipt"] = direct_receipt
                    notes.append("warehouse_receipt: ok via CZCE.direct")
                else:
                    msg = direct_err or general_err or last_err or "no matching rows returned"
                    note_error("warehouse_receipt", "CZCE.direct", msg)
                    notes.append(f"warehouse_receipt: {msg}")
            else:
                msg = general_err or last_err or "no matching rows returned"
                note_error("warehouse_receipt", f"AKShare.{receipt_func_name}/get_receipt", msg)
                notes.append(f"warehouse_receipt: {msg}")

    if code and not fundamentals.get("warehouse_receipt"):
        aggregate_receipt = warehouse_receipt_from_inventory(snapshot, normalized)
        if aggregate_receipt:
            fundamentals["warehouse_receipt"] = aggregate_receipt
            notes.append("warehouse_receipt: ok via AKShare.futures_inventory_em aggregate fallback")

    if code and not fundamentals.get("position_rank"):
        position_calls = []
        if exchange == "DCE":
            position_calls.extend([
                ("get_dce_rank_table", lambda d: ak.get_dce_rank_table(date=d, vars_list=[code])),
                ("futures_dce_position_rank", lambda d: ak.futures_dce_position_rank(date=d, vars_list=[code])),
            ])
        elif exchange == "CZCE":
            position_calls.append(("get_czce_rank_table", lambda d: ak.get_czce_rank_table(date=d)))
        elif exchange == "SHFE":
            shfe_position, shfe_position_err = fetch_shfe_position_direct(snapshot, normalized)
            if shfe_position:
                fundamentals["position_rank"] = shfe_position
                notes.append("position_rank: ok via SHFE.direct")
            elif os.getenv("CHINA_FUTURES_TRY_LEGACY_SHFE_RANK"):
                position_calls.append(("get_shfe_rank_table", lambda d: ak.get_shfe_rank_table(date=d, vars_list=[code])))
            else:
                note_error(
                    "position_rank",
                    "SHFE.direct.www.dailydata.pm",
                    shfe_position_err or "no rows returned",
                )
                note_error(
                    "position_rank",
                    "SHFE.legacy_rank_endpoint",
                    "skipped: set CHINA_FUTURES_TRY_LEGACY_SHFE_RANK=1 to try old AKShare/SHFE rank path",
                )
        elif exchange == "GFEX":
            gfex_position, gfex_position_err = fetch_gfex_position_direct(snapshot, normalized)
            if gfex_position:
                fundamentals["position_rank"] = gfex_position
                notes.append("position_rank: ok via GFEX.direct")
            else:
                note_error("position_rank", "GFEX.direct.memberDealPosiQuotes", gfex_position_err or "no rows returned")
                position_calls.append(("futures_gfex_position_rank", lambda d: ak.futures_gfex_position_rank(date=d, vars_list=[code])))
        if exchange != "SHFE" or os.getenv("CHINA_FUTURES_TRY_LEGACY_SHFE_RANK"):
            position_calls.append(("get_rank_sum_daily", lambda d: ak.get_rank_sum_daily(start_day=d, end_day=d, vars_list=[code])))

        last_err = None
        for func_name, call in position_calls:
            for candidate_date in snapshot_date_candidates(snapshot, days=supplement_lookback_days()):
                data, err = try_call(call, candidate_date)
                last_err = err
                if err:
                    continue
                matched = {}
                if isinstance(data, dict):
                    for key, value in data.items():
                        rows = filter_rows_for_product(frame_records(value), code, name)
                        if rows:
                            matched[str(key)] = summarize_position_records(rows)
                else:
                    rows = frame_records(data)
                    rows = filter_rows_for_product(rows, code, name) or rows
                    if rows:
                        matched["rows"] = summarize_position_records(rows)
                if matched:
                    fundamentals["position_rank"] = {
                        "source": f"AKShare.{func_name}",
                        "date": iso_date(candidate_date),
                        "matched": matched,
                    }
                    notes.append("position_rank: ok")
                    break
            if fundamentals.get("position_rank"):
                break
        if not fundamentals.get("position_rank"):
            eastmoney_position, eastmoney_err = fetch_eastmoney_position_rank(snapshot, normalized)
            if eastmoney_position:
                fundamentals["position_rank"] = eastmoney_position
                notes.append("position_rank: ok via EastMoney.qhhqzl")
            else:
                note_error("position_rank", "EastMoney.qhhqzl.dragonAndTigerInfo", eastmoney_err or "no rows returned")
        if not fundamentals.get("position_rank"):
            if exchange == "CZCE":
                direct_position, direct_err = fetch_czce_position_direct(snapshot, normalized)
                if direct_position:
                    fundamentals["position_rank"] = direct_position
                    notes.append("position_rank: ok via CZCE.direct")
                else:
                    msg = direct_err or last_err or "no rows returned"
                    note_error("position_rank", "CZCE.direct", msg)
                    notes.append(f"position_rank: {msg}")
            elif exchange == "DCE":
                dce_position, dce_err = fetch_dce_position_mirror(snapshot, normalized)
                if dce_position:
                    fundamentals["position_rank"] = dce_position
                    notes.append("position_rank: ok via DCE.mirror")
                else:
                    msg = dce_err or last_err or "no rows returned"
                    note_error("position_rank", "DCE.mirror.dlspjys", msg)
                    notes.append(f"position_rank: {msg}")
            elif exchange == "SHFE" and not os.getenv("CHINA_FUTURES_TRY_LEGACY_SHFE_RANK"):
                msg = "SHFE direct pm endpoint returned no usable rows; configure Tushare or set CHINA_FUTURES_TRY_LEGACY_SHFE_RANK=1"
                notes.append(f"position_rank: {msg}")
            else:
                msg = last_err or "no rows returned"
                note_error("position_rank", "AKShare.position_rank", msg)
                notes.append(f"position_rank: {msg}")

    snapshot["data_source_status"]["gap_supplements"] = "; ".join(notes) if notes else "no gaps requested"


def fetch_news_with_jin10(snapshot, normalized):
    if os.getenv("CHINA_FUTURES_SKIP_JIN10"):
        snapshot["data_source_status"]["jin10_mcp"] = "skipped: CHINA_FUTURES_SKIP_JIN10 is set"
        return
    token = os.getenv("JIN10_MCP_TOKEN")
    if not token:
        snapshot["data_source_status"]["jin10_mcp"] = "skipped: JIN10_MCP_TOKEN not set"
        return

    keywords = jin10_keywords_for(normalized)
    flash_pages = max(0, int(os.getenv("CHINA_FUTURES_JIN10_FLASH_PAGES") or 1))
    news_pages = max(0, int(os.getenv("CHINA_FUTURES_JIN10_NEWS_PAGES") or 1))
    detail_count_limit = max(0, int(os.getenv("CHINA_FUTURES_JIN10_DETAIL_COUNT") or 1))
    if os.getenv("CHINA_FUTURES_JIN10_INCLUDE_DETAILS") == "0":
        detail_count_limit = 0
    coverage = {
        "source": "Jin10 MCP",
        "protocol_version": "2025-11-25",
        "keywords": keywords,
        "tools": {},
        "errors": [],
    }

    def coverage_tool(name, ok, count=0, has_more=None, next_cursor=None, detail=None):
        coverage["tools"][name] = {
            "ok": bool(ok),
            "count": int(count or 0),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "detail": detail,
        }

    def note_jin10_error(name, exc):
        coverage["errors"].append({"tool": name, "message": str(exc)})
        coverage_tool(name, False, detail=str(exc))

    try:
        client = Jin10McpClient(token)
        client.initialize()
        try:
            tools_payload = client.list_tools()
            tools = tools_payload.get("tools") or []
            coverage_tool("tools/list", True, count=len(tools))
        except Exception as exc:
            note_jin10_error("tools/list", exc)
        try:
            resources_payload = client.list_resources()
            resources = resources_payload.get("resources") or []
            coverage_tool("resources/list", True, count=len(resources))
        except Exception as exc:
            note_jin10_error("resources/list", exc)
        items = []
        for keyword in keywords[:1]:
            for tool_name in ("search_flash", "search_news"):
                try:
                    structured = client.tool(tool_name, {"keyword": keyword})
                    data = structured.get("data") or {}
                    rows = data.get("items") if isinstance(data, dict) else []
                    added = add_jin10_items(
                        items,
                        rows or [],
                        source=f"Jin10.{tool_name}",
                        keyword=keyword,
                        keywords=keywords,
                        max_add=8 if tool_name == "search_flash" else 6,
                    )
                    coverage_tool(tool_name, True, count=len(rows or []), detail=f"added={added}; keyword={keyword}")
                except Exception as exc:
                    note_jin10_error(tool_name, exc)
        try:
            cursor = None
            total_count = 0
            last_has_more = None
            last_next_cursor = None
            for _ in range(flash_pages):
                args = {"cursor": cursor} if cursor else {}
                latest_flash = client.tool("list_flash", args)
                data = latest_flash.get("data") or {}
                rows = data.get("items") or []
                total_count += len(rows)
                add_jin10_items(
                    items,
                    rows,
                    source="Jin10.list_flash",
                    keywords=keywords,
                    require_relevance=True,
                    max_add=4,
                )
                last_has_more = data.get("has_more")
                last_next_cursor = data.get("next_cursor")
                if not last_has_more or not last_next_cursor:
                    break
                cursor = last_next_cursor
            coverage_tool("list_flash", True, count=total_count, has_more=last_has_more, next_cursor=last_next_cursor)
        except Exception as exc:
            note_jin10_error("list_flash", exc)
        try:
            cursor = None
            total_count = 0
            last_has_more = None
            last_next_cursor = None
            for _ in range(news_pages):
                args = {"cursor": cursor} if cursor else {}
                latest_news = client.tool("list_news", args)
                data = latest_news.get("data") or {}
                rows = data.get("items") or []
                total_count += len(rows)
                add_jin10_items(
                    items,
                    rows,
                    source="Jin10.list_news",
                    keywords=keywords,
                    require_relevance=True,
                    max_add=4,
                )
                last_has_more = data.get("has_more")
                last_next_cursor = data.get("next_cursor")
                if not last_has_more or not last_next_cursor:
                    break
                cursor = last_next_cursor
            coverage_tool("list_news", True, count=total_count, has_more=last_has_more, next_cursor=last_next_cursor)
        except Exception as exc:
            note_jin10_error("list_news", exc)
        if detail_count_limit:
            detail_count = 0
            for item in list(items):
                news_id = item.get("id")
                if not news_id or detail_count >= detail_count_limit:
                    continue
                try:
                    detail = client.tool("get_news", {"id": news_id})
                except Exception:
                    continue
                data = detail.get("data")
                if isinstance(data, dict):
                    item.update(data)
                    item["detail_source"] = "Jin10.get_news"
                    detail_count += 1
            coverage_tool("get_news", True, count=detail_count)
        try:
            calendar = client.tool("list_calendar", {})
            data = calendar.get("data")
            if isinstance(data, list):
                snapshot["macro_calendar"] = data[:20]
                coverage_tool("list_calendar", True, count=len(data))
            else:
                coverage_tool("list_calendar", False, detail="response data is not a list")
        except Exception as exc:
            note_jin10_error("list_calendar", exc)
        snapshot["news_coverage"] = coverage
        if items:
            snapshot["news"] = items[:20]
            usable_tools = [name for name, row in coverage["tools"].items() if row.get("ok")]
            snapshot["data_source_status"]["jin10_mcp"] = f"ok: {len(snapshot['news'])} items; tools={','.join(usable_tools)}"
        else:
            snapshot["data_source_status"]["jin10_mcp"] = "ok: no matching items"
    except (urllib.error.URLError, TimeoutError, RuntimeError, OSError, ValueError) as exc:
        snapshot["news_coverage"] = coverage
        snapshot["data_source_status"]["jin10_mcp"] = f"failed: {exc}"


def compute_technical(snapshot):
    bars = bars_through_analysis_date(snapshot)
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
    if quote.get("open") is None:
        quote["open"] = values["open"]
    if quote.get("high") is None:
        quote["high"] = values["high"]
    if quote.get("low") is None:
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
    contract = normalized.get("input") if normalized.get("is_exact_contract") else None
    if not contract:
        contract = normalized.get("product_code") + " main/daily" if normalized.get("product_code") else None
    quote.update(
        {
            "contract": contract,
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


def update_effective_dates(snapshot):
    meta = snapshot.setdefault("metadata", {})
    analysis_date = meta.get("analysis_date")
    quote = snapshot.get("quote") or {}
    candidates = []
    if quote.get("daily_bar_date"):
        candidates.append(quote.get("daily_bar_date"))
    for row in snapshot.get("daily_bars") or []:
        value = first_existing(row, ["date", "日期", "datetime", "trade_date"])
        if value:
            candidates.append(value)
    for value in (snapshot.get("fundamentals") or {}).values():
        if isinstance(value, dict) and value.get("date"):
            candidates.append(value.get("date"))
    normalized_dates = []
    for item in candidates:
        text = normalize_date_text(item)
        if text and (not analysis_date or text <= analysis_date):
            normalized_dates.append(text)
    if normalized_dates:
        effective = max(normalized_dates)
        meta["effective_market_date"] = effective
        meta["is_analysis_date_trading_day_like"] = effective == analysis_date
        if analysis_date and effective != analysis_date:
            warning = f"analysis_date {analysis_date} has no same-day market data; using latest available market date {effective}"
            warnings = snapshot.setdefault("warnings", [])
            if warning not in warnings:
                warnings.append(warning)


def finalize_missing(snapshot):
    quote = snapshot["quote"]
    for field in ["contract", "last", "change_pct", "volume", "open_interest"]:
        if quote.get(field) in (None, ""):
            snapshot["missing_reasons"].append(f"quote.{field}: unavailable from configured data sources")
    if not snapshot.get("daily_bars"):
        snapshot["missing_reasons"].append("daily_bars: unavailable from configured data sources")
    fundamentals = snapshot["fundamentals"]
    if not fundamentals.get("inventory"):
        snapshot["missing_reasons"].append("fundamentals.inventory: unavailable from configured data sources")
    if not fundamentals.get("warehouse_receipt"):
        snapshot["missing_reasons"].append("fundamentals.warehouse_receipt: unavailable from configured data sources")
    if not fundamentals.get("spot_basis"):
        snapshot["missing_reasons"].append("fundamentals.spot_basis: unavailable from configured data sources")
    if not fundamentals.get("position_rank"):
        snapshot["missing_reasons"].append("fundamentals.position_rank: unavailable from configured data sources")
    if not snapshot["news"]:
        snapshot["missing_reasons"].append("news: not fetched by local script; use current source-backed web search if needed")


def completeness_error_for(snapshot, field):
    for item in snapshot.get("supplement_errors") or []:
        if item.get("field") == field:
            return {
                "source": item.get("source"),
                "category": item.get("category") or "source_error",
                "message": item.get("message"),
            }
    for reason in snapshot.get("missing_reasons") or []:
        if field in str(reason):
            return {"source": "snapshot", "category": "missing", "message": reason}
    return {"source": "snapshot", "category": "missing", "message": "unavailable from configured data sources"}


def update_data_completeness(snapshot):
    quote = snapshot.get("quote") or {}
    fundamentals = snapshot.get("fundamentals") or {}
    checks = [
        {
            "field": "quote",
            "ok": all(quote.get(key) not in (None, "") for key in ("contract", "last", "volume", "open_interest")),
            "source": quote.get("source"),
        },
        {
            "field": "daily_bars",
            "ok": bool(snapshot.get("daily_bars")),
            "source": "snapshot.daily_bars",
        },
        {
            "field": "spot_basis",
            "ok": bool(fundamentals.get("spot_basis")),
            "source": (fundamentals.get("spot_basis") or {}).get("source"),
        },
        {
            "field": "inventory",
            "ok": bool(fundamentals.get("inventory")),
            "source": (fundamentals.get("inventory") or {}).get("source"),
        },
        {
            "field": "warehouse_receipt",
            "ok": bool(fundamentals.get("warehouse_receipt")),
            "source": (fundamentals.get("warehouse_receipt") or {}).get("source"),
        },
        {
            "field": "position_rank",
            "ok": bool(fundamentals.get("position_rank")),
            "source": (fundamentals.get("position_rank") or {}).get("source"),
        },
        {
            "field": "news",
            "ok": bool(snapshot.get("news")),
            "source": "Jin10 MCP" if snapshot.get("news") else None,
        },
        {
            "field": "macro_calendar",
            "ok": bool(snapshot.get("macro_calendar")),
            "source": "Jin10 MCP" if snapshot.get("macro_calendar") else None,
            "required": False,
        },
    ]
    rows = []
    required_total = 0
    required_ok = 0
    for item in checks:
        required = item.get("required", True)
        row = {
            "field": item["field"],
            "ok": bool(item.get("ok")),
            "required": required,
            "source": item.get("source"),
        }
        if not row["ok"]:
            row.update(completeness_error_for(snapshot, item["field"]))
        if required:
            required_total += 1
            required_ok += 1 if row["ok"] else 0
        rows.append(row)
    snapshot["data_completeness"] = {
        "required_ok": required_ok,
        "required_total": required_total,
        "required_ratio": round(required_ok / required_total, 4) if required_total else None,
        "fields": rows,
    }


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
        "news_coverage": {},
        "macro_calendar": [],
        "data_completeness": {},
        "supplement_errors": [],
        "raw_samples": {},
        "missing_reasons": [],
        "warnings": [],
    }
    proxy_env = disable_proxy_for_public_sources(snapshot)
    try:
        fetch_with_tqsdk(snapshot, normalized, want_tq=not args.no_tqsdk)
        if snapshot["quote"].get("last") is None or not snapshot.get("daily_bars"):
            fetch_with_akshare(snapshot, normalized)
    finally:
        restore_proxy_env(proxy_env)
    update_effective_dates(snapshot)
    if not getattr(args, "no_tushare", False):
        fetch_with_tushare(snapshot, normalized)
    else:
        snapshot["data_source_status"]["tushare"] = "skipped by flag"
    fetch_manual_supplements(snapshot, normalized)
    proxy_env = disable_proxy_for_public_sources(snapshot)
    try:
        fetch_fundamentals_with_akshare(snapshot, normalized)
        fetch_gap_supplements(snapshot, normalized)
    finally:
        restore_proxy_env(proxy_env)
    if not getattr(args, "no_jin10", False):
        fetch_news_with_jin10(snapshot, normalized)
    else:
        snapshot["data_source_status"]["jin10_mcp"] = "skipped by flag"
    compute_technical(snapshot)
    enrich_quote_from_daily_bars(snapshot)
    fill_quote_from_daily_bars(snapshot)
    update_effective_dates(snapshot)
    finalize_missing(snapshot)
    update_data_completeness(snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Fetch a China futures market snapshot.")
    parser.add_argument("instrument", help="Chinese futures variety name or contract code, e.g. 螺纹钢, 沪铜, RB2410")
    parser.add_argument("--date", default=None, help="Analysis date, YYYY-MM-DD. Defaults to Asia/Shanghai today.")
    parser.add_argument("--out", default=None, help="Write JSON to this file instead of stdout.")
    parser.add_argument("--no-tqsdk", action="store_true", help="Skip TqSdk even if configured.")
    parser.add_argument("--no-jin10", action="store_true", help="Skip Jin10 MCP news/calendar enrichment.")
    parser.add_argument("--no-tushare", action="store_true", help="Skip optional Tushare Pro warehouse/position enrichment.")
    args = parser.parse_args()
    snapshot = build_snapshot(args)
    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()

