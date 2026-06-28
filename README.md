# Analyze China Futures

`analyze-china-futures` is a Codex Skill for generating China futures market daily reports. It prioritizes TqSdk for quotes and bars, uses AKShare/100ppi/exchange public data for fundamentals, enriches news with Jin10 MCP, can add Tushare Pro warehouse and member-position data, and accepts manual vendor/exchange exports when public endpoints are blocked. It marks missing data instead of inventing prices, fundamentals, news, basis, inventory, warehouse receipts, or positions.

## What It Does

- Produces Markdown daily reports for user-specified China futures varieties or contracts.
- Supports commodities and index futures such as 螺纹钢, 沪铜, 铁矿石, 焦煤, 豆粕, RB, CU, I, JM, IF, IC, IH, and IM.
- Includes market snapshot, technical structure, basic fundamental/flow context, research view, trade plan, risk notes, and missing-data disclosure.
- Uses TqSdk first when `TQSDK_USER` and `TQSDK_PASSWORD` are available.
- Uses AKShare, 100ppi, exchange public data, Jin10 MCP, optional Tushare Pro, and manual files as fallback/enrichment sources where available.
- Keeps missing basis, warehouse receipt, member-position, and news fields visible instead of silently filling guesses.

## Install

Copy this folder into your Codex skills directory:

```powershell
Copy-Item -Recurse . "$env:USERPROFILE\.codex\skills\analyze-china-futures"
```

Then invoke it in Codex:

```text
用 $analyze-china-futures 分析今天焦煤，生成 Markdown 日报，包含研究观点和交易计划，不编造缺失数据。
```

## Data Source Setup

Install Python dependencies:

```powershell
py -m pip install --user -r requirements.txt
```

Set TqSdk credentials as user environment variables:

```powershell
.\scripts\setup_tqsdk_env.ps1
```

The setup script prompts locally and does not print the password.

Check what is ready on this machine:

```powershell
py .\scripts\check_data_sources.py --pretty --network
```

Optional sources:

- TqSdk: quotes and daily bars, configured with `TQSDK_USER` and `TQSDK_PASSWORD`.
- Jin10 MCP: flash/news/calendar enrichment, configured with `JIN10_MCP_TOKEN`.
- Tushare Pro: warehouse receipts and member-position rankings, configured with `TUSHARE_TOKEN`.
- Manual files: place vendor or exchange exports in `manual-data/` when public automated endpoints are blocked.

See `references/ready-made-resources.md` for the field-by-field resource matrix and official/public data links.

Set Tushare Pro token:

```powershell
.\scripts\setup_tushare_env.ps1 -Token "your_token_here"
```

Manual supplement file examples:

```text
manual-data\20260626_AO_warehouse_receipt.xlsx
manual-data\20260626_JM_position_rank.json
manual-data\20260626_FG_basis.csv
```

Supported manual formats are `.json`, `.csv`, `.xls`, and `.xlsx`. Manual file names can use either the requested analysis date or the latest effective market date from diagnostics, such as `20260626_*` for a weekend report dated `2026-06-28`. Manual files only fill missing fields; they do not overwrite structured data already fetched from configured sources.

## Direct Script Usage

Fetch a snapshot:

```powershell
py .\scripts\fetch_china_futures_snapshot.py "焦煤" --out snapshot.json
```

Render a report:

```powershell
py .\scripts\render_daily_report.py snapshot.json --out report.md
```

Run a quick validation:

```powershell
py .\scripts\quick_validate.py
```

Diagnose all configured data sources and current data gaps:

```powershell
py .\scripts\diagnose_data_readiness.py FG JM AO --date 2026-06-27
```

Prepare exact manual-data file requests for missing basis, warehouse, and position fields:

```powershell
py .\scripts\prepare_manual_data_requests.py FG JM AO --date 2026-06-27
```

The manual request output includes the effective market date, suggested file name, required columns, and source hints such as exchange download/API links, Tushare Pro endpoints, or vendor-export guidance.

Include Jin10 news in the smoke test:

```powershell
py .\scripts\quick_validate.py --with-network-news
```

Audit data-gap coverage for several products:

```powershell
py .\scripts\audit_data_gaps.py FG JM AO --date 2026-06-27
```

Audit the four core remediation targets: basis, warehouse receipts, member positions, and Jin10 news flow:

```powershell
py .\scripts\audit_completion_status.py FG JM AO LC SI --date 2026-06-27 --with-jin10-full
```

Probe exchange public endpoints for warehouse receipts and position rankings:

```powershell
py .\scripts\probe_exchange_sources.py FG JM AO --date 2026-06-27
```

Probe optional Tushare Pro endpoints after setting `TUSHARE_TOKEN`:

```powershell
py .\scripts\probe_tushare_sources.py FG JM AO --date 2026-06-27
```

Probe Jin10 MCP flash, news, and calendar tools:

```powershell
py .\scripts\probe_jin10_sources.py FG JM AO
```

## Safety

This project is for research assistance only. Generated reports must include:

```text
本内容仅供研究辅助，不构成投资建议。
```

Do not commit credentials, generated reports with private data, or trading account information.

## Contributing

Issues and pull requests are welcome. Useful improvements include:

- Better exchange data adapters.
- More robust basis, inventory, and warehouse receipt collection.
- Additional product mappings.
- Cleaner report templates.
- Tests using mocked snapshots.

## 2026-06 数据补源更新

- 仓单字段新增 AKShare `futures_inventory_em` 聚合兜底；当交易所分仓库仓单不可用时，报告会标注为 `aggregate` 口径，不冒充明细仓单。
- 席位持仓新增东方财富期货龙虎榜公开 JSON 兜底；可补成交量、多头、空头及增减。
- 金十 MCP 继续负责新闻、快讯和财经日历，优先读取 `structuredContent`。
