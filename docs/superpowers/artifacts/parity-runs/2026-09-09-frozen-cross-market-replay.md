# 冻结 cross-market 输入后的历史 replay

日期：2026-09-09  
状态：`needs_explanation`，不计入五日 clean parity

## 运行范围

- source date：`20260904`
- signal date：`20260909`
- old artifact：当前生产目录中的 2026-09-04 morning manifest
- new artifact：public `v0.1.4` shadow pipeline，独立临时输出目录
- cross-market input：从 old manifest 提取并冻结为 exact-date snapshot
- delivery：`MORNING_SEND_REPORT=0`，未发送 Feishu
- DailyWatch20/D11-H5：历史 artifact 不满足日期契约，按 fail-closed/audit-only 处理

## Parity 摘要

比较器记录：

| 项目 | 结果 |
|---|---:|
| data snapshot match | `true` |
| missing from old | 1 |
| missing from new | 1 |
| differing files | 1 (`morning_manifest.json`) |
| manifest differences | 19 |
| unexplained differences | `true` |

冻结 cross-market 输入后，US/Asia/commodity/macro 的业务数值差异不再是本轮的
主问题。仍然存在的差异包括：

- 新运行的 `freshness` 读取 canonical data root 的当前 latest 分区，而旧 manifest
  是当时的历史 as-of 状态；
- 旧 manifest 引用了已经不存在的历史 DailyWatch20 topic artifact，新运行因此按
  日期契约拒绝消费当前 20260908 topic；
- 输出绝对路径和 cross-market `_source` 属于环境/来源元数据差异；
- weekly recap 元数据和内部 pipeline marker 的产物集合不一致。

## 结论

这次 replay 证明 snapshot identity 门禁和 fail-closed 行为有效，也证明只冻结
cross-market 不足以构成完整 parity 输入。它不能作为 clean run 或生产切换证据。

## 下一步

1. 为 A 股数据增加显式 as-of snapshot/receipt，而不是读取当前 latest 分区。
2. 保留 DailyWatch20 versioned run 和 topic artifact，使历史 replay 可解析。
3. 对 `_source`、路径和内部 marker 使用已声明的环境归一化/产物契约规则。
4. 完整输入冻结后重新运行；只有 `unexplained_differences=false` 才开始五日计数。

