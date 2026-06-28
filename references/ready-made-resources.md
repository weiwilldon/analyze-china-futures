# 现成数据资源矩阵

本文列出用于补齐基差、仓单、席位持仓和新闻流的现成资源。优先级不是“越贵越好”，而是按自动化稳定性、结构化程度、可验证性排序。

## 总览

| 数据缺口 | 首选自动源 | 免费/公开补充 | 账号或付费增强 | 手动兜底 |
|---|---|---|---|---|
| 基差 / 现货升贴水 | AKShare `futures_spot_price` / `futures_spot_price_daily` | 100ppi 每日基差页 | Mysteel、SMM、百川盈孚、隆众、Wind、Choice | `manual-data/*basis*.csv/xlsx/json` |
| 仓单 / 注册仓单 | Tushare Pro `fut_wsr`，若配置 token | SHFE/DCE/CZCE/GFEX 官网仓单日报、AKShare 仓单函数 | 交易所授权数据、产业数据库、Wind、Choice | `manual-data/*warehouse*.csv/xlsx/json` |
| 席位持仓 / 会员排名 | Tushare Pro `fut_holding`，若配置 token | SHFE/DCE/CZCE/GFEX 日成交持仓排名、AKShare 排名函数 | 交易所授权数据、Wind、Choice | `manual-data/*position*.csv/xlsx/json` |
| 新闻 / 快讯 / 日历 | Jin10 MCP | 交易所公告、公开新闻页 | 金十、财联社、Wind、Choice、产业资讯终端 | 暂不建议手动导入新闻，报告中引用源链接更清楚 |

## 官方与主要文档入口

- Tushare Pro 权限/期货接口总览：`https://tushare.pro/document/1?doc_id=108`
- Tushare Pro 每日成交持仓排名 `fut_holding`：`https://tushare.pro/wctapi/documents/139.md`
- AKShare 快速入门和接口索引：`https://akshare.akfamily.xyz/tutorial.html`
- AKShare 期货数据文档：`https://akshare.akfamily.xyz/data/futures/futures.html`
- SHFE 仓单日报：`https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/?query_params=dailystock`
- SHFE 仓单 JSON：`https://www.shfe.com.cn/data/tradedata/future/dailydata/YYYYMMDDdailystock.dat`
- SHFE 席位持仓 JSON：`https://www.shfe.com.cn/data/tradedata/future/dailydata/pmYYYYMMDD.dat`
- SHFE 日周数据入口：`https://www.shfe.com.cn/reports/tradedata/`
- DCE 仓单日报：`https://www.dce.com.cn/dalianshangpin/xqsj/tjsj26/rtj/cdrb/index.html`
- DCE 日成交持仓排名：`https://www.dce.com.cn/dalianshangpin/xqsj/tjsj26/rtj/rcjccpm/index.html`
- DCE publicweb 镜像仓单：`http://www.dlspjys.cn/publicweb/quotesdata/wbillWeeklyQuotes.html`
- DCE publicweb 镜像席位持仓：`http://www.dlspjys.cn/publicweb/quotesdata/exportMemberDealPosiQuotesBatchData.html`
- CZCE 仓单日报：`https://www.czce.com.cn/cn/jysj/cdrb/H077003010index_1.htm`
- GFEX 仓单日报：`https://www.gfex.com.cn/gfex/cdrb/hqsj_tjsj.shtml`
- GFEX 仓单 API：`http://www.gfex.com.cn/u/interfacesWebTdWbillWeeklyQuotes/loadList`
- GFEX 席位合约列表 API：`http://www.gfex.com.cn/u/interfacesWebTiMemberDealPosiQuotes/loadListContract_id`
- GFEX 席位排名 API：`http://www.gfex.com.cn/u/interfacesWebTiMemberDealPosiQuotes/loadList`

## 接入取舍

### 免费公开源

适合无账号运行和日常兜底。缺点是交易所页面可能有 WAF、DNS、动态页面或格式变化，不能保证机器每天稳定抓全。

### Tushare Pro

适合补仓单和席位持仓。脚本在 `TUSHARE_TOKEN` 存在时优先尝试：

- `fut_wsr`：仓单日报
- `fut_holding`：每日成交持仓排名

该源需要账号权限。当前本机已经安装 `tushare` 包，但没有配置 `TUSHARE_TOKEN`，所以只能验证模块存在，不能验证真实返回。

### Jin10 MCP

适合补新闻、快讯、宏观日历。脚本使用标准 MCP 流程，并优先读取 `structuredContent`。列表分页遵循：

- 请求参数：`cursor`
- 响应字段：`data.next_cursor`
- 是否还有更多：`data.has_more`

### 手动文件

适合交易所官网需要浏览器下载，或供应商只能导出文件的场景。把文件放到 `manual-data/` 后，脚本自动补缺失字段。模板在 `manual-data/templates/`。

## 当前落地状态

- 已接入并验证：TqSdk、AKShare、100ppi、Jin10 MCP、手动文件导入。
- 已接入但未实盘验证：Tushare Pro 仓单/席位，因为缺 `TUSHARE_TOKEN`。
- 不建议继续强抓：被 WAF 拦截的交易所页面。更稳的方式是 Tushare Pro、交易所授权数据、供应商导出或浏览器手动下载后放入 `manual-data/`。

## 2026-06 新增公开补源

- `warehouse_receipt` 新增 AKShare `futures_inventory_em` 聚合兜底：当分仓库仓单不可用时，以公开库存/仓单日报聚合序列补齐字段，写明 `aggregate` 口径。
- `position_rank` 新增东方财富期货龙虎榜公开 JSON：`qhhqzl.eastmoney.com/marketFutuWeb/dragonAndTigerInfo/getLongAndShortPosition` 和 `getVloumeInfo`，用于补成交量、多头持仓、空头持仓及增减。
- `news` 继续以 Jin10 MCP 为主，列表分页仍按 `cursor / data.next_cursor / data.has_more`。
