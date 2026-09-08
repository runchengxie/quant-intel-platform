# 生成网页看板

## 最简单的方式

先准备好 `out/` 中的日报数据，然后运行：

```bash
uv run dm dashboard
```

默认会生成 `out/web_dashboard.html`。用浏览器打开这个文件即可查看。

## 指定输出位置

```bash
uv run dm dashboard \
  --out /tmp/market-intel-dashboard.html \
  --snapshot-dir data-snapshots/latest
```

`--snapshot-dir` 用于指定跨市场和其他快照的位置。没有快照时，看板仍可以展示已有的报告数据，但部分区域会显示缺失状态。

## 使用状态面板

如果有市场状态 CSV，可以这样运行：

```bash
uv run dm dashboard \
  --state-panel out/market_state_panel.csv
```

状态面板是可选输入，不会改变核心报告数据。

## 常见问题

如果页面为空，先检查：

1. `out/` 中是否有日报 JSON
2. `--snapshot-dir` 是否指向正确目录
3. 是否误用了生产目录中的旧数据

看板字段和输入格式见[网页看板](../web-dashboard.md)和[产物契约](../contracts.md)。
