# 最新范围修正（2026-09-07，覆盖下文旧范围）

## 每轮 Chrome 前检可靠性规则（2026-09-08 起）

所有计划轮次均执行分阶段前检并保存到 `runs/<QUANT_RUN_ID>/chrome_preflight_diagnostics.jsonl`：先记录已登录 Chrome 标签枚举与连接结果，再单独记录群名、最新锚点和消息 DOM 是否实际读取成功。标签存在不等于页面读取成功；只有实际 DOM 中核实「宇菠萝的认知圈1群」、最新端和两小时重叠范围后，才允许声明前检成功。

首次连接或 DOM 读取失败时，在正常工具许可范围内约 3 秒后复查连接、约 10 秒后复查页面实读，最多两次；每次必须记录开始/结束时间、耗时、阶段、attempt、成功状态或错误原文摘要。不得绕过系统锁屏或认证。仍失败时保留失败证据，不生成虚假同轮凭证，并继续其他来源。

每轮使用 `scripts/chrome_preflight_diagnostics.py` 记录阶段，并在凭证完成后执行 `validate`。成功路径至少包含 `chrome_tab_enumeration`、`group_dom_read`、`processing_ledger_reuse`、`group_receipt` 四个成功阶段。可用 `power` 子命令只读保存相邻窗口内显示器开关与 `SkyComputerUseService` 活动；这些日志只用于时序证据。`screenLock` 设置只代表设置，关闭显示器、显示器唤醒或一次 `Mac is locked` 错误均不能单独证明当时会话真实锁定。

即使页面读取成功，也必须先保存轻量快照并执行处理账本 `reuse`；只对 `pending_voice_count` 中仍为空的新批次点击原生“转文字”。最终数据库中不存在对应 item 时不得复用。不得重复转写已完成批次。

## 每日任务强制前置步骤（本轮凭证）

先生成唯一 `QUANT_RUN_ID= prem arket` 格式运行 ID（实际使用 `premarket_YYYYMMDDTHHMMSSZ`，不含空格），在启动每日 shell 前完成 Chrome 群聊读取。先保存仅含页面当前可见字段的轻量快照，再执行 `.venv/bin/python scripts/douyin_group_processing_ledger.py reuse`。该命令只会在角色/头像、时间分隔、连续语音时长序列组成的批次指纹完全一致，且对应 item 仍存在于数据库时复用既有审核转写。随后只对 `pending_voice_count` 中仍为空的新批次逐段执行原生“转文字”；禁止对已成功复用的批次再次点击。核实最新端和上次成功时间前两小时的覆盖范围。新快照添加 `collection_evidence`：`run_id` 为该 ID、`latest_checked: true`、`overlap_covered: true`、`pending_voice_count: 0`。这些是实际完成后的证据声明，不得为绕过校验填写；未能覆盖、锁屏或转写失败必须保留失败状态。

随后执行 `.venv/bin/python scripts/prepare_douyin_group_run.py --run-id <该ID>`，完成严格构建、更新跨运行语音批次账本并生成本轮带内容哈希的凭证，再用 `QUANT_RUN_ID=<该ID> bash scripts/run_daily_collection.sh`。凭证只接受同轮、两小时内且文件哈希相符的捕获；单独运行 shell 不会自动点击语音菜单，未提供凭证时群聊明确失败。浏览器失败也要继续运行其他来源。报告使用数据库实际新增数，scheduler 的 new_count 仅为候选数，不能作为入库数。没有新消息也必须实际检查最新端并生成当轮凭证，但批次账本匹配时不重复转写。

只采集群主或管理员发言。群系统通知、入群/退群等事件和普通群成员消息不入库、不在网页展示。每条显式作者消息必须从角色标签核实 `群主`/`管理员`；无标签的同名作者不自动放行。连续堆叠消息可以继承已核实角色，但遇到新作者、系统通知或缺口必须断开。`role` 应从页面角色标签提取；旧快照可读取紧随作者显示的角色行。转写对象仅限已核实群主/管理员的语音。

首次采集40条中，14条系统消息已移除；视频卡片修正后保留5条群主/管理员记录，其中9月6日21:48「周复盘」的21段语音已合成一条1396字、10个语义段落。该语音早已入库，不能重复添加。页面默认当天筛选可能看不到昨天的记录，验证时点击“查看全部日期”并展开9月6日或直接定位语音记录。

下文“所有成员”“通知保留”仅为首次实施历史，已作废。未来只执行本段范围。

# 抖音群聊采集

来源 `douyin_group_yuboluo_1`，群名必须精确匹配「宇菠萝的认知圈1群」。采集用户已登录 Chrome 中该群已核实群主或管理员的消息及分享卡片，排除所有系统通知和普通成员发言。不能把同名群主和管理员仅凭显示名当作同一人；保留头像 DOM URL 作为当前页面的身份线索。

## 2026-09-07 首次接入

网页浮窗和独立 `https://www.douyin.com/chat` 都只能加载到 9 月 5 日的入群通知，未见可确认群创建/历史起点的信号。保存 40 条网页可见消息，21 段周复盘语音合并成 1 条、10 个语义段落，最终 20 条网页记录。仅代表已采范围，不能宣称完整群历史。首次只保存卡片文字的问题已修正：两条视频补齐实际作品链接和标题，自动发布通知移除，视频正文仍未转写。

## 每轮流程

1. 使用可用的浏览器工具选择已登录 Chrome，进入消息面板/独立聊天页，核实群名。仅通过用户授权页面读取 DOM；不读取 Cookie、密码、localStorage 或私有应用状态。新账号已在用户 Chrome 登录，不要以旧的独立抖音浏览器 profile 代替群聊会话。
2. 保存消息快照后再滚动。消息容器 `.messageMessageBoxmessageBox` 的父层 `data-index` 是倒序排列：索引越大越早；它不是消息 ID。虚拟列表会移除屏幕外节点。每次转写/滚动后立即读取当前 DOM 并累积保存。新消息到达会令所有 index 移位；检测到最新消息锚点变化时停止本批，重新采集对齐，不可继续按旧 index 覆盖。
3. 每个语音 `.MessageItemAudioaudioBox` 右键，点击出现的「转文字」，等待对应 `.MessageItemAudiovoiceText`。这是抖音原生转写，勿标成经过听音复核。保存原始每段文字和时长。失败语音保留待处理状态；不得用空文本冒充完成。
4. 当前 DOM 字段：时间 `.MessageBoxTimetimeLayout`，作者 `.MessageBoxMessageTitleavatarName`，时长 `.MessageItemAudioduration`，语音转写 `.MessageItemAudiovoiceText`。只有时间分隔符，无逐条精确时间；保存原标签及继承精度。作者缺省仅在连续堆叠消息中继承。通知不是成员发言；仅保留已核实群主/管理员发言。
5. 按完整连续发言顺序合并同一发送者的多段语音，不能跨文字、其他人、日期时间分隔或未采集缺口合并。每组转写按语义话题组织段落；`voice_paragraph_starts` 填当前快照每个段落起点的 index。保留原字词和数字，不把来源的市场判断当作核实事实。真实独立消息 ID 若页面没有暴露，禁止伪造；当前去重使用来源、时间分隔、发送者、完整内容指纹和重复次数，需人工核对跨快照的相同内容/相对时间。
6. 累积快照写 `data/browser_sessions/douyin_group_yuboluo_1.json`。对象含 `group_name`、ISO `captured_at`、`history_complete`、`history_boundary`、`messages`、`voice_paragraph_starts`；每条包含 `index,text,author,time,voice,duration,images,links`（按可见字段提供）。可用 `scripts/browser_session_bridge.py --port 8769` 的 `/group-import` 本地表单从浏览器保存；提交后以磁盘文件确认成功。不得把历史快照只更新 captured_at 冒充本轮刷新。
7. 从项目根目录执行 `.venv/bin/python scripts/build_douyin_group.py`，再用 `PYTHONPATH=apps/api .venv/bin/python -m app.services.ingestion_service --db data/quant_intel.sqlite --jsonl data/douyin_built/yuboluo_group_1.jsonl --run-id <本轮唯一标识>` 入库。重复导入应新增 0。已入库长语音组如增加新片段，应先核对旧完整组并明确更新，不能把旧组和扩展组同时当新消息。不要让通用批处理覆盖手工审核的段落。
8. 检查 A股来源卡片、来源筛选、合并语音完整文字和段落。单独报告原始读取数量、合并后条数、新入库数、失败/待补数量、最早可见时间。快照超过24小时，adapter会报 stale，不得把它报成成功读取新消息。某来源失败时其他来源继续。

历史尚未完整；之后每轮可尝试当前页面正常提供的历史加载，若仍到同一边界，记录限制，不盲目循环。若要补到更早，需取得该账号能实际显示的早期群记录（例如用户手机端可访问记录）；不能猜测缺失内容。

## 视频分享（2026-09-07 修正）

- `.MessageItemShareAwemecontainer` 是视频卡片；其中 `.MessageItemShareAwemeauthorName` 是视频作者，不能作为消息正文。群消息发送者及角色仍以卡片外的消息标题为准。
- 正常点击原卡片，保存地址栏实际出现的 `modal_id` 对应 `https://www.douyin.com/video/<id>`，并从播放页读取标题、作者。快照每条设 `message_kind: video_share` 和 `shared_video: {url,title,author,observed_url,verification}`。不能凭作者主页或封面猜作品 ID。缺链接会拒绝构建，必须补齐后再导入。
- `.MessageItemGroupNoticeGroupNoticeBox` 是系统自动通知，设 `message_kind: system_notice`；“我发布了新作品，快来看看！”不独立入库，不继承前一条的群主身份。
- 9月6日18:21分享：宇菠萝《出门躲鼻炎，顺便规避下周风险》，video/7682361511919467194。9月7日11:49分享：A股急诊室《市场底层：所有赚钱的方法，为什么最后都会走向拥挤》，video/7682346128800599338。两条群发送者均为群主宇菠萝。
- 原记录 ID 保持稳定，已入库补链接须更新对应记录；导入工具 INSERT OR IGNORE 不会自动更新旧行。修改前备份受影响行，并确认周复盘语音正文和语义段落未改变。
