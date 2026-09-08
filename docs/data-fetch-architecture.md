# 跨市场数据抓取架构

## 三层保障机制

为避免单点故障导致晨间报告缺失海外数据，采用三层递进式抓取架构：

```
Layer 1: GitHub Actions       05:00    cross-market.yml → data-snapshots/
Layer 2: 本机调度              06:00/07:00  检查并补抓
Layer 3: 报告流水线             07:00    Windows morning_pipeline.ps1 → 选股预览 + morning-report → 代码投递
```

### Layer 1：GitHub Actions 主路径

文件：`.github/workflows/cross-market.yml`
时间：工作日 05:00 中国标准时间（CST）（协调世界时（UTC） 21:00 前一日）
机制：使用 yfinance 从 GitHub runner 抓取美股、日韩半导体、商品、宏观指标，写入 `data-snapshots/` 并 commit 回仓库。

数据覆盖：
- 美股 Mag7 + 半导体（NVDA, AMD, AVGO, TSLA, AAPL, MSFT, GOOGL, AMZN, META）
- 日韩半导体核心标的（Tokyo Electron, Advantest, Samsung, SK Hynix 等）
- 基准指数（SPY, QQQ, SMH, ^N225, ^KS11）
- 商品（GC=F, SLV, GLD）
- 宏观（DXY, VIX via FRED, 10Y via FRED）
- 情绪（AAII, CBOE/VIX）

输出位置：
- `data-snapshots/cross-market/YYYY-MM-DD.json`
- `data-snapshots/latest/cross_market_snapshot.json`
- `data-snapshots/latest/cross_market_snapshot.md`

### Layer 2：本机调度检查快照，必要时实时补抓

Linux 文件：`scripts/local_fetch_cross_market.sh`
Linux 时间：工作日 06:00 CST
Linux systemd 单元：`~/.config/systemd/user/local-fetch-cross-market.{service,timer}`
Windows 文件：`scripts/windows/morning_pipeline.ps1`
Windows 时间：工作日 07:00 CST

Linux 安装使用 `scripts/setup_cron.sh --layer2` 渲染 `scripts/systemd/*.service` 模板。Windows 安装使用 `scripts/windows/install_scheduled_tasks.ps1 -Force` 注册 Task Scheduler 任务。

流程：
1. `git pull` 获取 Layer 1 的最新快照
2. 执行 `fallback_fetch.py`：
   - 检查 `data-snapshots/` 是否有匹配快照
   - 有匹配快照时直接使用，标记 `_source: data-snapshots`
   - 缺失或超过 2 天时，本地通过 yfinance 实时补抓，可走 mihomo 代理 `127.0.0.1:7890`

日志：`~/.hermes/logs/local_fetch_cross_market.log`

### Layer 3：报告流水线，报告前最后补充

Windows 主链路：`Market Intel Morning`，工作日 07:00 CST
- 执行 `scripts/windows/morning_pipeline.ps1` → hotsector 选股预览 → `a-share-daily morning` → `a-share-daily morning-report`
- `a-share-daily morning` 内部调用 `cross_market.py run()`，该函数：
  1. 先检查 `data-snapshots/`（Layer 1/2 应已完成）
  2. 快照不可用时，触发实时抓取
- 数据仍不可用时，报告会标注缺失项并继续发送。

Hermes 日更定时任务默认保持暂停，仅作为人工补发或临时接管入口。不要和 Windows `Market Intel Morning` 同时启用。

## 亚洲市场数据保障

晚报侧使用同样的三层思路：

```
Layer 1: GitHub Actions tushare-daily       09:30  → 轻量 TuShare 快照写入 data-snapshots/
Layer 2: 本机调度                            17:30/18:00/18:20/18:40  → 刷新完整 TuShare 与日韩相关数据
Layer 3: Windows evening pipeline           19:00  → evening_pipeline.ps1 → 图表/文字 → 代码投递
```

`evening_pipeline.sh` 会先运行数据刷新和图表生成。高权限 TuShare 数据默认关闭时，会跳过热点主题和 `moneyflow_ths` 图。设置 `A_SHARE_ENABLE_TUSHARE_PREMIUM=1` 后，缺少当日热点主题或 `moneyflow_ths` 时会生成中文占位图，避免发送上一交易日残留图片。晚报投递端优先读取 `evening_manifest.json` 中的图表路径，只发送本次运行产物。

## 时间轴全景

```
北京时间（CST, UTC+8）
──────────────────────────────────────────────────────────────
00:00  美股交易中
04:00  美股收盘（夏令 EDT 16:00）
05:00  [Layer 1] GitHub Actions cross-market.yml 执行
06:00  [Layer 2] Linux 本地 systemd timer 执行
07:00  [Windows] Market Intel Morning 执行，发送选股预览和晨报（日韩 08:00 开盘前1h）
08:00  日韩开盘
09:00  台湾开盘
09:30  A股开盘
────── 亚洲交易时段 ──────────────────────────────────────
13:30  台湾收盘
14:00  日本收盘
14:30  韩国收盘
15:00  A股收盘
16:00  美股盘前开始
17:30  [Layer 2] A-share / Asia 核心数据刷新
18:00  [Layer 2] current contract / universe 发布
18:20  [Layer 2] 晚报前增强数据第一轮补抓
18:40  [Layer 2] 晚报前增强数据第二轮补抓
19:00  Windows/Hermes Market Intel Evening 执行（亚洲全收盘 + 美股盘前）
19:20  [Layer 2] 增强数据回填，仅服务次日早报和 freshness 修复
20:30  [Layer 2] 增强数据回填，仅服务次日早报和 freshness 修复
21:00  [Layer 2] 分钟因子 / Hermite optional demo 批处理
21:30  美股开盘
──────────────────────────────────────────────────────────────
```

## 日韩市场覆盖

### 指数
- 日经 225（^N225）：yfinance，计入 BENCHMARK_SYMBOLS
- 韩国 KOSPI（^KS11）：yfinance，计入 BENCHMARK_SYMBOLS

### 半导体个股（跨市场领先指标）
- 日本：8035.T（Tokyo Electron）、6857.T（Advantest）、6146.T（Disco）、6723.T（Renesas）、6920.T（Lasertec）
- 韩国：005930.KS（三星电子）、000660.KS（SK 海力士）、042700.KS（Hanmi Semiconductor）

### 市场新闻
- `MarketNewsSpec` 覆盖：us, jp, hk, kr, cn, gold
- 韩国：Asia/Seoul 时区，15:30 收盘

## 故障降级路径

| 场景 | Layer 1 | Layer 2 | Layer 3 | 结果 |
|------|---------|---------|---------|------|
| 正常 | OK | 复用快照 | 复用快照 | 完整数据 |
| GitHub Actions 失败 | FAIL | yfinance 实时抓 | 复用 Layer 2 | 完整数据 |
| GitHub Actions + 本地都失败 | FAIL | FAIL | yfinance 实时抓 | 完整数据（延迟） |
| 全部失败 | FAIL | FAIL | FAIL | 降级报告（标注缺失） |

## 相关文件

| 文件 | 用途 |
|------|------|
| `.github/workflows/cross-market.yml` | Layer 1 GitHub Actions |
| `scripts/local_fetch_cross_market.sh` | Linux Layer 2 本地脚本 |
| `scripts/windows/morning_pipeline.ps1` | Windows 晨报入口，内嵌 hotsector 选股预览 |
| `scripts/windows/evening_pipeline.ps1` | Windows 晚报入口，包含 market-data-platform 刷新 |
| `scripts/windows/install_scheduled_tasks.ps1` | 注册 Windows Task Scheduler 任务 |
| `scripts/windows/preflight.ps1` | Windows 正式任务前 doctor 预检 |
| `scripts/windows/test_scheduled_tasks.ps1` | Windows 一次性 smoke task |
| `scripts/systemd/local-fetch-cross-market.service` | Linux Layer 2 service 模板，由 `setup_cron.sh` 渲染到 systemd user 目录 |
| `~/.config/systemd/user/local-fetch-cross-market.timer` | Linux Layer 2 timer |
| `src/a_share_daily/cross_market.py` | 核心抓取逻辑 + 快照回退 |
| `src/a_share_daily/fallback_fetch.py` | 快照优先补抓（Layer 2/3 共用） |
| `src/a_share_daily/global_leadlag.py` | 全球领先资产映射 + 基准指数 |
| `src/daily_messenger/common/market_news.py` | 各市场交易时间规格 |
| `scripts/morning_pipeline.sh` | Layer 3 晨间入口（选股预览 + 清单 + 代码化晨报） |
| `scripts/evening_pipeline.sh` | 晚报入口（代码直发事实材料 + 后续点评） |

## 维护说明

### 添加新市场
1. 在 `market_news.py` 添加 `MarketNewsSpec`
2. 在 `global_leadlag.py` 添加相关标的或指数
3. 更新 `cross-market.yml` 的 summary 生成逻辑
4. 更新本文档

完整日内时间表见 [daily-schedule.md](daily-schedule.md)。

### 调整 Layer 2 执行时间
```bash
systemctl --user edit local-fetch-cross-market.timer
# 修改 OnCalendar= 后
systemctl --user daemon-reload
systemctl --user restart local-fetch-cross-market.timer
```

### 手动触发
```bash
# Layer 2 手动执行
systemctl --user start local-fetch-cross-market.service

# 查看日志
journalctl --user -u local-fetch-cross-market.service -n 50

# Layer 3 手动执行
hermes cronjob run fc559b72e51c
```
