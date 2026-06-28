# Data Sources

For a field-by-field list of ready-made resources that fill basis, warehouse receipts, member positions, and news flow, see `data-gap-resources.md`.

## Priority

1. Use TqSdk when it is importable and credentials/configuration are available. Prefer it for real-time quotes, continuous main contracts, and intraday or daily bars.
2. Use public data libraries such as AKShare when TqSdk is unavailable. Prefer exchange or official fields when they are exposed by the library.
3. Use official exchange websites or current web sources for announcements, inventory, warehouse receipts, and news when the user needs those fields and scripts do not provide them.
4. If no reliable source returns a field, set it to missing and explain the impact. Never backfill with guessed values.

## TqSdk Handling

- Detect TqSdk by import, not by assuming installation.
- Treat credentials as optional. Common environment variables are `TQSDK_USER` and `TQSDK_PASSWORD`; if they are absent, skip TqSdk without failing the whole report.
- Use continuous main contracts when the user names a variety rather than an exact contract. For example, map 螺纹钢/RB to `KQ.m@SHFE.rb` when possible.
- Use uppercase product codes for CZCE and CFFEX continuous contracts, such as `KQ.m@CZCE.FG`; use lowercase for SHFE/DCE/INE where TqSdk expects lowercase, such as `KQ.m@DCE.jm`.
- When TqSdk quote fields omit daily change or high/low, enrich them from the latest daily bar if it is available and mark the source detail.
- Close API sessions after fetching data.

## Public Source Handling

- Try AKShare dynamically because function names and signatures can change.
- Capture source names, errors, and missing fields in the JSON snapshot.
- Prefer data freshness over breadth for daily reports. A partial current quote is more useful than stale complete data.
- Use `futures_inventory_em` for inventory, `futures_czce_warehouse_receipt` for CZCE warehouse receipts, and `futures_spot_price`/`futures_spot_price_daily` for spot/basis when available.

## Gap Supplement Resources

- Basis / spot-futures spread: use AKShare `futures_spot_price` and `futures_spot_price_daily`, which wrap 100ppi spot/basis data. For SMM-supported products, use SMM H5 structured Next.js spot data and compute `basis = SMM spot average - futures price` from the snapshot quote or daily close. Current SMM mappings include AO / 氧化铝 (`https://hq.smm.cn/h5/SMM-alumina-price`), CU / 沪铜 (`https://hq.smm.cn/h5/cu`), AL / 沪铝 (`https://hq.smm.cn/h5/alu`), ZN / 沪锌 (`https://hq.smm.cn/h5/zn`), PB / 沪铅 (`https://hq.smm.cn/h5/pb`), NI / 沪镍 (`https://hq.smm.cn/h5/ni`), SN / 沪锡 (`https://hq.smm.cn/h5/sn`), LC / 碳酸锂 (`https://hq.smm.cn/h5/Li2CO3`), and SI / 工业硅 (`https://hq.smm.cn/h5/si`). If AKShare rejects the date or returns no rows, use the direct 100ppi daily page (`https://www.100ppi.com/sf/day-YYYY-MM-DD.html`) and handle its `HW_CHECK` cookie challenge before parsing the commodity row. If 100ppi has no matching row, try 99 Futures / 99qh `spot_price_qh` for products it lists, such as some SHFE varieties. Treat 99qh HTTP 401 / "无权限访问" as `auth_or_permission`, not as a fabricated zero basis. Treat products absent from all public spot/basis sources as a real data gap.
- Basis lookback is intentionally shorter than warehouse/position lookback because public spot pages are slow and often do not cover every futures variety. Tune it with `CHINA_FUTURES_BASIS_LOOKBACK_DAYS` (default `3`). For slow or blocked networks, set `CHINA_FUTURES_SKIP_AKSHARE_BASIS=1` or `CHINA_FUTURES_SKIP_99QH_BASIS=1`; the snapshot must then mark `spot_basis` as missing instead of inventing a value.
- Warehouse receipts: use exchange public data through AKShare:
  - SHFE: `futures_shfe_warehouse_receipt`
  - DCE: `futures_dce_warehouse_receipt`
  - CZCE: `futures_czce_warehouse_receipt`
  - GFEX: `futures_gfex_warehouse_receipt`
  - General fallback: `get_receipt(start_date, end_date, vars_list=[code])`
  - CZCE fallback: direct Excel files under `http://www.czce.com.cn/cn/DFSStaticFiles/Future/YYYY/YYYYMMDD/FutureDataWhsheet.xls`.
  - SHFE fallback: direct JSON files under `https://www.shfe.com.cn/data/tradedata/future/dailydata/YYYYMMDDdailystock.dat`, matched strictly by `VARID`.
- Member position rankings / seat flow: use exchange public top-member ranking data through AKShare:
  - SHFE: direct JSON files under `https://www.shfe.com.cn/data/tradedata/future/dailydata/pmYYYYMMDD.dat`; fallback `get_shfe_rank_table` only when explicitly enabled.
  - DCE: `get_dce_rank_table`, fallback `futures_dce_position_rank`
  - CZCE: `get_czce_rank_table`
  - GFEX: `futures_gfex_position_rank`
  - Cross-exchange summary fallback: `get_rank_sum_daily`
  - CZCE fallback: direct Excel files under `http://www.czce.com.cn/cn/DFSStaticFiles/Future/YYYY/YYYYMMDD/FutureDataHolding.xls`.
  - SHFE legacy `tsite/kx/pmYYYYMMDD.dat` rank endpoints are skipped by default to avoid slow DNS/404 failures during daily report generation. Set `CHINA_FUTURES_TRY_LEGACY_SHFE_RANK=1` only when explicitly testing the old AKShare/SHFE rank path.
- News / macro flow: use Jin10 MCP when `JIN10_MCP_TOKEN` is configured. Follow the standard MCP sequence (`initialize`, `notifications/initialized`, `tools/list`, `resources/list`, then `tools/call`) and read `result.structuredContent` first for tool calls. Prefer `search_flash` for real-time catalysts, `search_news` / `get_news` for longer context, `list_flash` and `list_news` for latest streams, and `list_calendar` for scheduled macro event risk. Snapshot JSON records `news_coverage` so reports can show which Jin10 tools were actually reached.
- Official exchange announcements remain the tie-breaker for delivery, margin, fee, limit, warehouse, and abnormal trading notices.

## Public Interface Limits

- DCE public warehouse/position endpoints may return HTTP 412 from some networks or user agents. Treat this as `blocked_by_exchange_waf`, not as zero warehouse receipts or zero positions.
- When DCE official `www.dce.com.cn` returns HTTP 412, use the public DCE mirror domain `www.dlspjys.cn` for the same `publicweb/quotesdata` endpoints:
  - warehouse receipt mirror: `http://www.dlspjys.cn/publicweb/quotesdata/wbillWeeklyQuotes.html`
  - member position mirror: `http://www.dlspjys.cn/publicweb/quotesdata/exportMemberDealPosiQuotesBatchData.html`
  The mirror should still be treated as exchange-public data and parsed conservatively; if a product has no matching warehouse rows, keep the warehouse gap instead of reporting zero.
- SHFE legacy `tsite.shfe.com.cn` data files may fail with DNS/network errors in some environments. For warehouse receipts, use the newer `www.shfe.com.cn/data/tradedata/future/dailydata/YYYYMMDDdailystock.dat` JSON path. For member ranking, use `www.shfe.com.cn/data/tradedata/future/dailydata/pmYYYYMMDD.dat`; the older `kx/pmYYYYMMDD.dat` path can return 404.
- CZCE static Excel files are reliable for historical dates when the exchange publishes the file; HTTP 404 / "当日无数据" means no file is available for that date.
- GFEX public endpoints are structured JSON APIs for warehouse receipts and member rankings. Use `u/interfacesWebTdWbillWeeklyQuotes/loadList` for warehouse receipts, `u/interfacesWebTiMemberDealPosiQuotes/loadListContract_id` for contract lists, and `u/interfacesWebTiMemberDealPosiQuotes/loadList` for rank data.

## Optional Professional Sources

- TqSdk should remain the preferred account-based enhancement for quotes and history. If warehouse receipt or seat-ranking products are required intraday, consider adding a paid data vendor or exchange-authorized feed rather than scraping blocked public endpoints.
- Tushare Pro is the preferred optional enhancement for warehouse receipts and member ranking when public exchange endpoints are blocked:
  - `fut_wsr`: futures warehouse receipt daily data
  - `fut_holding`: futures member holding / volume ranking
  - Configure with `TUSHARE_TOKEN`; install the `tushare` Python package. The script treats it as optional and continues without it.
- Jin10 MCP is appropriate for flash/news/calendar context, but it is not a substitute for official exchange warehouse receipts or member rankings.
- When public exchange endpoints are blocked, keep the field missing with the classified error and cite the official resource path users can verify manually.

## Missing Data Rules

- Use `null` for missing numeric fields in JSON.
- Add a short reason in `missing_reasons`.
- Keep `data_completeness` in the snapshot so downstream reports can show machine-readable field status, source, and error category.
- In the final report, say whether missing data weakens trend, basis, inventory, position, or news confidence.
- Use source-backed browsing for missing news, basis, inventory, or warehouse receipt context when the user wants a final daily report. Cite every external source used.
- Do not create synthetic prices, open interest, inventory, basis, or news.

## Non-Trading Days

- When the analysis date has no same-day market data, keep `metadata.analysis_date` as the user-requested date and set `metadata.effective_market_date` to the latest date actually found in quote, bars, basis, inventory, warehouse receipt, or position data.
- When the user requests a historical date, do not let newer quote, inventory, basis, warehouse, or position rows move `effective_market_date` beyond the requested analysis date. Keep newer rows visible as source context when useful, but do not treat them as same-day evidence.
- Add a warning when `effective_market_date` differs from `analysis_date`.
- Treat exchange "no data for date" on weekends or holidays as a date-availability issue, not as zero warehouse receipt, zero basis, or zero position.
- Reports should show both the requested analysis date and the effective market date.

## Product Normalization

Accept Chinese names, pinyin-style aliases, uppercase/lowercase contract prefixes, and exact contract codes. If the input is ambiguous, ask the user for the exchange or contract before producing a trade plan.
