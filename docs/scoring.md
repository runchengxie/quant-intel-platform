# 主题评分方法论

## 概述

评分系统从 ETL 产出的 `raw_market.json` 中提取五个维度，按主题加权合成 0–100 总分。

## 五个评分维度

| 维度 | 权重（默认） | 数据来源 | 计算方法 |
|------|-------------|----------|----------|
| fundamental（基本面） | 0.30 | 主题行情表现 | `_scale(perf, midpoint=1.0, sensitivity=40)` |
| valuation（估值） | 0.25 | 平均市盈率（PE） | `_inverse_ratio_score(pe, baseline=35, sensitivity=90)` |
| sentiment（情绪） | 0.20 | Cboe Put/Call + AAII | Z-score → tanh 压缩 → 0–100 映射 |
| liquidity（资金） | 0.15 | 平均 PS | `_inverse_ratio_score(ps, baseline=8, sensitivity=70)` |
| event（事件） | 0.10 | 宏观事件/财报 | 固定值或事件强度映射 |

## 评分函数

### `_scale(value, midpoint, sensitivity)`

线性映射到 0–100：

$$score = 50 + (value - midpoint) \times sensitivity$$

钳制到 [0, 100]。

### `_inverse_ratio_score(value, baseline, sensitivity)`

对估值类指标（PE、PS），越低越好：

$$score = \_scale\left(\frac{baseline}{value}, midpoint=1.0, sensitivity\right)$$

### 情绪聚合（`sentiment.aggregate`）

1. Put/Call 比率：取对数后的 Z-score，取反（恐慌 = 反向看多），tanh 压缩
2. AAII 多空差：Z-score，取反（极端乐观 = 反向看空），tanh 压缩
3. 合成：`50 + 50 × mean(component_scores)`，钳制到 [0, 100]

历史数据保留：Put/Call 近 252 个值，AAII 近 104 个值。

## 权重配置

`config/weights.yml` 支持按主题覆盖默认权重：

```yaml
weights:
  default:          # 通用
    fundamental: 0.30, valuation: 0.25, sentiment: 0.20, liquidity: 0.15, event: 0.10
  theme_ai:         # AI 主题
    fundamental: 0.30, valuation: 0.15, sentiment: 0.25, liquidity: 0.20, event: 0.10
  theme_btc:        # BTC（情绪和资金权重更高）
    fundamental: 0.10, valuation: 0.15, sentiment: 0.30, liquidity: 0.30, event: 0.15
```

## 阈值与建议

| 阈值 | 默认值 | 含义 |
|------|--------|------|
| `action_add` | 75 | 总分 ≥ 此值 → 关注增强 |
| `action_trim` | 45 | 总分 ≤ 此值 → 关注降温 |

## 降级处理

当 ETL 失败或数据缺失时：

- 缺失的维度使用中性值（50）或历史缓存
- `scores.json.degraded = true`
- 日报会在标题和卡片中标注（数据延迟）
- 特定维度标记 `fallback: true` 说明使用了回退值

## 配置变更流程

修改 `config/weights.yml` 必须同步：

1. 更新 `version` 和 `changed_at`
2. 运行 `pytest -k contract` 确认契约测试通过
3. 更新 `tests/test_scoring.py` 中的预期值
