# 术语表

本表说明文档里出现的英文缩写与中英混用术语，方便第一次接触项目的人。代码标识符和专有名词（数据商、框架、股票代码）保持英文，不翻译。

## 缩写（每个文档首次出现时写中文全称）

| 缩写 | 中文全称 |
|------|----------|
| ADR | 架构决策记录 |
| CLI | 命令行 |
| CI/CD | 持续集成与持续部署 |
| PR | 拉取请求 |
| ETL | 数据抽取、转换与加载 |
| API | 应用程序接口 |
| TA | 技术分析 |
| LLM | 大语言模型 |
| OOS | 样本外 |
| CST | 中国标准时间 |
| ET | 美国东部时间 |
| UTC | 协调世界时 |
| PE | 市盈率 |
| EPS | 每股收益 |
| TTM | 过去十二个月滚动 |
| NTM | 未来十二个月 |
| SMA | 简单移动平均 |
| RSI | 相对强弱指标 |
| ATR | 平均真实波幅 |
| PIT | 时点（point-in-time，指数据在真实可用时刻的快照） |
| EOD | 数据截止日（end of day） |
| PSR | 概率夏普比率 |
| DSR | 修正夏普比率 |
| Rank IC | 截面排序信息系数 |
| gitlink | Git 子模块指针 |

## 中英混用术语（统一用中文，英文只保留在代码标识符里）

| 英文 | 中文 |
|------|------|
| fallback | 兜底 |
| snapshot | 快照 |
| contract | 契约 |
| manifest | 清单 |
| token | 令牌 |
| hook | 钩子 |
| namespace | 命名空间 |
| submodule | 子模块 |
| pipeline | 流水线 |
| dashboard | 看板 |
| idempotency / idempotent | 幂等 |
| degraded | 降级 |
| handoff | 交接 |
| deploy / deployment | 部署 |
| preview | 预览 |
| delivery | 投递 |
| repo | 仓库 |
| cron | 定时任务 |
| provider | 数据提供方 |
| deferred stub | 延迟占位 |
| registry | 注册表 |
| receipt | 回执 |
| panel | 面板（如因子面板，指按截面排列的因子矩阵） |
| live ETL | 实时 ETL（联机抽取转换加载，与离线快照相对） |
| fail closed | 严格失败即止（校验未通过时整体不渲染、不投递，而非降级放行） |

## 保留英文（专有名词，不翻译）

- 数据商与框架：TuShare、FMP、Alpha Vantage、FRED、EDGAR、AAII、CBOE、OANDA、yfinance、GLM、Qwen、DeepSeek
- 平台与代码：GitHub、GitHub Actions、Feishu/lark、Hermes、systemd、PowerShell、Pages、OIDC
- 金融代码：VIX、VVIX、SPY、QQQ、SMH、GLD、SLV、GC=F、DXY、HSI、BTC、XAU、A股
- 数据格式：JSON、CSV、YAML、RSS/Atom

## 专有名称与内部代号

文档和代码里反复出现、但字面不好懂的名字都列在这里。它们大多对应真实的代码目录、飞书群或机器人，所以这里只解释、不改名。

| 名称 | 是什么 | 说明 |
|------|--------|------|
| hotsector | 热点板块筛选器（子模块 hot-sector-screener）的简称，也指它产出的热点板块列表 | 由中文（热点板块）拼接缩写而来 |
| Hermes | 消息投递层（基于 Feishu/lark 的推送框架），负责把报告发到飞书 | 专有名词，保留英文 |
| DailyWatch、DailyWatch20 | 本项目的核心产物：每天观察的 20 只 A 股名单 | DailyWatch 意为每日观察，20 表示 20 只 |
| lark-cli | 飞书（Lark）命令行客户端，脚本用它发消息 | Lark 是飞书海外品牌名，保留英文 |
| watchlist20 | 20 股观察名单的产出物与命令（strategy watchlist20 run），与 DailyWatch20 同义 | 策略层的叫法 |
| AI精选 | AI 选股器（ai-stock-picker）产出的 AI 精选股票列表 | 中文名，含义直白 |
| Mag7 | Magnificent Seven，美股七大科技龙头（苹果、微软、谷歌、亚马逊、英伟达、Meta、特斯拉）的合称 | 专有名词，保留英文 |
| Numeric（Numeric 排名） | 一种用数值打分排序的方法 | 与五臂是两个不同概念，见下 |
| 五臂（五臂稳定性实验） | 研究方法术语：在同一批冻结数据上跑 5 个实验臂，用拉丁方设计减少顺序偏差，检验模型输出是否稳定 | 是一种实验设计 |
| Hermite | 稳定性守卫（因子之上的因子变换），用作 B 袖 guard | 和 Hermes（飞书投递层）是不同组件，注意区分 |

补充说明：项目里没有 Numeric Shadow 这个名称。容易混淆的是 Numeric 排名（一种排序方法）和五臂稳定性实验（一种实验设计），两者是不同概念。

## 实验与研究用语（研究态标记，非生产发布）

这些词出现在研究类文档（configuration.md、report-distribution.md）里，描述实验状态而非线上功能，平时阅读报告时容易误读为已发布能力。

| 用语 | 含义 |
|------|------|
| research_only | 标记为仅研究的产物：计算并记录证据，但不渲染、不发送、不进入生产报告 |
| shadow | 影子模式：新逻辑并行运行、产出对照结果，但不替换线上路径，用于比对 |
| pick-plan / trial | 配对实验：一组冻结的输入与配置，用来在固定条件下复现某次实验 |
| append-only evidence | 只追加的证据：实验结果以追加方式记录，不覆盖历史，便于追溯每次运行 |
| Pro+thinking | 一种模型推理配置（更高成本的深度思考模式），部分实验尚未覆盖 |
