# Analyze China Futures

`analyze-china-futures` is a Codex Skill for generating China futures market daily reports. It prioritizes TqSdk when credentials are configured, falls back to public sources such as AKShare, and marks missing data instead of inventing prices, fundamentals, news, basis, inventory, or warehouse receipts.

## What It Does

- Produces Markdown daily reports for user-specified China futures varieties or contracts.
- Supports commodities and index futures such as 螺纹钢, 沪铜, 铁矿石, 焦煤, 豆粕, RB, CU, I, JM, IF, IC, IH, and IM.
- Includes market snapshot, technical structure, basic fundamental/flow context, research view, trade plan, risk notes, and missing-data disclosure.
- Uses TqSdk first when `TQSDK_USER` and `TQSDK_PASSWORD` are available.
- Uses AKShare/public data as fallback where available.

## Install

Copy this folder into your Codex skills directory:

```powershell
Copy-Item -Recurse . "$env:USERPROFILE\.codex\skills\analyze-china-futures"
```

Then invoke it in Codex:

```text
用 $analyze-china-futures 分析今天焦煤，生成 Markdown 日报，包含研究观点和交易计划，不编造缺失数据。
```

## Optional TqSdk Setup

Install Python dependencies:

```powershell
py -m pip install --user tqsdk akshare pandas numpy
```

Set TqSdk credentials as user environment variables:

```powershell
.\scripts\setup_tqsdk_env.ps1
```

The setup script prompts locally and does not print the password.

## Direct Script Usage

Fetch a snapshot:

```powershell
py .\scripts\fetch_china_futures_snapshot.py "焦煤" --out snapshot.json
```

Render a report:

```powershell
py .\scripts\render_daily_report.py snapshot.json --out report.md
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
