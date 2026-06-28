# manual-data

Put manually downloaded or vendor-exported supplement files here when public automated endpoints are blocked.

Supported formats:

- `.json`
- `.csv`
- `.xls`
- `.xlsx`

CSV files can be UTF-8 or common Chinese encodings such as GBK/GB18030. Excel workbooks may contain multiple sheets; the fetch script reads non-empty sheets together. Common Chinese export columns such as `成交量`, `持买单量`, `持卖单量`, `仓单`, `注册仓单`, `现货`, and `基差` are accepted.

Filename pattern:

- Include the date: `YYYYMMDD` or `YYYY-MM-DD`
- Include the product code or Chinese product name
- Include the field kind

Examples:

- `20260626_AO_warehouse_receipt.xlsx`
- `2026-06-26_氧化铝_仓单.csv`
- `20260626_JM_position_rank.json`
- `20260626_FG_basis.csv`

Use the files in `templates/` as column examples:

- `templates/basis_template.csv`
- `templates/warehouse_receipt_template.csv`
- `templates/position_rank_template.csv`

Generate suggested filenames for current missing fields:

```powershell
py scripts/prepare_manual_data_requests.py FG JM AO --date 2026-06-27
```

The fetch script only uses these files to fill missing fields. It does not overwrite data already collected from Tushare, AKShare, exchange public sources, 100ppi, TqSdk, or Jin10 MCP.

Real exported data files in this directory are ignored by Git by default. Only this README and the template files are intended to be versioned.
