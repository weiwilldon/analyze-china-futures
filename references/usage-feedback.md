# Usage Feedback And Remediation

Use this note when improving the skill after live trading or heartbeat use.

## Problems Observed

- Live watch checks used the full daily-report snapshot path, so each short update also fetched basis, inventory, warehouse receipts, position ranks, news, and macro calendar.
- Multiple products were fetched sequentially, creating repeated TqSdk sessions and repeated public-data fallbacks.
- TqSdk INFO output could pollute stdout, making JSON parsing brittle in automations.
- Exact contract handling needed to preserve the requested contract label instead of falling back to a generic main-contract label.
- Fast trading updates need different confidence language from daily research: quote-only data is useful for triggers, not for full fundamental conviction.

## Remediation

- Use `scripts/fetch_intraday_watch.py` for heartbeat/盘中盯盘/短线点位 tasks.
- Keep `scripts/fetch_china_futures_snapshot.py` for reports, research views, fundamental checks, and contract comparisons.
- Batch all watch instruments into one command, for example:

```powershell
py scripts/fetch_intraday_watch.py "焦煤" "玻璃" --wait-seconds 2 --format json
```

- For watch outputs, state entry trigger, invalidation/stop, and "无进场点，继续等" when no clear setup exists. Do not expand into a full report unless the user asks.
- Always keep the disclaimer: `本内容仅供研究辅助，不构成投资建议。`
