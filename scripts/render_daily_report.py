#!/usr/bin/env python3
"""Render a Markdown draft report from a futures snapshot JSON file."""

import argparse
import json
import sys
from pathlib import Path


def fmt(value, suffix="", digits=2):
    if value is None or value == "":
        return "缺失"
    if isinstance(value, float):
        if abs(value) >= 10000 and value.is_integer():
            return f"{value:,.0f}{suffix}"
        if value.is_integer():
            return f"{value:.0f}{suffix}"
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def quality(snapshot):
    missing = snapshot.get("missing_reasons") or []
    quote = snapshot.get("quote") or {}
    has_core_quote = quote.get("last") is not None and quote.get("volume") is not None and quote.get("open_interest") is not None
    if has_core_quote and len(missing) <= 2:
        return "部分完整（行情与技术较完整，基本面/新闻需人工补源）"
    if quote.get("last") is not None:
        return "部分完整"
    return "不足，需补充实时行情"


def trend_label(snapshot):
    tech = snapshot.get("technical") or {}
    quote = snapshot.get("quote") or {}
    last = quote.get("last") or tech.get("last_close")
    ma5 = tech.get("ma5")
    ma20 = tech.get("ma20")
    change_pct = quote.get("change_pct")
    if last is None:
        return "数据不足", "缺少价格数据，不能形成可靠方向判断。"
    if ma20 is not None and last < ma20 and (ma5 is None or last < ma5):
        if change_pct is not None and change_pct > 0:
            return "弱势震荡中的低位修复", "价格仍低于短中期均线，但当日收涨，属于弱势结构内的修复。"
        return "偏弱震荡", "价格低于短中期均线，趋势仍偏弱。"
    if ma20 is not None and last > ma20 and (ma5 is None or last >= ma5):
        return "偏强震荡", "价格位于主要均线之上，结构相对偏强。"
    return "中性震荡", "价格处在关键均线附近，方向需要成交持仓和基本面继续确认。"


def confidence(snapshot):
    missing = snapshot.get("missing_reasons") or []
    quote = snapshot.get("quote") or {}
    if quote.get("source") == "TqSdk" and quote.get("change_pct") is not None and len(missing) <= 2:
        return "中等"
    if quote.get("last") is not None:
        return "中等偏低"
    return "低"


def status_summary(statuses):
    useful = []
    degraded = []
    for key, value in (statuses or {}).items():
        if value == "ok":
            useful.append(key)
        elif key == "proxy":
            continue
        else:
            text = str(value)
            if len(text) > 180:
                text = text[:177].rstrip() + "..."
            degraded.append(f"{key}: {text}")
    return useful, degraded


def fundamental_lines(snapshot):
    fundamentals = snapshot.get("fundamentals") or {}
    inventory = fundamentals.get("inventory") or {}
    receipt = fundamentals.get("warehouse_receipt") or {}
    basis = fundamentals.get("spot_basis") or {}
    lines = []
    if inventory:
        lines.append(
            f"- 库存：{fmt(inventory.get('value'))}，增减 {fmt(inventory.get('change'))}，日期 {fmt(inventory.get('date'))}，来源 {inventory.get('source', '缺失')}。"
        )
    else:
        lines.append("- 库存：缺失。")
    if receipt:
        matched = receipt.get("matched_rows") or {}
        row_count = sum(len(v) for v in matched.values() if isinstance(v, list))
        lines.append(
            f"- 仓单：已抓取 {fmt(receipt.get('date'))} 郑商所仓单匹配记录 {row_count} 条，来源 {receipt.get('source', '缺失')}。"
        )
    else:
        lines.append("- 仓单：缺失。")
    if basis:
        lines.append(
            f"- 现货/基差：现货 {fmt(basis.get('spot'))}，期货 {fmt(basis.get('futures'))}，基差 {fmt(basis.get('basis'))}，来源 {basis.get('source', '缺失')}。"
        )
    else:
        lines.append("- 现货/基差：缺失。")
    return lines


def missing_risk_text(missing):
    missing_text = " ".join(missing or [])
    items = []
    if "inventory" in missing_text:
        items.append("库存")
    if "warehouse_receipt" in missing_text:
        items.append("仓单")
    if "spot_basis" in missing_text:
        items.append("基差")
    if "news" in missing_text:
        items.append("新闻")
    if not items:
        return "盘中政策、供需或宏观事件改变预期。"
    return "、".join(items) + "仍有缺口，基本面判断需降权。"


def render(snapshot):
    meta = snapshot.get("metadata") or {}
    normalized = snapshot.get("normalized") or {}
    quote = snapshot.get("quote") or {}
    tech = snapshot.get("technical") or {}
    missing = snapshot.get("missing_reasons") or []
    statuses = snapshot.get("data_source_status") or {}
    useful_sources, degraded_sources = status_summary(statuses)
    bias, view_text = trend_label(snapshot)
    instrument = normalized.get("input") or (snapshot.get("input") or {}).get("instrument") or "未知品种"
    source = quote.get("source_detail") or quote.get("source") or "缺失"
    support = tech.get("support_20d")
    resistance = quote.get("high") or tech.get("resistance_20d")
    ma5 = tech.get("ma5")
    ma20 = tech.get("ma20")
    open_interest = quote.get("open_interest")
    fundamentals_text = fundamental_lines(snapshot)

    lines = [
        f"# 中国期货日报：{instrument}（{meta.get('analysis_date', '未知日期')}）",
        "",
        f"> 数据完整度：{quality(snapshot)}",
        "> 本内容仅供研究辅助，不构成投资建议。",
        "",
        "## 1. 核心结论",
        f"- 方向判断：{bias}",
        f"- 置信度：{confidence(snapshot)}",
        f"- 今日关键变量：{fmt(support)} 支撑、{fmt(ma5)} 附近 MA5、{fmt(resistance)} 压力、成交持仓变化。",
        f"- 最大风险：{missing_risk_text(missing)}",
        "",
        "## 2. 行情概览",
        "| 字段 | 数值 |",
        "|---|---:|",
        f"| 主力/合约 | {fmt(quote.get('contract'))} |",
        f"| 最新价/收盘价 | {fmt(quote.get('last'))} |",
        f"| 涨跌 | {fmt(quote.get('change'))} |",
        f"| 涨跌幅 | {fmt(quote.get('change_pct'), '%')} |",
        f"| 开盘 | {fmt(quote.get('open'))} |",
        f"| 最高 | {fmt(quote.get('high'))} |",
        f"| 最低 | {fmt(quote.get('low'))} |",
        f"| 成交量 | {fmt(quote.get('volume'))} |",
        f"| 持仓量 | {fmt(open_interest)} |",
        f"| 结算价 | {fmt(quote.get('settlement'))} |",
        f"| 数据源 | {source} |",
        "",
        "## 3. 技术结构",
        f"- 趋势：{view_text}",
        f"- MA5：{fmt(ma5)}；MA20：{fmt(ma20)}。",
        f"- 支撑：{fmt(support)}；压力：{fmt(resistance)}。",
        f"- 波动与量能：成交量 {fmt(quote.get('volume'))}，持仓量 {fmt(open_interest)}；若价格方向与持仓变化背离，优先按震荡修复处理。",
        "",
        "## 4. 基本面与资金",
        *fundamentals_text,
        f"- 成交持仓：当前持仓 {fmt(open_interest)}，结合价格位置判断资金确认度。",
        "- 新闻与宏观：本地脚本不自动编写新闻结论；需要使用当前、可引用来源补充。",
        "",
        "## 5. 研究观点",
        f"- 多头逻辑：若价格守住 {fmt(support)} 并重新站上 {fmt(ma5)}，低位修复可能延续。",
        f"- 空头逻辑：若价格跌破 {fmt(support)} 或反弹不能站稳 {fmt(resistance)}，弱势结构仍占优。",
        f"- 综合判断：{view_text}",
        "",
        "## 6. 交易计划",
        f"- 偏向：{bias}，优先轻仓或等待确认。",
        f"- 多头触发：重新站上 {fmt(resistance)}，且成交放大、持仓不再明显下降。",
        f"- 多头止损/失效：跌回 {fmt(ma5)} 下方或跌破 {fmt(support)}。",
        f"- 空头触发：反弹不能站稳 {fmt(resistance)}，或跌破 {fmt(support)} 后无法快速收回。",
        f"- 空头止损/失效：有效突破 {fmt(resistance)} 上方并持续放量。",
        "- 目标/管理：先看相邻支撑/压力区；盈利后移动止损，避免重仓追涨杀跌。",
        "- 不参与条件：临近重大公告、夜盘波动异常、产业消息未确认、数据缺口影响方向判断。",
        "",
        "## 7. 数据缺口",
    ]
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- 暂无关键缺口。")
    lines.extend(["", "## 8. 数据源状态"])
    lines.append("- 可用：" + ("、".join(useful_sources) if useful_sources else "无"))
    if degraded_sources:
        lines.append("- 降级/失败：")
        lines.extend(f"  - {item}" for item in degraded_sources)
    else:
        lines.append("- 降级/失败：无")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Render a China futures Markdown daily report.")
    parser.add_argument("snapshot", help="Snapshot JSON path.")
    parser.add_argument("--out", default=None, help="Write Markdown to this file instead of stdout.")
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    text = render(snapshot)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
