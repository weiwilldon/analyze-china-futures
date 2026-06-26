# Data Sources

## Priority

1. Use TqSdk when it is importable and credentials/configuration are available. Prefer it for real-time quotes, continuous main contracts, and intraday or daily bars.
2. Use public data libraries such as AKShare when TqSdk is unavailable. Prefer exchange or official fields when they are exposed by the library.
3. Use official exchange websites or current web sources for announcements, inventory, warehouse receipts, and news when the user needs those fields and scripts do not provide them.
4. If no reliable source returns a field, set it to missing and explain the impact. Never backfill with guessed values.

## TqSdk Handling

- Detect TqSdk by import, not by assuming installation.
- Treat credentials as optional. Common environment variables are `TQSDK_USER` and `TQSDK_PASSWORD`; if they are absent, skip TqSdk without failing the whole report.
- Use continuous main contracts when the user names a variety rather than an exact contract. For example, map 螺纹钢/RB to `KQ.m@SHFE.rb` when possible.
- When TqSdk quote fields omit daily change or high/low, enrich them from the latest daily bar if it is available and mark the source detail.
- Close API sessions after fetching data.

## Public Source Handling

- Try AKShare dynamically because function names and signatures can change.
- Capture source names, errors, and missing fields in the JSON snapshot.
- Prefer data freshness over breadth for daily reports. A partial current quote is more useful than stale complete data.

## Missing Data Rules

- Use `null` for missing numeric fields in JSON.
- Add a short reason in `missing_reasons`.
- In the final report, say whether missing data weakens trend, basis, inventory, position, or news confidence.
- Use source-backed browsing for missing news, basis, inventory, or warehouse receipt context when the user wants a final daily report. Cite every external source used.
- Do not create synthetic prices, open interest, inventory, basis, or news.

## Product Normalization

Accept Chinese names, pinyin-style aliases, uppercase/lowercase contract prefixes, and exact contract codes. If the input is ambiguous, ask the user for the exchange or contract before producing a trade plan.
