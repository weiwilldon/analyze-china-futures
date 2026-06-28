#!/usr/bin/env python3
"""Create a manual-data request list for missing futures fields."""

import argparse
import contextlib
import importlib.util
import json
import os
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


FIELD_META = {
    "spot_basis": {
        "kind": "basis",
        "template": "manual-data/templates/basis_template.csv",
        "columns": "date, product/code, spot, futures, basis",
        "source_hint": "产业数据库或供应商现货/基差导出，如 Mysteel/SMM/百川盈孚/隆众/Wind/Choice",
    },
    "warehouse_receipt": {
        "kind": "warehouse_receipt",
        "template": "manual-data/templates/warehouse_receipt_template.csv",
        "columns": "date, product/code, warehouse, receipt/change",
        "source_hint": "交易所仓单日报、Tushare fut_wsr、供应商仓单导出",
    },
    "position_rank": {
        "kind": "position_rank",
        "template": "manual-data/templates/position_rank_template.csv",
        "columns": "date, product/code, rank, vol, long_open_interest, short_open_interest",
        "source_hint": "交易所日成交持仓排名、Tushare fut_holding、供应商席位持仓导出",
    },
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Args:
    pass


def audit_rows(instruments, date):
    audit = load_module("audit_data_gaps", SCRIPTS / "audit_data_gaps.py")
    fetch = audit.load_fetch_module()
    args = Args()
    args.no_tqsdk = False
    args.no_tushare = False
    args.no_jin10 = True
    date = date or fetch.today_shanghai()
    rows = []
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            for instrument in instruments:
                rows.append(audit.audit_one(fetch, instrument, date, args))
    return date, rows


def missing_fields(row):
    out = []
    for field, key in (
        ("spot_basis", "basis"),
        ("warehouse_receipt", "warehouse_receipt"),
        ("position_rank", "position_rank"),
    ):
        if not (row.get(key) or {}).get("ok"):
            out.append(field)
    return out


def suggested_name(date, product_code, meta):
    compact = str(date).replace("-", "")
    return f"{compact}_{product_code}_{meta['kind']}.csv"


def compact_date(value):
    return str(value or "").replace("-", "")


def dce_params(date, product_code, field):
    compact = compact_date(date)
    year = compact[:4]
    month_zero = str(int(compact[4:6]) - 1)
    day = compact[6:]
    lower = str(product_code or "").lower()
    if field == "warehouse_receipt":
        return {
            "wbillWeeklyQuotes.variety": "all",
            "year": year,
            "month": month_zero,
            "day": day,
        }
    return {
        "memberDealPosiQuotes.variety": lower,
        "memberDealPosiQuotes.trade_type": "0",
        "contract.contract_id": "all",
        "contract.variety_id": lower,
        "year": year,
        "month": month_zero,
        "day": day,
        "batchExportFlag": "batch",
    }


def with_query(url, params):
    return f"{url}?{urllib.parse.urlencode(params)}" if params else url


def source_hints(normalized, field, date):
    product_code = normalized.get("product_code")
    exchange = normalized.get("exchange")
    compact = compact_date(date)
    year = compact[:4]
    hints = []
    if field == "spot_basis":
        hints.extend(
            [
                {
                    "name": "100ppi 每日基差页",
                    "kind": "public_page",
                    "url": f"https://www.100ppi.com/sf/day-{date}.html",
                    "note": "若页面覆盖该品种，可导出现货、期货和基差列。",
                },
                {
                    "name": "产业数据库导出",
                    "kind": "vendor_export",
                    "url": "",
                    "note": "Mysteel/SMM/百川盈孚/隆众/Wind/Choice 的现货或基差导出可放入 manual-data。",
                },
            ]
        )
    if field == "warehouse_receipt":
        hints.append(
            {
                "name": "Tushare Pro fut_wsr",
                "kind": "optional_api",
                "url": "https://tushare.pro/document/2?doc_id=153",
                "note": "配置 TUSHARE_TOKEN 后脚本会自动尝试；适合公开入口被拦截时补仓单。",
            }
        )
        hints.append(
            {
                "name": "AKShare futures_inventory_em aggregate fallback",
                "kind": "public_api",
                "url": "https://akshare.akfamily.xyz/data/futures/futures.html",
                "note": "脚本会在分仓库仓单不可用时使用公开库存/仓单日报聚合序列补齐仓单字段，并标注 aggregate 口径。",
            }
        )
        if exchange == "CZCE":
            hints.extend(
                [
                    {
                        "name": "CZCE 仓单静态 Excel",
                        "kind": "direct_file",
                        "url": f"http://www.czce.com.cn/cn/DFSStaticFiles/Future/{year}/{compact}/FutureDataWhsheet.xls",
                        "note": "若返回 404，说明该日期文件未发布或不可用；可从网页手动找最近有效交易日。",
                    },
                    {
                        "name": "CZCE 仓单日报入口",
                        "kind": "official_page",
                        "url": "https://www.czce.com.cn/cn/jysj/cdrb/H077003010index_1.htm",
                        "note": "浏览器打开后下载仓单日报，再按模板整理。",
                    },
                ]
            )
        elif exchange == "DCE":
            params = dce_params(date, product_code, field)
            hints.extend(
                [
                    {
                        "name": "DCE 仓单公开镜像",
                        "kind": "public_page",
                        "url": with_query("http://www.dlspjys.cn/publicweb/quotesdata/wbillWeeklyQuotes.html", params),
                        "note": "若自动解析被挑战页拦截，可用浏览器打开后复制表格或下载。",
                    },
                    {
                        "name": "DCE 仓单官方入口",
                        "kind": "official_page",
                        "url": with_query("http://www.dce.com.cn/publicweb/quotesdata/wbillWeeklyQuotes.html", params),
                        "note": "可能返回 HTTP 412/WAF；优先用镜像或 Tushare。",
                    },
                ]
            )
        elif exchange == "SHFE":
            hints.extend(
                [
                    {
                        "name": "SHFE 仓单 JSON",
                        "kind": "direct_file",
                        "url": f"https://www.shfe.com.cn/data/tradedata/future/dailydata/{compact}dailystock.dat",
                        "note": "按 VARID 严格匹配品种；404 表示该日期文件不可用。",
                    },
                    {
                        "name": "SHFE 日周数据入口",
                        "kind": "official_page",
                        "url": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/",
                        "note": "浏览器下载仓单日报后放入 manual-data。",
                    },
                ]
            )
        elif exchange == "GFEX":
            hints.extend(
                [
                    {
                        "name": "GFEX 仓单 API",
                        "kind": "direct_api",
                        "url": "http://www.gfex.com.cn/u/interfacesWebTdWbillWeeklyQuotes/loadList",
                        "note": f"POST 参数 gen_date={compact}；脚本已能自动调用。",
                    },
                    {
                        "name": "GFEX 仓单日报入口",
                        "kind": "official_page",
                        "url": "https://www.gfex.com.cn/gfex/cdrb/hqsj_tjsj.shtml",
                        "note": "浏览器下载后可放入 manual-data。",
                    },
                ]
            )
    if field == "position_rank":
        hints.append(
            {
                "name": "Tushare Pro fut_holding",
                "kind": "optional_api",
                "url": "https://tushare.pro/document/2?doc_id=154",
                "note": "配置 TUSHARE_TOKEN 后脚本会自动尝试；适合公开席位入口被拦截时补数据。",
            }
        )
        hints.append(
            {
                "name": "EastMoney qhhqzl futures dragon-and-tiger board",
                "kind": "public_api",
                "url": f"https://qhweb.eastmoney.com/lhb/dkcc/{str(exchange or '').lower()}/{product_code}",
                "note": "脚本会用东方财富期货龙虎榜 JSON 接口补成交量、多头持仓、空头持仓及增减；交易所原始排名仍优先。",
            }
        )
        if exchange == "CZCE":
            hints.extend(
                [
                    {
                        "name": "CZCE 持仓排名静态 Excel",
                        "kind": "direct_file",
                        "url": f"http://www.czce.com.cn/cn/DFSStaticFiles/Future/{year}/{compact}/FutureDataHolding.xls",
                        "note": "若返回 404，说明该日期文件未发布或不可用；可从网页手动找最近有效交易日。",
                    },
                    {
                        "name": "CZCE 交易数据入口",
                        "kind": "official_page",
                        "url": "https://www.czce.com.cn/cn/jysj/mrhq/H770303index_1.htm",
                        "note": "浏览器下载成交持仓排名后按模板整理。",
                    },
                ]
            )
        elif exchange == "DCE":
            params = dce_params(date, product_code, field)
            hints.extend(
                [
                    {
                        "name": "DCE 席位导出镜像",
                        "kind": "public_download",
                        "url": "http://www.dlspjys.cn/publicweb/quotesdata/exportMemberDealPosiQuotesBatchData.html",
                        "method": "POST",
                        "params": params,
                        "note": "若返回 HTML 而不是下载文件，按 WAF/挑战页处理，用 Tushare 或浏览器下载兜底。",
                    },
                    {
                        "name": "DCE 席位导出官方入口",
                        "kind": "official_download",
                        "url": "http://www.dce.com.cn/publicweb/quotesdata/exportMemberDealPosiQuotesBatchData.html",
                        "method": "POST",
                        "params": params,
                        "note": "可能返回 HTTP 412/WAF；优先用镜像或 Tushare。",
                    },
                ]
            )
        elif exchange == "SHFE":
            hints.extend(
                [
                    {
                        "name": "SHFE 席位 JSON",
                        "kind": "direct_file",
                        "url": f"https://www.shfe.com.cn/data/tradedata/future/dailydata/pm{compact}.dat",
                        "note": "脚本按 PRODUCTID / rank fields 解析成交、持买、持卖排名。",
                    },
                    {
                        "name": "SHFE 日周数据入口",
                        "kind": "official_page",
                        "url": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/",
                        "note": "浏览器下载会员成交持仓排名后放入 manual-data。",
                    },
                ]
            )
        elif exchange == "GFEX":
            hints.extend(
                [
                    {
                        "name": "GFEX 席位合约列表 API",
                        "kind": "direct_api",
                        "url": "http://www.gfex.com.cn/u/interfacesWebTiMemberDealPosiQuotes/loadListContract_id",
                        "note": f"POST 参数 variety={str(product_code or '').lower()}, trade_date={compact}。",
                    },
                    {
                        "name": "GFEX 席位排名 API",
                        "kind": "direct_api",
                        "url": "http://www.gfex.com.cn/u/interfacesWebTiMemberDealPosiQuotes/loadList",
                        "note": "脚本按 data_type=1/2/3 分别取成交、持买、持卖排名。",
                    },
                    {
                        "name": "GFEX 成交持仓排名入口",
                        "kind": "official_page",
                        "url": "https://www.gfex.com.cn/gfex/rcjccpm/hqsj_tjsj.shtml",
                        "note": "浏览器下载或核验排名数据。",
                    },
                ]
            )
    return hints


def resource_plan_for(row, field):
    for item in row.get("resource_plan") or []:
        if item.get("field") == field:
            return item
    return {}


def build_requests(instruments, date):
    date, rows = audit_rows(instruments, date)
    requests = []
    for row in rows:
        normalized = row.get("normalized") or {}
        product_code = normalized.get("product_code") or row.get("instrument")
        effective_date = row.get("effective_market_date") or date
        for field in missing_fields(row):
            meta = FIELD_META[field]
            related_errors = [
                item
                for item in row.get("supplement_errors") or []
                if item.get("field") == field or (field == "spot_basis" and item.get("field") == "spot_basis")
            ]
            requests.append(
                {
                    "instrument": row.get("instrument"),
                    "product_code": product_code,
                    "exchange": normalized.get("exchange"),
                    "field": field,
                    "effective_market_date": effective_date,
                    "suggested_file": f"manual-data/{suggested_name(effective_date, product_code, meta)}",
                    "template": meta["template"],
                    "required_columns": meta["columns"],
                    "source_hint": meta["source_hint"],
                    "source_hints": source_hints(normalized, field, effective_date),
                    "resource_plan": resource_plan_for(row, field),
                    "reason": "; ".join(row.get("missing_reasons") or []),
                    "errors": related_errors,
                }
            )
    return {"date": date, "requests": requests}


def render_markdown(report):
    lines = ["# 手动数据补充清单", ""]
    if not report["requests"]:
        lines.append("当前审计没有发现需要手动文件补充的基差、仓单或席位字段。")
        return "\n".join(lines) + "\n"
    lines.append("| 品种 | 交易所 | 字段 | 有效行情日 | 建议文件 | 模板 | 关键列 |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in report["requests"]:
        lines.append(
            "| {product} | {exchange} | {field} | {date} | {file} | {template} | {columns} |".format(
                product=item["product_code"],
                exchange=item.get("exchange") or "",
                field=item["field"],
                date=item.get("effective_market_date") or "",
                file=item["suggested_file"],
                template=item["template"],
                columns=item["required_columns"],
            )
        )
    lines.append("")
    lines.append("## 来源建议")
    for item in report["requests"]:
        lines.append(f"- {item['product_code']} {item['field']}：{item['source_hint']}")
        plan = item.get("resource_plan") or {}
        if plan.get("recommended_next"):
            lines.append(f"  - 建议动作：{plan['recommended_next']}")
        for hint in item.get("source_hints") or []:
            label = hint.get("name")
            url = hint.get("url")
            note = hint.get("note")
            method = hint.get("method")
            params = hint.get("params")
            method_text = f"，方法 {method}" if method else ""
            params_text = f"，参数 `{json.dumps(params, ensure_ascii=False)}`" if params else ""
            if url:
                lines.append(f"  - {label}：{url}{method_text}{params_text}。{note}")
            else:
                lines.append(f"  - {label}：{note}")
    lines.append("")
    lines.append("把文件放入 `manual-data/` 后，重新运行快照或诊断；脚本只会用手动文件填补缺失字段，不覆盖已有结构化来源。")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Prepare manual-data file requests for missing fields.")
    parser.add_argument("instruments", nargs="*", default=["FG", "JM", "AO"], help="Product names or codes.")
    parser.add_argument("--date", default=None, help="Analysis date, YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args()

    report = build_requests(args.instruments, args.date)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
