# A股信息源接入边界

## 市场字段

- `market:us`：现有 X、Discord、Substack 信息源。
- `market:cn`：A股信息源。
- 历史记录没有市场标签时默认归入 `us`，避免旧数据迁移造成中断。

## A股信息源

### 抖音：久韭究财

目标流程：作者主页增量采集 → 按作品 ID 去重 → 保存公开元数据并下载独立口播音轨 → 中文语音转写 → 交易观点分析 → 写入 `information_items`。抖音视频画面流和 OCR 不参与采集或正文生成。

建议采集实现使用 `jiji262/douyin-downloader`，它支持作者主页批量下载、增量模式、发布时间过滤、SQLite 去重和 OpenAI Transcriptions API。Codex 调用层可使用 `zrong/skills` 仓库中的 `video-downloader` skill。

入库建议：

- `source_type`: `douyin`
- `source_id`: `douyin_jiujiujiucai`
- `source.tags`: `premarket`, `market:cn`, `douyin`, `transcript`
- `external.id`: 抖音 `aweme_id`
- `content.text`: 完整转写文本
- `raw_payload`: 视频标题、发布时间、作者、公开链接、下载侧车元数据和转写信息

不要把 Cookie、请求头、临时媒体直链或 API Key 写入数据库。

### 抖音：潘姨有点神

处理规则与“久韭究财”完全相同：登录主页增量采集、作品 ID 去重、公开视频下载与中文转写、Codex 财经语境复核；会员或付费预览仅保留标题并标记 `review_only`，不进入后续分析。

- `source_type`: `douyin`
- `source_id`: `douyin_panyiyoudianshen`
- `source.tags`: `premarket`, `market:cn`, `douyin`, `transcript`
- `external.id`: 抖音 `aweme_id`
- `author.external_id`: `MS4wLjABAAAAiZFYelCAfbPcGXxkCEZEOpJPi-Fo_frPHiaEA45UerKIM-XTAXssDViEHNRu_bH2`

### 微信公众号：财躺平

采用用户提供文章链接后的单篇读取入库流程，不做账号级自动爬取。

- `source_type`: `wechat`
- `source_id`: `wechat_caitangping`
- `source.tags`: `premarket`, `market:cn`, `wechat`, `user_supplied_url`
- `external.id`: 规范化文章 URL 或文章 ID
- `content.text`: 文章正文

## 分析与去重

- 视频以 `aweme_id` 去重，文章以规范化 URL 去重。
- 使用平台原始发布时间，不使用采集时间代替。
- 转写文本需要保留原文，并单独生成题材、观点、理由、风险、原句和 A股代码实体。
- 单个视频下载、转写或分析失败不能阻断其他来源。
