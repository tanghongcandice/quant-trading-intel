# v1.3.5 群聊缺口持久重试（2026-09-18）

- 每轮读取最终库 group_retry_queue；待办即使不在本轮两小时窗口也不能丢弃。使用 evidence 中时间、作者、相邻语音时长定位旧消息；index 只是本轮提示，不能跨轮直接点击。
- checkpoint 自动登记缺失语音和异常分享卡片；先处理可见待办，再向历史滚动定位剩余待办。每条每轮最多尝试两次，失败记录原因并继续其他消息，不删除待办、不宣称全量成功。
- CUA 通道：异常卡片必须点击对应原卡片，读取实际播放页 URL 和可见标题/作者，再按现有快照协议保存 shared_video；不得猜链接或补造正文。语音继续使用原生“转文字”，每段保存并校验相邻消息防串位。
- CUA 每次尝试后执行 .venv/bin/python scripts/group_retry_queue.py --run-id "$QUANT_RUN_ID" --attempt-key <快照返回的fingerprint>；失败追加 --error "<具体原因>"。独立脚本自动记录。
- 可见内容补齐只标记 awaiting_import。prepare 将指纹附到 JSONL，最终库事务核实对应 message_parts 后才标记 resolved；重复记录也必须核实正文证据，不能仅凭 ID 销账。
- 所有复核和入库完成后再次运行 .venv/bin/python scripts/group_retry_queue.py --run-id "$QUANT_RUN_ID"，检查 runs/<RUN_ID>/group_retry_report.json。报告新增、恢复、仍待处理数量及失败原因；队列未清空时继续冻结群聊完整游标，其他来源正常完成。
- 专用 profile 未完成真实验证时不得创建启用标记；仍走现有 CUA 通道，不能把脚本已更新描述为现场补采已成功。

# 独立群聊脚本（2026-09-18，用户授权的新通道）

用户已授权将群聊浏览器操作迁移到独立持久化 Playwright profile。本节优先于下文仅使用日常 Chrome/CUA 的限制。不得复制日常 Chrome profile、读取或输出凭据；首次由用户登录 `data/browser_profiles/douyin_group`。

- 首次登录：`.venv/bin/python scripts/douyin_group_collector.py login --wait-seconds 1800`，用户登录后打开「宇菠萝的认知圈1群」。脚本实际读到精确群名和消息列表才报告登录完成。
- 真实验证：生成新 QUANT_RUN_ID，运行 `.venv/bin/python scripts/douyin_group_collector.py collect --run-id "$QUANT_RUN_ID" --headed --activate`。与每日采集共用锁，专用 profile 另有非阻塞锁。
- 直接调用既有 checkpoint 函数逐窗口保存真实 DOM，保留同轮窗口哈希、最终库账本复用、两小时重叠、索引对齐、原生转写及部分入库。诊断阶段使用实际 begin/end。未解析的视频分享仍留置，不猜链接。
- `--activate` 只在完整收据及诊断均通过时写入 `data/collection_state/douyin_group_script_enabled.json`。未通过前不得手填该文件，旧定时流程不切换。
- 启用后每日 shell 在采集锁内自动调用独立脚本，无需先由 CUA 操作；已有同轮人工断点时避免重复运行。失败保留证据并继续其他来源；凭证和入库验证保持不变。
- 本次实现仍待用户首次登录和真实完整覆盖验收。离线测试不能代替在线成功。若窗口变化无法安全对齐、原生转写两次无结果、滚动三次无进展或达到时间/步数界限，保留断点及失败原因。不会无限重试或推进不完整游标。

# Codex 自动化：每日五次增量采集

## 群聊部分入库（2026-09-17，覆盖下文整批成功后才能入库的旧要求）

群聊窗口持久化后，无论完整性 ready 是否为 true，均尝试 `prepare_douyin_group_run.py --run-id "$QUANT_RUN_ID"` 和诊断 validate。`partial_ready` 允许已核验完整语音组先入库，异常卡片及缺片段的语音组保留在检查点与 group_pending.json。不得伪造成功阶段；程序核验真实窗口后允许部分导出。部分导入冻结游标，下轮从旧游标重叠两小时继续，并复用已入库组；完整覆盖后才推进。每日 shell 已加入自动准备部分收据步骤。报告必须同时列出已入库内容及剩余缺口，partial_failure 不等于全部失败。

## 英文入库翻译门禁（2026-09-16）

- `collect_premarket.py` 将 X、Discord、Substack 缺少中文翻译的英文正文分流到本轮 `pending_codex_review.jsonl`，不直接进入 ready 入库列表。纯网址免翻译；空白翻译不算完成。
- 本轮待审英文必须由 Codex 补齐 `raw_payload.translation`，保持英文原文不变，再经标准入库入口入库；包括 X 长帖扩展更新，不复用截断译文。存在待审项时报告 awaiting_codex_review，不能称全部完成。
- 不为该规则扫描全量历史。历史翻译修复仅在用户指定的小范围内进行；本次限定 20260916T120157Z 轮次最近最多 10 条缺译英文。

## 抖音公开转录补全（2026-09-16）

- 久韭究财和潘姨统一从最终库挑选未完成的公开转录，每来源每轮最多 3 条，间隔 6 小时、自动最多 5 次；新作品采集不受补全额度影响。以 `douyin_retry_attempts` 查看尝试结果，完整记录不重做，明确会员内容不进入队列。
- 下载器 HTTP 403 或无元数据不能解释为作品没有音轨；读取本轮 `<source>_enrichment.log` 和 `<source>_transcription.log`，单列实际失败。
- 已授权 Chrome 正常播放页可作为补采来源。运行 `scripts/douyin_playback_bridge.py --run-id "$QUANT_RUN_ID"`，通过本地 8772 表单保存当前作品的真实标题、作者链接、时长与实际播放媒体地址。使用 `video.currentSrc` 或浏览器 `pageAssets` 已观察到的 `media-audio` 资源；禁止后台音乐代替。认证/验证不可用时保留失败，不绕过。
- 浏览器证据保存后运行同一脚本 `--download --run-id "$QUANT_RUN_ID"`，使用最终播放音轨转写。完整口播须 Codex 复核，`text_refinement.status=reviewed` 只在实读复核后设置；自动术语检查不冒称 Codex 已复核。
- 新完整转录进入 `pending_codex_review.jsonl`；补齐复核后经 `ingestion_service.import_jsonl` 原位更新，保留 ID、external_id、发布时间和 `douyin_revision_audit`，同步全文索引。报告更新数而非新增数。
- 本节有限公开转录重试是“不得历史补采”的明确例外；禁止的是无边界扫描、历史清理和重做已完成内容。不得使用 `--force-retry` 或提高默认额度来绕过退避。达到 5 次或作者归属未验证时单列需要处理，不能静默当作完成。
- `scripts/run_daily_collection.sh` 会导出同轮 `QUANT_RUN_ID` 并生成 `runs/<QUANT_RUN_ID>/douyin_completion.json`。即便脚本返回 0，也必须检查 `pending_review_path`、`pending_review_count` 和该完成报告；`success_with_held_items` 不代表正文已补齐。
- 自动化在本轮继续处理允许额度内的正常播放页回退、全文复核和事务导入，不只留下计划。浏览器不可用或授权受限时保留错误、继续其他来源。完成复核后用 `scripts/check_douyin_completion.py --db data/quant_intel.sqlite --collection-json /tmp/quant_intel_daily_collection_${QUANT_RUN_ID}.json --output runs/${QUANT_RUN_ID}/douyin_completion.json` 重新核对最终库；退出 2 表示仍有留置，退出 1 表示校验失败。只有最终正文已提交且待处理数为零才报告转录全部完成。

## X 截断恢复（2026-09-15）

- helper 将详情补全失败保留为 `pending_retry` 并输出具体错误；不得将整批命令成功等同于每帖完整。
- X adapter 每轮轮转重试最终库中最多 3 条公开截断记录，不受旧发布时间游标排除。检查各来源 `retry-<ID>/stderr.log`，失败须单列报告，登录失效请用户恢复专用 profile，不绕过验证。
- 补全原文必须重新生成中文翻译，禁止复用旧截断译文。事务入库只允许更长且完整的公开原文替换，保留原 ID 和审计；失败保留原记录，不冒报完成。
- “正文较长但末尾无标点”只用于触发详情页检查，不能在详情页目标正文已经稳定后继续单独作为截断证据。详情页稳定最长正文且主帖自身没有 `Show more/显示更多` 时应标记完整；引用卡片的控件不得影响主帖判断。

## v1.3.4 群聊断点修复（覆盖旧群聊前检操作）

- 每轮优先执行 `docs/douyin_group_collection.md` 顶部最新规则和 `scripts/douyin_group_browser_workflow.js`。使用本地 `/group-checkpoint` 表单逐窗口保存；滚动后下一次工具调用再保存，逐段原生转写后立即保存。恢复时重新观察同轮 DOM，不把跨轮未入库文字当权威。
- 新窗口自动执行最终库支持的账本复用；稳定前缀扩展需至少两段真实文字锚点、完整旧前缀及唯一最终库匹配。只转写 pending 段，扩展由事务更新原条目并留审计，不插入重复语音组。
- 不再手写 `latest_checked` / `overlap_covered` / `pending_voice_count` 冒充收据。`prepare_douyin_group_run.py` 只接受同轮有窗口哈希和可追溯文字的断点；adapter 只读本轮 `group_items.jsonl`。新消息造成索引移位时保留拒绝证据并换新 ID 对齐。
- 每个阶段用 `chrome_preflight_diagnostics.py begin/end` 包围真实操作，先持久化开始再调用工具，错误保留原文摘要。阶段耗时含编排时间，不填 0；未完成开始、最后一次失败、窗口/内容哈希不符均拒绝 ready。
- 连接失败按已有两次复查上限重枚举；末次可在同一授权 Chrome 新开聊天页并核实群名。不得绕过认证/锁屏；依旧失败时报告具体阶段和断点路径，其他来源继续。保留现有任务时刻、模型、项目与通知设置，不新增定时任务。

## v1.2.1 入库与翻译修正规则

- 所有入库经过 `ingestion_service.import_jsonl` 的事务守卫；Discord 不使用仅正文前缀或不限定日期的全局去重。
- 核对目标作者 ID，非目标作者只作为上下文隔离。跨来源合并限定同作者、120 秒内，检查回复与静态附件，支持原文整行后追加中文的镜像版本，优先 TianYi。
- 同频道不同消息 ID 不按正文自动合并。保留去重审计，新增数量以最终留存数为准。
- 仅网址的作者消息（含链接预览）免翻译；带作者评论的消息仅翻译评论并原样保留 URL，不添加语言说明。
- 使用共享 `link_policy` 和最新翻译附加、采集入口；网页列表与详情的 HTTP/HTTPS 地址直接可点击，历史纯网址译文不显示。
- 不重跑无边界历史补采、清理或回填脚本；本文件顶部明确授权的有界公开转录重试除外。
- 最终状态区分来源失败与条目留置：来源无法采集、事务失败或关键验证失败才记 `partial_failure`；全部来源完成而仅有少量安全留置时记 `success_with_held_items`，并列出条目及原因。留置全部经同轮或后续核实恢复后，将原轮最终完成状态更新为 `success`。不得让少量留置看起来像整轮采集失败。

每天在北京时间 00:00、08:00、12:30、16:00、20:00 运行增量采集。实际任务入口为：

```bash
./scripts/run_daily_collection.sh
```

1. 运行本地后端采集入口。
2. 采集 X、Discord、Substack，以及已配置的抖音和微信公众号文章。
3. 以上次成功时间为游标，并向前重叠 2 小时补漏。
4. 将数据归一化为 `information_item.v1`。
5. 写入本地 SQLite：`quant-trading-intel/data/quant_intel.sqlite`。
6. 生成当天 `premarket_report.v1` 快照。
7. 输出采集摘要：每个来源数量、失败来源、最新发布时间、数据库路径、报告路径。

约束：

- 单个来源失败不应中断其他来源。
- 不要打印 cookies、tokens 或任何敏感凭据。
- X、Discord、Substack 使用当前配置的 x-crawler / exporter / helper 入口；不得退回旧页面 fixture。抖音主页沿用已授权的独立浏览器 profile，群聊使用授权 Chrome 页面。不得打印或导出凭据。
- Discord 回复需要保留被回复消息上下文；静态图片可下载，跳过动图和视频。
- 抖音只采标题与口播转录；必须使用最终播放音轨，不能把背景音乐当口播。
- 公开抖音主页口播在构建 JSONL 时执行 A 股证券名称及财经术语检查，再走事务入库；保存标准术语命中与修正数量审计，残留已知高置信度错词时拒绝构建。当前是高置信度词表检查，不宣称覆盖全部 A 股证券或替代 Codex 上下文复核。
- X、抖音明确订阅截断内容仅供每日原文审阅，不参与观点和标的分析；Substack 已授权会员文章按正常内容处理。不得仅凭截断误判订阅。
- 微信公众号只处理用户提供的链接，保留行情相关原文段落，排除动物救助和无关随笔；按原发布时间去重入库。
- 完成后列出实际新增或更新的来源、标题、发布时间与 ID；新增、恢复、更新、重复和失败分别统计。静态图片验证必须读取响应体并检查实际字节，不以 HEAD/HTTP 200 为成功依据；权限错误单列报告。
- 采集时间筛选必须以 `created_at` / `published_at` 为准，而不是 `collected_at`。
- 入库必须去重。

## v1.3.2 最终库权威与公开长帖补全

- `data/quant_intel.sqlite` 是去重、游标推进和处理复用的唯一权威来源。调度状态库只作为采集审计账本；如果状态库已有记录但最终数据库没有对应 `source_id + external_id`，必须标记为待恢复并重新输出、补齐富化和入库，不能计作重复。
- 各来源的两小时重叠窗口以最终数据库事务成功提交的 `source_cursors` 为基准。不得因仅完成采集或仅写入调度状态而推进用于排除候选的游标。
- 抖音主页的音频下载与 Whisper 复用只认最终数据库中的作品 ID；状态库独有 ID 必须重新进入恢复处理。会员作品仍只保存标题并保持 `review_only`。
- 久韭究财与潘姨的当前增量发现使用同一套最终库游标和两小时重叠规则。历史补采状态、退避时间或批次额度不得提前返回空候选，也不得阻断主页中新作品的下载、转写和入库；历史补采失败只能影响历史补采自身。
- X 对明确非订阅内容的长帖预览执行详情页补全：出现“Show more/显示更多”，或正文接近 280 字符且句尾明显未完成时，打开对应 status 详情页，等待正文稳定并保留最长版本。详情页补全失败时才允许设置 `source_truncated=true`，且不得误标为订阅预览。
- 每轮摘要中的“重复”和“新增”以最终数据库实际存在和实际留存为准；发现状态库与最终库不一致时，单列恢复数量与作品 ID。

## v1.3.3 群聊前检可靠性

- 每个计划轮次都必须为同轮 `QUANT_RUN_ID` 创建 `runs/<QUANT_RUN_ID>/chrome_preflight_diagnostics.jsonl`，分开记录 Chrome 标签连接与群聊 DOM 实读。只有在页面中实际核实群名、最新锚点和两小时重叠后才算成功。
- 首次连接或 DOM 读取失败后，约 3 秒复查连接、约 10 秒复查页面实读，最多两次。仍失败则保留阶段、attempt、时间和错误摘要，不生成虚假凭证，并继续其他来源。
- 使用 `scripts/chrome_preflight_diagnostics.py` 记录 `chrome_tab_enumeration`、`group_dom_read`、`processing_ledger_reuse`、`group_receipt`，凭证生成后执行 `validate`。可用其 `power` 子命令只读采集相邻显示器与 `SkyComputerUseService` 时序证据。
- `screenLock` 设置、显示器关闭/唤醒和一次 `Mac is locked` 报错均不能独立证明历史会话真实锁定；报告只区分已证实事件和未证实原因，不改变系统电源或安全设置，也不绕过认证。
- 轻量快照后先执行群聊处理账本 `reuse`，只转写仍为空的新语音；复用必须同时满足批次指纹一致且对应 item 存在于最终数据库。
