# Contributing

Thanks for helping improve `analyze-china-futures`.

## Good Pull Requests

- Keep the Skill instructions concise.
- Do not add secrets, account IDs, tokens, or private trading data.
- Prefer structured data adapters over scraping fragile text when possible.
- Mark missing fields explicitly instead of estimating unsupported values.
- Add or update a small fixture/snapshot when changing report behavior.

## Validation

Before opening a pull request, run:

```powershell
py -m py_compile .\scripts\fetch_china_futures_snapshot.py .\scripts\render_daily_report.py
```

If Codex's skill validation script is available, also run it against the folder.
