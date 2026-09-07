# 增量处理账本

采集分为三个阶段，禁止把最终数据库去重当作避免重复工作的唯一手段：

1. **轻量发现**：刷新来源并读取稳定 ID、时间、标题、访问状态和必要上下文。
2. **处理前判重**：同时查询 `data/premarket_state.sqlite` 和最终数据库；稳定 ID 与内容未变化时复用已验证产物。
3. **重处理**：仅对新增、内容变化或本地产物缺失的记录执行图片 GET、翻译、音频下载、ASR 和分析。

## 渠道规则

- X：tweet ID 稳定。正文未变化且已保存静态图片的字节数仍匹配时，不重复下载图片；新英文内容仍进入翻译审核。
- Discord：message ID 稳定。每轮继续刷新页面/导出，以更新附件签名 URL 和回复上下文；正文、父消息 ID 和静态附件数量未变化时复用已保存图片，不重复下载或翻译。
- Substack：canonical URL/文章 ID 加平台更新时间组成版本键。版本未变化时复用已读取正文；版本变化时重新打开文章。
- 抖音主页：aweme ID 稳定。两小时重叠范围仍保留，但仅数据库和调度状态中都不存在的公开作品进入下载与 Whisper；付费/会员内容继续只作原文审阅。
- 微信文章：使用既有 `source_id + external_id` 事务去重；仅处理用户提供的文章链接。
- 抖音群聊：无稳定消息 ID。使用已核实角色/头像、时间分隔和连续语音时长序列组成批次指纹。轻量快照保存后先运行：

  ```bash
  .venv/bin/python scripts/douyin_group_processing_ledger.py reuse
  ```

  只有仍为空的语音才允许点击抖音原生“转文字”。`prepare_douyin_group_run.py` 会把完成批次写入 `data/collection_state/douyin_group_voice_ledger.json`，且复用前必须确认对应 item 仍存在于最终数据库。

稳定 ID 或指纹相同但正文、版本标记、父消息、访问状态或附件集合变化时，不视为可直接复用；应进入更新审核。所有最终写入仍必须经过 `ingestion_service.import_jsonl` 的事务守卫。
