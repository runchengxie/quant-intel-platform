# MiniMax 每日简评实施记录

原计划日期：2026-09-15。状态核对：2026-09-19。

MiniMax 简评入口及 Pages 集成已随 PR #5 合并，合并提交为 `6dc8bb2`。本文保留这一路生成的设计和实施范围。当前默认的结构化市场解读使用 Gemini，两者分别维护简评与解读数据，配置见 [README](../../../README.md#模型生成)。

## 已实现的流程

1. 从报告索引中选出最新有效晨报，以及目标日期不晚于晨报、生成时间早于晨报的最近一份晚报。
2. 将配对报告和 `prompts/daily-commentary-v1.md` 交给 MiniMax 文本接口。
3. 校验生成文本，写入简评日期、来源 ID、生成时间、模型、提示词版本和源内容哈希。
4. 合并仓库与已发布网站的近期简评，保留当前公开窗口内有效的记录。
5. 模型未配置、材料不足或调用失败时保留已有记录，并继续发布报告。

对应代码为 `scripts/generate_daily_summary.py`，测试位于 `tests/test_generate_daily_summary.py`。生成内容单独写入构建产物，不要求把每次云端输出自动提交回仓库。

## 输入与输出约束

配对同时使用报告目标日期和原报告生成时间，支持跨周末与休市日选择晚报。发送给 MiniMax 的事实材料限于所选两份报告。

提示词要求生成一段自然、简短的中文，建议约 40 至 80 字。校验器去除 `<think>` 内容、归一化空白，拒绝空文本、标题、列表和超过 120 个字符的输出。

短简评校验主要约束输出格式及来源身份。逐条引用、数字检查和观察条件核验由后来新增的结构化解读入口负责，不能仅凭短简评通过校验就认定其全部判断有据可查。

## 配置与失败处理

API 入口为 `https://api.minimaxi.com/v1/chat/completions`。密钥通过 `MINIMAX_API_KEY` 提供，模型由 `MINIMAX_MODEL` 指定，默认值为 `MiniMax-M2.7`。请求中的密钥只放在认证头中。

同一来源和配置的简评可复用缓存，`--force` 用于重新生成。工作流的 `force_summary` 输入对应这一选项。调用失败时，已有简评保留其原始日期，未生成的新日期保持空状态。

本地入口示例：

```bash
python3 scripts/generate_daily_summary.py \
  --reports data/reports.json \
  --summaries data/daily_summaries.json \
  --output /tmp/quant-market-intel-daily-summaries.json
```

## 运行状态与验证范围

截至状态核对日，仓库的原有短简评是人工审核样例，模型标记为 `chatgpt-reviewed`。MiniMax 的实际在线效果仍需真实调用记录支持。

09-19 验证成功的是 `gemini-3.8-flash` 结构化解读，首条输出使用 09-14 材料并标为历史回放。这条运行记录不验证 MiniMax 短简评入口。

已有测试覆盖配对选择、缺少一侧材料、晚于晨报的晚报排除、HTTP 响应、格式检查、缓存、历史保留，以及无密钥或调用失败时继续发布。当前完整检查命令见 [README](../../../README.md#检查与维护)。

接口依据见 [MiniMax Chat Completions 文档](https://platform.minimax.cn/docs/api-reference/text-chat-openai)。模型可用性仍以所用账户的真实调用结果为准。
