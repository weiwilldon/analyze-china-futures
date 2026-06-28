# 数据缺口补全资源清单

本文记录本 Skill 针对基差、仓单、席位持仓和完整新闻流采用的现成资源。原则是：优先结构化接口，账号源只做增强，不因缺少账号而阻断日报生成；所有失败都要写入 `supplement_errors`，不能把缺失字段当作 0。

## 1. 基差 / 现货升贴水

优先级：

1. AKShare `futures_spot_price` / `futures_spot_price_daily`
2. 100ppi 每日基差页面 `https://www.100ppi.com/sf/day-YYYY-MM-DD.html`
3. 99期货 / 99qh `spot_price_qh`
4. 第三方专业现货数据源，如 Mysteel、SMM、百川盈孚、隆众资讯等，适合后续用付费账号扩展

当前脚本行为：

- 先调 AKShare，失败后访问 100ppi 页面。
- 100ppi 有 `HW_CHECK` 验证时自动处理 cookie 后再解析。
- 100ppi 无匹配行时尝试 99qh；若返回 HTTP 401 / `无权限访问`，按 `auth_or_permission` 记录。
- 100ppi 不覆盖的品种，例如某些新上市或产业链品种，会标记为 `source_error` 或 `no matching product rows returned`。

## 2. 仓单 / 注册仓单

优先级：

1. AKShare 交易所仓单函数：
   - SHFE：`futures_shfe_warehouse_receipt`
   - DCE：`futures_dce_warehouse_receipt`
   - CZCE：`futures_czce_warehouse_receipt`
   - GFEX：`futures_gfex_warehouse_receipt`
   - 通用注册仓单：`get_receipt(start_date, end_date, vars_list=[code])`
2. 交易所公开文件：
   - CZCE：`FutureDataWhsheet.xls`
   - SHFE/DCE/GFEX：公开网页或数据文件，若网络/WAF 允许可继续扩展直连解析
3. Tushare Pro `fut_wsr`

当前脚本行为：

- 先使用可公开访问的 AKShare/交易所数据。
- 专用仓单函数失败后，再用 AKShare `get_receipt` 做通用注册仓单兜底。
- CZCE 额外尝试官方静态 Excel 文件。
- DCE 官网被 HTTP 412 拦截时，额外尝试 `www.dlspjys.cn/publicweb/quotesdata/wbillWeeklyQuotes.html` 镜像入口；若品种在仓单表没有匹配行，仍按真实缺口记录，不写成 0。
- SHFE 旧 `tsite` 域名 DNS 失败时，额外尝试 `https://www.shfe.com.cn/data/tradedata/future/dailydata/YYYYMMDDdailystock.dat` JSON 文件，严格按 `VARID` 匹配品种，避免把英文仓库名里的字母误判为品种代码。
- 如配置 `TUSHARE_TOKEN` 且安装 `tushare`，会优先用 Tushare Pro 补仓单。
- DCE 公开接口可能返回 HTTP 412，SHFE 旧接口可能 DNS 失败；这些按真实错误分类，不伪造仓单。

## 3. 席位持仓 / 会员成交持仓排名

优先级：

1. AKShare 交易所席位排名函数：
   - SHFE：`get_shfe_rank_table`
   - DCE：`get_dce_rank_table`，备选 `futures_dce_position_rank`
   - CZCE：`get_czce_rank_table`
   - GFEX：`futures_gfex_position_rank`
   - 汇总备选：`get_rank_sum_daily`
2. 交易所公开文件：
   - CZCE：`FutureDataHolding.xls`
3. Tushare Pro `fut_holding`

当前脚本行为：

- 对指定品种在最近若干日期内回看，寻找交易所已发布的排名数据。
- CZCE 额外尝试官方静态 Excel 文件。
- DCE 官网被 HTTP 412 拦截时，额外尝试 `www.dlspjys.cn/publicweb/quotesdata/exportMemberDealPosiQuotesBatchData.html` 镜像 zip；已验证可解析会员名、成交量、持买单量、持卖单量和增减字段。
- GFEX 使用交易所 JSON API：`loadListContract_id` 获取合约列表，`loadList` 按 `data_type=1/2/3` 获取成交量、持买、持卖排名。
- 如配置 `TUSHARE_TOKEN`，用 Tushare Pro 作为公开源被拦截时的增强来源。
- 未取到时保留 `position_rank` 缺口，并写明是无数据、WAF、网络、解析变化还是源错误。

## 4. 完整新闻流 / 快讯 / 财经日历

优先级：

1. Jin10 MCP：
   - `search_flash({ keyword })`
   - `list_flash({ cursor })`
   - `search_news({ keyword, cursor })`
   - `get_news({ id })`
   - `list_calendar({})`
2. 交易所公告，用于保证金、手续费、涨跌停、交割、异常交易等官方事件
3. 行业资讯源，如 Mysteel、SMM、隆众、百川盈孚等，适合付费增强

当前脚本行为：

- 使用标准 MCP 流程连接 Jin10，优先读取 `structuredContent`。
- 先按品种关键词搜索快讯，再补搜索资讯和最新快讯流。
- 最新快讯流按标准分页字段 `cursor` / `next_cursor` / `has_more` 翻页，默认最多取两页，避免一次日报过重。
- 对 `list_flash` 这类全市场流做品种关键词相关性过滤，避免把无关新闻混进期货日报。
- 对 `id`、`url` 和正文片段去重，避免搜索流、资讯流和最新流重复计入。
- 读取财经日历作为宏观事件风险。
- 新闻只作为已验证信息来源，不把无关股票概念新闻当成期货基本面。

## 5. 本机当前配置状态

用下面命令检查，不会打印任何 token 或密码：

```powershell
py scripts/check_data_sources.py --pretty --network
```

当前设计下：

- 无账号：行情、技术、部分库存、部分基差、部分公开仓单/席位、缺口说明可用。
- 有 TqSdk：行情和历史 K 线显著增强。
- 有 Jin10 MCP：新闻、快讯和财经日历增强。
- 有 Tushare Pro：仓单和席位持仓覆盖率显著增强，尤其用于公开交易所接口被拦截时。

## 6. 手动文件兜底

当交易所官网必须通过浏览器下载，或 Mysteel、SMM、百川盈孚、隆众、Wind、Choice 等供应商只能导出文件时，可以把下载结果放进 `manual-data/`，脚本会自动补缺失字段。

非交易日或周末报告可以使用诊断里显示的有效行情日命名文件，例如报告日期是 `2026-06-28`、有效行情日是 `2026-06-26` 时，`20260626_FG_position_rank.csv` 会被自动匹配。

可用目录：

- 当前运行目录下的 `manual-data/`
- Skill 根目录下的 `manual-data/`
- 环境变量 `CHINA_FUTURES_MANUAL_DATA_DIR` 指向的目录，多个目录用系统路径分隔符分开

支持格式：

- `.json`
- `.csv`
- `.xls`
- `.xlsx`

文件名需要同时包含日期、品种代码或中文名、字段类型。例如：

- `20260626_AO_warehouse_receipt.xlsx`
- `2026-06-26_氧化铝_仓单.csv`
- `20260626_JM_position_rank.json`
- `20260626_FG_basis.csv`

字段类型关键词：

- 基差：`basis`、`spot_basis`、`基差`、`现货`
- 仓单：`warehouse`、`warehouse_receipt`、`仓单`、`注册仓单`
- 席位持仓：`position`、`position_rank`、`holding`、`rank`、`席位`、`持仓`、`排名`

脚本只用手动文件补缺失字段，不覆盖已经从 Tushare、AKShare、交易所公开接口或 100ppi 取到的数据。

## 7. 尚未完全解决的限制

- DCE、SHFE、GFEX 的公开网页可能存在 WAF、DNS、动态页面或格式变化，单靠免费公开接口不能保证每天稳定抓全。
- Tushare Pro 需要 `TUSHARE_TOKEN`，当前没有 token 时只能验证模块存在，不能验证仓单/席位实盘返回。
- 100ppi 并不覆盖所有期货品种，缺失品种需要接入 Mysteel、SMM 等产业数据库才能达到更完整的基差覆盖。

## 2026-06 补充接入

- 仓单兜底：当交易所分仓库仓单、AKShare 专用仓单函数、Tushare Pro 都不可用时，脚本会使用 AKShare `futures_inventory_em` 的公开库存/仓单日报聚合序列补齐 `warehouse_receipt`，并写入 `granularity=aggregate`、`quality=aggregate_inventory_or_receipt_series`。该口径只代表聚合库存/仓单序列，不冒充分仓库注册仓单明细。
- 席位持仓兜底：脚本新增东方财富期货龙虎榜 JSON 接口 `https://qhhqzl.eastmoney.com/marketFutuWeb/dragonAndTigerInfo/getLongAndShortPosition` 与 `getVloumeInfo`，用 `contract`、`market`、`date` 参数获取成交量、多头持仓、空头持仓及增减。交易所官方排名和 Tushare Pro 仍优先，东方财富作为公开第三方补充源。
- 完成度审计：`scripts/audit_completion_status.py FG JM AO LC SI --date 2026-06-29 --with-jin10-full` 已验证四类核心缺口 `spot_basis / warehouse_receipt / position_rank / news` 在该样本中均可自动补齐。
