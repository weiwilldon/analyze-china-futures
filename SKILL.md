---
name: analyze-china-futures
description: Analyze China futures markets and produce Markdown daily reports, research views, trade plans, and contract comparisons for China commodity futures, stock index futures, and user-specified futures varieties. Use when Codex needs to analyze today's China futures market, a named futures product such as 螺纹钢/沪铜/铁矿/豆粕, a contract code such as RB/CU/I/IF, basis/inventory/open-interest context, technical levels, risk scenarios, or a research-backed trading plan.
---

# Analyze China Futures

## Core Workflow

Use this skill to analyze user-specified China futures varieties or contracts. Default to a Markdown daily report unless the user asks for another format.

1. Parse the requested variety or contract and the analysis date. Use Asia/Shanghai today when the date is omitted.
2. Read `references/data-sources.md` before fetching data. Prefer reliable live data over assumptions.
3. Run `scripts/fetch_china_futures_snapshot.py "<instrument>" --date YYYY-MM-DD` to collect a structured JSON snapshot. If the script reports missing fields, keep those gaps visible.
4. Read `references/analysis-playbook.md` before forming the final view.
5. Run `scripts/render_daily_report.py <snapshot.json>` when a stable Markdown draft is useful, then improve the narrative with current context and user intent.
6. Browse current public sources when the user asks for a publishable daily report and the snapshot lacks news, basis, inventory, warehouse receipts, or exchange announcements. Cite sources and do not treat unsourced commentary as fact.
7. Read `references/report-template.md` when the user wants a full daily report or when consistency matters.

Do not invent prices, contract codes, inventories, warehouse receipts, basis, news, or positions. If a data source is unavailable, state the gap and explain how it affects confidence.

## Output Standards

- Include both a research view and a trade plan when the user asks for analysis, unless they explicitly request data-only output.
- For trade plans, include direction bias, trigger, stop loss, invalidation condition, target/management idea, and risk caveat.
- Clearly mark whether the view is based on complete data, partial data, or qualitative reasoning.
- Prefer the rendered draft's calculated quote, technical levels, and data gaps over memory. Refine the prose, but do not overwrite sourced values without stronger evidence.
- If the script provides structured inventory, warehouse receipt, or basis data, use those fields directly in the basic-fundamentals section and only browse to corroborate or fill remaining gaps.
- Include: `本内容仅供研究辅助，不构成投资建议。`
- For comparison requests, analyze each requested variety with the same fields and finish with relative strength, cleaner setup, and key risk.

## Script Usage

Fetch a snapshot:

```bash
python scripts/fetch_china_futures_snapshot.py "螺纹钢" --date 2026-06-26 --out snapshot.json
```

Render a draft report:

```bash
python scripts/render_daily_report.py snapshot.json --out report.md
```

The fetch script tries TqSdk first when available and configured, then public Python data sources such as AKShare. It is acceptable for it to return a partial snapshot with explicit missing-data reasons.

## References

- `references/data-sources.md`: data priority, source behavior, and missing-data rules.
- `references/analysis-playbook.md`: analysis roles and reasoning checklist.
- `references/report-template.md`: stable Markdown report structure.
