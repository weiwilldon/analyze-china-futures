# Optional Professional Data Sources

This skill works without paid accounts, but some public exchange endpoints are rate-limited, WAF-protected, or unavailable for certain dates. Use these optional sources when warehouse receipts or member rankings must be more complete.

Run this first to see what is configured locally:

```powershell
py scripts/check_data_sources.py --pretty
```

Add `--network` to verify the Jin10 MCP handshake without printing the token.

## Tushare Pro

Best use:

- Warehouse receipts: `fut_wsr`
- Member holding / volume ranking: `fut_holding`

Setup:

```powershell
py -m pip install tushare
[Environment]::SetEnvironmentVariable("TUSHARE_TOKEN", "your_token_here", "User")
```

Or use the bundled helper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_tushare_env.ps1 -Token "your_token_here"
```

Runtime behavior:

- If `TUSHARE_TOKEN` is set and `tushare` is importable, `fetch_china_futures_snapshot.py` tries Tushare before public exchange fallback for `warehouse_receipt` and `position_rank`.
- Use `--no-tushare` or set `CHINA_FUTURES_SKIP_TUSHARE=1` to skip it.
- If Tushare returns no rows, the script records the gap and continues.

## Jin10 MCP

Best use:

- Flash stream: `search_flash`, `list_flash`
- News stream: `search_news`, `list_news`, `get_news`
- Macro/event risk: `list_calendar`

Runtime behavior:

- Uses `JIN10_MCP_TOKEN` via the configured MCP service.
- Reads `structuredContent` first.
- Runs the standard MCP setup/list flow before tool calls: `initialize`, `notifications/initialized`, `tools/list`, and `resources/list`.
- Snapshot fetching uses Jin10 by default when `JIN10_MCP_TOKEN` is present. `diagnose_data_readiness.py` also includes Jin10 by default, so news coverage is not incorrectly reported as missing on configured machines.
- `list_flash` and `list_news` are paged with `cursor` / `next_cursor` / `has_more` and filtered by product keywords before entering a report.
- Each snapshot writes a `news_coverage` object with per-tool counts, pagination state, and errors for `search_flash`, `search_news`, `list_flash`, `list_news`, `get_news`, and `list_calendar`.
- HTTP fallback client uses retries for transient TLS/timeout failures. Tune with `JIN10_MCP_TIMEOUT_SECONDS` and `JIN10_MCP_RETRIES` if your network is slow.
- Tune news breadth with `CHINA_FUTURES_JIN10_FLASH_PAGES` and `CHINA_FUTURES_JIN10_NEWS_PAGES`; both default to `1`.
- Tune article detail fetches with `CHINA_FUTURES_JIN10_DETAIL_COUNT`; it defaults to `1`. Set `CHINA_FUTURES_JIN10_INCLUDE_DETAILS=0` to skip detail calls.
- Use `--no-jin10` or set `CHINA_FUTURES_SKIP_JIN10=1` to skip it.

## TqSdk

Best use:

- Main/continuous quotes
- Daily bars
- Intraday market context

Runtime behavior:

- Uses `TQSDK_USER` and `TQSDK_PASSWORD`.
- Use `--no-tqsdk` to skip it.
