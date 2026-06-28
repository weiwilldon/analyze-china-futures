# Source Coverage Matrix

This matrix records which ready-made resources are used for each data gap. The rule is: use structured sources first, never fabricate missing fields, and keep classified errors in the snapshot.

| Field | Primary source | Fallback source | Optional professional source | Current behavior |
|---|---|---|---|---|
| Quotes / daily bars | TqSdk main continuous contract | AKShare daily / realtime functions | TqSdk account | Filled when TqSdk or AKShare supports the symbol |
| Basis / spot spread | AKShare `futures_spot_price` / `futures_spot_price_daily` | SMM H5 spot pages for AO/CU/AL/ZN/PB/NI/SN/LC/SI; 100ppi direct daily page with `HW_CHECK` cookie handling; 99qh `spot_price_qh`; manual CSV/JSON/XLS/XLSX exports | Vendor spot/basis feed such as Mysteel/SMM/Baiinfo/Lonzhong | Filled for products present on public spot sources or manual files; manual file names may use analysis date or latest effective market date; AO/CU/AL/ZN/PB/NI/SN/LC/SI basis can be computed from SMM spot average minus futures price; 99qh permission failures are classified as `auth_or_permission` |
| Inventory | AKShare `futures_inventory_em` | Code/name retry | Vendor inventory feed | Filled when Eastmoney inventory table covers the product |
| Warehouse receipt | Tushare Pro `fut_wsr` when configured | AKShare exchange functions; SHFE direct `www.shfe.com.cn/...dailystock.dat`; DCE `dlspjys.cn` publicweb mirror; GFEX JSON API; CZCE direct `FutureDataWhsheet.xls`; manual files | Exchange-authorized or vendor warehouse feed | SHFE direct path and DCE/GFEX public APIs can fill several blocked official paths; manual file names may use analysis date or latest effective market date; products absent from the table remain explicit gaps |
| Seat / member ranking | Tushare Pro `fut_holding` when configured | SHFE direct `www.shfe.com.cn/.../pmYYYYMMDD.dat`; AKShare exchange ranking functions; DCE `dlspjys.cn` publicweb mirror zip; GFEX JSON ranking APIs; CZCE direct `FutureDataHolding.xls`; manual files | Exchange-authorized or vendor member-position feed | SHFE/DCE/GFEX public APIs can fill several blocked official paths; manual file names may use analysis date or latest effective market date; products absent from the table remain explicit gaps |
| News / flash | Jin10 MCP `search_flash`, `search_news`, `list_flash`, `list_news`, `get_news` | Exchange notices and current source-backed web search for official events | Jin10 MCP token | Filled when `JIN10_MCP_TOKEN` is configured; MCP discovery uses `tools/list` and `resources/list`; list pagination uses `cursor` / `next_cursor` / `has_more`; results are de-duplicated and filtered for relevance; per-tool counts are saved in `news_coverage` |
| Macro calendar | Jin10 MCP `list_calendar` | Current web browsing with citation | Jin10 MCP token | Filled when Jin10 MCP is configured |

## Error Categories

- `no_data_for_date`: the official/public source reports no file or no data for that date.
- `blocked_by_exchange_waf`: an exchange endpoint rejects automated access, such as HTTP 412.
- `auth_or_permission`: a source exists but rejects the request due to token, permission, score, or HTTP 401.
- `dns_or_network_failure`: host resolution or network connection failed.
- `timeout`: the source did not respond in time.
- `parser_or_format_changed`: the endpoint responded, but the parser no longer matches the format.
- `source_error`: any other source failure.

## Completion Criteria

A report is considered data-complete only when quote, daily bars, basis, inventory or warehouse receipt where relevant, position ranking, and news/calendar are either filled or explicitly marked with a source and error category.

Use `scripts/probe_exchange_sources.py` to verify whether warehouse receipt and position-ranking exchange endpoints are currently reachable. This separates script/parser problems from source-side WAF, DNS, timeout, and no-data conditions.

Use `scripts/probe_tushare_sources.py` after setting `TUSHARE_TOKEN` to verify whether Tushare Pro `fut_wsr` and `fut_holding` can fill warehouse receipt and member-position gaps for the selected products.

Use `scripts/probe_jin10_sources.py` to verify Jin10 MCP `search_flash`, `search_news`, `list_flash`, `list_news`, and `list_calendar` availability and per-keyword item counts.

Use `scripts/diagnose_data_readiness.py` as the first-line diagnosis command. It combines local source checks, current data-gap audit, exchange endpoint probes, Tushare probes, Jin10 probes when configured, manual-data requests, and next-step recommendations in one Markdown report. Pass `--no-jin10` for a faster offline diagnosis.

## 2026-06 Coverage Update

| Field | Newly Added Ready-Made Source | Coverage Note |
|---|---|---|
| Warehouse receipt | AKShare `futures_inventory_em` aggregate fallback | Fills `warehouse_receipt` only when exchange/Tushare/manual warehouse details are absent. Marked as aggregate inventory/warehouse series, not warehouse-level registered receipt rows. |
| Seat / member ranking | EastMoney futures dragon-and-tiger board JSON (`getLongAndShortPosition`, `getVloumeInfo`) | Fills top volume, long open interest, short open interest, and changes by member/company. Exchange official and Tushare sources remain preferred. |
| News flow | Jin10 MCP full probe | Keeps `structuredContent` as primary machine-readable content and applies keyword relevance filtering. |
