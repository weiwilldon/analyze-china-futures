---
name: analyze-china-futures
description: Analyze China futures markets and produce intraday watch snapshots, Markdown daily reports, research views, trade plans, and contract comparisons for China commodity futures, stock index futures, and user-specified futures varieties. Use when Codex needs to analyze today's China futures market, monitor short-term intraday entry points, a named futures product such as 螺纹钢/沪铜/铁矿/豆粕/玻璃/焦煤/氧化铝, a contract code such as RB/CU/I/IF/FG/JM/AO, basis/inventory/open-interest context, technical levels, risk scenarios, or a research-backed trading plan.
---

# 中国期货分析助手

## 核心流程

使用本 Skill 分析用户指定的中国期货品种或合约。用户没有指定格式时，默认输出 Markdown 日报或简版研究报告。

### 盘中盯盘快路径

当用户要求“盘中”“盯盘”“每 5 分钟看一下”“有没有进场点”“短线点位”时，优先运行快速脚本，不要调用完整日报快照：

```powershell
py scripts/fetch_intraday_watch.py "焦煤" "玻璃" --wait-seconds 2 --format json
```

快路径只使用一次 TqSdk 批量连接抓取实时报价、买卖一档、日内高低点、成交量和持仓，跳过 AKShare、100ppi、交易所仓单/席位、Tushare 和 Jin10。它适合 5 分钟盯盘；若 TqSdk 不可用，明确说明快路径缺少实时行情，不要编造价格。完整复盘、日报、基本面、新闻或跨品种研究仍使用 `fetch_china_futures_snapshot.py`。

1. 解析用户输入的品种、合约和日期；日期缺省时使用 Asia/Shanghai 当天。
2. 读取 `references/data-sources.md`，优先使用可靠的实时或结构化数据，不用记忆和猜测补字段。
3. 运行 `scripts/fetch_china_futures_snapshot.py "<品种或合约>" --date YYYY-MM-DD` 生成结构化 JSON 快照。
4. 读取 `references/analysis-playbook.md`，按行情、技术、基本面、资金持仓、新闻、风险、结论拆解。
5. 如需稳定日报草稿，运行 `scripts/render_daily_report.py <snapshot.json>`，再基于用户意图做中文推理和风险总结。
6. 如果快照缺新闻、基差、库存、仓单、席位持仓或交易所公告，优先按 `references/data-gap-resources.md` 补充；仍不可得时明确标记缺口和影响。
7. 用户要求完整日报时，读取 `references/report-template.md` 保持输出结构稳定。

不要编造价格、合约、库存、仓单、基差、新闻或持仓。如果数据源不可用，要写明缺失原因和置信度影响。

## 输出标准

- 用户要求“分析”时，默认同时包含研究观点和交易计划，除非用户明确只要数据。
- 交易计划必须包含方向偏向、触发条件、止损、失效条件、目标/管理思路和风险提示。
- 明确标注结论基于完整数据、部分数据，还是定性推理。
- 优先采用脚本快照里的行情、技术位和数据缺口；不要用没有来源的记忆覆盖结构化字段。
- 如果脚本提供库存、仓单、基差、席位排名、新闻或财经日历，直接引用这些字段。
- 必须包含提示：`本内容仅供研究辅助，不构成投资建议。`
- 对比多个品种时，用相同字段逐一分析，最后给出相对强弱、最清晰的交易结构和关键风险。

## 脚本用法

获取快照：

```powershell
py scripts/fetch_china_futures_snapshot.py "螺纹钢" --date 2026-06-26 --out snapshot.json
```

盘中快速盯盘：

```powershell
py scripts/fetch_intraday_watch.py "焦煤" "玻璃" --wait-seconds 2 --format json
```

生成日报草稿：

```powershell
py scripts/render_daily_report.py snapshot.json --out report.md
```

检查本机数据源配置，不打印密钥：

```powershell
py scripts/check_data_sources.py --pretty
```

运行快速验证：

```powershell
py scripts/quick_validate.py
```

汇总诊断数据源和缺口：

```powershell
py scripts/diagnose_data_readiness.py FG JM AO --date 2026-06-27
```

生成手动数据补充清单：

```powershell
py scripts/prepare_manual_data_requests.py FG JM AO --date 2026-06-27
```

批量审计数据缺口：

```powershell
py scripts/audit_data_gaps.py FG JM AO --date 2026-06-27
```

审计基差、仓单、席位持仓、金十新闻流四类补齐目标的完成状态：

```powershell
py scripts/audit_completion_status.py FG JM AO LC SI --date 2026-06-27 --with-jin10-full
```

探测交易所仓单/席位公开入口：

```powershell
py scripts/probe_exchange_sources.py FG JM AO --date 2026-06-27
```

探测 Tushare Pro 仓单/席位接口：

```powershell
py scripts/probe_tushare_sources.py FG JM AO --date 2026-06-27
```

探测 Jin10 MCP 快讯/新闻/日历接口：

```powershell
py scripts/probe_jin10_sources.py FG JM AO
```

脚本会在可用时优先使用 TqSdk 与 Jin10 MCP，再补充 AKShare、100ppi、交易所公开数据和可选的 Tushare Pro。允许返回部分快照，但必须写明每个缺失字段的原因。

## 参考文件

- `references/data-sources.md`：数据优先级、来源行为和缺失规则。
- `references/data-gap-resources.md`：基差、仓单、席位持仓、完整新闻流的数据补全资源清单。
- `references/ready-made-resources.md`：现成数据资源矩阵，包含交易所、AKShare、Tushare、金十和手动文件兜底入口。
- `references/optional-pro-sources.md`：Tushare Pro、Jin10 MCP、TqSdk 的可选增强配置。
- `references/source-coverage-matrix.md`：字段覆盖范围和错误分类。
- `references/analysis-playbook.md`：分析角色和推理检查表。
- `references/usage-feedback.md`：实战盯盘后的缺点、缺漏和优化规则。
- `references/report-template.md`：稳定 Markdown 日报模板。

## 2026-06 数据补源更新

- `warehouse_receipt` 可在交易所仓单明细不可用时使用 AKShare `futures_inventory_em` 聚合库存/仓单日报序列兜底，必须标注 `aggregate` 口径。
- `position_rank` 可使用东方财富期货龙虎榜公开 JSON 接口兜底，补成交量、多头持仓、空头持仓及增减；交易所官方/Tushare Pro 仍优先。
- `news` 继续使用 Jin10 MCP，优先读取 `structuredContent`。
