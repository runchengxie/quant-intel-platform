# 公开网站内容包

[English page](site-content-bundles.md)

Platform 将索引内的公开快照导出为字节稳定的 ZIP。校验命令核对归档字节、
已安装生产者身份和公开资格，再生成包含 artifacts/public/data 与
artifacts/public/reports 的外部输入目录，供 market-export-site-snapshot 使用。
这些命令不上传文件、不触发工作流、不部署网站、不发送消息。生产启用和
Pages、Deploy 消费端属于后续独立变更。

## 安装与使用

在隔离环境中从已评审的 Platform 不可变 Git 提交安装 market-intel。
可编辑安装、普通目录安装、缺少 VCS 元数据，以及调用者声明的提交与
实际安装提交不一致时，命令都会拒绝运行。在源码目录外使用隔离 Python
（-I）；也可使用控制台入口。

所有输入、内容包、回执与输出使用已配置的外部 DATA_ROOT。
下面是合成示例路径，不指向生产状态：

~~~bash
candidate="$DATA_ROOT/quant-intel-platform/example-content"
producer_revision="<reviewed-40-character-Platform-Git-revision>"
created_at="2026-11-01T00:00:00Z"
market-pack-site-content \
  --root "$candidate/input" --output "$candidate/content.zip" \
  --created-at "$created_at" --producer-revision "$producer_revision" \
  --receipt "$candidate/pack-receipt.json"
archive_sha256=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["archive_sha256"])' \
  "$candidate/pack-receipt.json")
market-verify-site-content \
  --bundle "$candidate/content.zip" --sha256 "$archive_sha256" \
  --output "$candidate/verified" --expected-producer-revision "$producer_revision" \
  --receipt "$candidate/verify-receipt.json"
market-export-site-snapshot --root "$candidate/verified" \
  --output "$candidate/reexported"
~~~

所有目标必须是新的外部路径，且不能相互重叠。已有目标（包括空目录）会被拒绝。
重试时复用原始内容包和回执；独立复核时选择新的输出路径。运行期间，调用者必须
独占输出目标。输入无效时不会提交输出或回执；回执写入或提交失败时撤回配对提交，
不替换已有输出。

## 身份与公开资格

清单包含 schema_version market_intel.site_content_bundle.v1、
publication public、bundle_id、created_at_utc、producer 与按路径排序的 files。
每个文件记录 path、sha256、bytes。producer 记录 owner
quant-intel-platform、distribution market-intel、source_revision、source_sha256。

逻辑 bundle_id 是去除 bundle_id 字段后的规范 UTF-8 JSON 的 SHA-256：
键排序、紧凑分隔符、有限数值、无额外空白。archive_sha256 单独绑定完整 ZIP 字节。
两者都不是 Git 提交。候选内容的 UTC 时间只设置一次，生成的健康状态文件也使用
该时间。普通导出器继续使用原有健康检查时间规则，因此后续重新导出有独立输出哈希。旧亚洲新闻投影遍历无序字段集合，打包器仅对 owner 生成的亚洲新闻 JSON 使用规范键顺序序列化；其中已有的内容、源文件和 Markdown 哈希字段及其值均保持不变。重新导出的亚洲新闻 JSON 键顺序可能不同，但解析后的内容必须完全相同。

已安装分发包必须携带真实 Git direct_url 元数据并匹配预期不可变提交。
生产者逐一校验安装包文件的 RECORD，再对排序后的相对路径、字节长度和实测
SHA-256 求哈希。source_sha256 覆盖已安装的生产者代码及包内资源，不包含分发
元数据、命令启动脚本或解释器字节码；不覆盖依赖包，也不声称持有原始私有报告。
已安装包被修改后校验失败。仅有版本号 0.1.0 不能证明具备内容包能力。

打包前，索引内的亚洲报告、图表与新闻、美股日报投影、评论、周报均通过 owner
公开契约检查。未知嵌套字段和缺失的必要公开标记会被拒绝；内容哈希不等于公开资格。
索引窗口外的历史源文件由已有导出器排除。导出快照或内容包中的额外文件会被拒绝。
原始源文件哈希和历史连续合约报告的精确哈希白名单保持原义；不引入新的数值
归一化规则或报告生成逻辑。

## ZIP 与回执

ZIP 首项为 manifest.json，之后依次是按路径排序的 payload/data/... 与
payload/reports/... 普通文件。使用 ZIP_STORED、固定时间
1980-01-01 00:00:00、Unix 普通文件权限 0644，不允许注释或扩展字段。
不压缩可避免压缩器版本差异及解压炸弹。校验器重建规范归档并要求逐字节一致，
拒绝替代本地头、前置数据和尾部附加数据。

上限：归档 64 MiB、展开内容 256 MiB、单文件 16 MiB、4096 个内容文件、
清单 2 MiB。由于不压缩，归档上限也限制了实际可容纳的内容量。重复 JSON 键或
ZIP 名称、非有限数值、绝对路径、点路径、反斜杠、盘符、大小写冲突、Windows
设备名、符号链接、带硬链接的输入文件、设备成员、未知字段、哈希或长度不符、
输入输出重叠，均会被拒绝。实现不直接调用任意 ZIP 解包接口。

不可变 ContentBundleReceipt 包含 schema_version
market_intel.site_content_receipt.v1、bundle_id、archive_sha256、
producer_revision、created_at_utc 和有序文件记录（path、sha256、bytes）。
JSON 回执置于归档外，不能单独授权公开发布。保留原始内容包、清单和回执，供后续
发布审计使用。生产者命令成功不等于网站已公开部署。

参阅[公开 JSON Schema](https://github.com/runchengxie/quant-intel-platform/blob/main/schemas/public/site_content_bundle.v1.schema.json)
和[平台发布边界](../platform-publication.md)。

更新已校验的输入目录时，导出器始终重建 data/health.json 与 data/us_daily_status.json，旧内容不会进入新包。daily_summaries.summaries 和 insights.insights 由已有 owner 源绑定函数筛选，insights.outcomes 重新计算。保留的记录仍须通过严格公开字段和证据校验；导出快照及已校验归档要求完整绑定。健康检查时间必须等于清单中的候选时间。

Markdown 与图片的公开准入仍由 owner 负责。传输保留索引内已准入的原始字节，并执行各类契约已声明的 Markdown／图片哈希校验（周报，以及亚洲新闻与报告的绑定）。未声明下载哈希的历史报告索引继续沿用原有准入契约。传输哈希不能证明任意正文都不含保密信息。
