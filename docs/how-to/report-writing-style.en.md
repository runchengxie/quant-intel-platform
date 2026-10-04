# Report writing style

[Chinese version](report-writing-style.zh-CN.md)

Research requests, short summaries, and evidence-backed market insights should
use clear, natural Chinese. Apply the same guidance to full reports and
section-specific requests. Human source reviewers should follow it when writing
approved paraphrases.

Check publication dates, event dates, and applicable conditions. Assess whether
information remained relevant at the report's cutoff, using only evidence
available by then. Keep unknown dates unknown. Do not use later events to
explain an earlier judgment. Include dates in prose only when they help readers;
do not repeat metadata in every sentence.

Write directly. Remove redundant negative clauses, formulaic contrasts, obscure
wording, translation-like prose, unnecessary Chinese-English mixing, and
unsupported conclusions. Skip formulaic closing paragraphs. Use Chinese
punctuation. Avoid unnecessary quotation marks, bold text, semicolons, and
em dashes. Keep meaningful source names and inline code when the output format
allows them. Review the draft once more before returning it.

For example, a source-audited paraphrase might read:

> 嘉信理财10月1日的盘前观察主要关注科技股表现和高位美债收益率。

The source's publication time and intraday phase still belong in its metadata.
Removing a repetitive disclaimer does not make the paraphrase a closing-market
explanation. Preserve required uncertainty, missing-data notices, evidence
references, JSON fields, and numeric contracts.

Personal Feishu commentary should be brief and omit dates. Its verified input
still retains dates, and the commentary must not use later or external
information. Do not use Markdown in that surface. A writing-policy change
invalidates commentary-generation caches, but not successful delivery receipts.

These instructions and editorial checks do not guarantee human-quality prose.
Offline tests verify prompt wiring and cache boundaries, not live model output.
Previously approved reports are not rewritten automatically. Runtime changes
require a separate release.
