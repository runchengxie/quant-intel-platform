# 保存新闻原文并预览六个栏目

这个入口保存 StreetAccount 原文，并生成待审核的本地预览。输出包含市场表现、市场主线、公司与行业动态、经济数据与美联储、重点上涨个股和重点下跌个股。

运行时明确指定美股交易日，并选择源码仓库之外的新目录：

```bash
uv run python -m daily_messenger.daily_report.news_snapshot \
  --date YYYY-MM-DD --output-dir /external/news-snapshots/new-run
```

复用已存档原文时，必须提供当时的抓取时间：

```bash
uv run python -m daily_messenger.daily_report.news_snapshot \
  --date YYYY-MM-DD --input-rss /external/source.xml \
  --captured-at YYYY-MM-DDTHH:MM:SS+00:00 \
  --output-dir /external/news-snapshots/replay-run
```

输出中的 `source.xml` 保留原始字节，`snapshot.json` 保存日期、来源位置和哈希，`preview.md` 用于阅读，最后生成的 `receipt.json` 记录文件哈希。没有回执的目录属于未完成输出。已有目录不会被覆盖。

程序会检查纽约交易日、提前收盘、频道日期和正文中的星期。旧日期、盘前快照或发生变化的正文结构会被隔离。隔离返回码为 2，其他输入失败返回码为 1，生成待审核预览返回码为 0。

抓取时间只说明内容在抓取时已经存在。RSS 条目时间与收盘正文有冲突时，程序保留原始时间，发布时间继续留空。操作者提供的历史抓取时间不等于经过独立验证的时间，不能把当前时间填成历史抓取时间。程序没有放宽现有报告的时间审核规则。

默认预览保留英文原文。中文预览需要额外提供 `--locale zh-CN --editor-json /external/editorial.json`。编辑文件包含原文哈希，以及六个按顺序排列的栏目，每个栏目引用自己的原文块。程序检查数字和引用，但无法判断单位、因果关系和翻译含义是否正确。第一次中文样稿由人工根据冻结原文整理，尚未接入自动翻译。

这些输出不能直接进入公开发布。来源审核、转载使用范围、重大消息的原始公告核对和六栏目推送适配仍需继续完成。入口不会调用模型、发送消息或安装定时任务。

字段、命令和接入限制见[英文完整说明](news-source-preview.en.md)。
