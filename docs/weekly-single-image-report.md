# 周六市场风格周报单图交付

周报将通过现有门禁的价值因子和大小盘风格图合为一张竖版 PNG，附上原正文的市场背景、当前状态和下周观察。所有数值沿用原报告，不重新计算研究指标。统计区间重叠及研究观察限制保留在图内。完整 Markdown 和原图继续归档。

渲染入口：

```bash
WEEKLY_PREVIEW_ROOT="${DATA_ROOT:?}/weekly-report-preview"
python -m a_share_analysis.weekly_recap_image \
  --report "$WEEKLY_PREVIEW_ROOT/report.md" \
  --value-card "$WEEKLY_PREVIEW_ROOT/value_weekly_card.png" \
  --size-card "$WEEKLY_PREVIEW_ROOT/size_style_card.png" \
  --date 20261016 --out "$WEEKLY_PREVIEW_ROOT/weekly_recap.png"
```

调用方负责先验证本期数据和报告截止日。此入口只渲染，不访问网络或发送消息。输入卡片必须为宽度至少 1200 像素的 PNG；输出不超过 1200×12000 像素和 10 MB，超限或缺少摘要章节会失败。大小盘关闭时可省略 `--size-card`；是否允许缺失由部署侧原有门禁决定。

飞书交付由部署仓库负责，按受众和本期日期使用一个图片幂等键。该入口不会启用调度，具体任务状态由部署侧管理。
