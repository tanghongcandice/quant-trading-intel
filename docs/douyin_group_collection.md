# v1.3.6 长期近期回看模式（2026-09-19）

用户已现场确认网页长期只能显示近期群聊且无法继续上划。独立采集器每轮仍须保存真实 DOM、处理当前可见待办、返回最新端复核并生成同轮部分收据；到达页面最早边界且滚动无进展后停止，不反复空转。

- 新近可见消息、完整语音组和已核实卡片继续正常入库或去重；不得因为历史连续性不足丢弃这些结果。
- 保持 `coverage_complete=false`、`partial_failure` 和完整游标冻结。最终库当前完整游标为 `2026-09-18 12:06 +08`，重叠目标为 `10:06 +08`；页面最早可见时间必须按每轮收据报告，不能手工改写游标来消除告警。
- 无法继续上划是已知平台回看限制，不等于 profile 未登录、语音转写失败或新消息采集失败。报告必须分别表达这些状态。
- 若未来页面或其他经用户授权的客户端真实提供了连续历史，仍可按窗口哈希、文字锚点和最终库证据补齐；在此之前不宣称完整覆盖。

# 初始加载与待办别名修复（2026-09-18）

独立脚本进入 `/chat` 后必须等待动态出现的裸群名或带人数标题，不得在页面 shell 初现时做一次性存在性判断。失败时保存 URL、标题和截图，第三次用同一授权 profile 的新标签重试。最终库已核实覆盖 2026-09-16 10:12 至 2026-09-17 21:01，并有审核记录至 2026-09-18 12:06 +08；事务游标校正至 12:06，后续从 10:06 重叠读取。网页近期回看限制不等同于数据库缺口。

独立脚本在打开群后等待消息和边界连续稳定，才开始持久化首个窗口。初始加载期间最早可见语音上的临时作者/时间头会随更多历史加载消失；不能放宽checkpoint把该变化无条件当作同一消息。已失败轮保留原证据，修复后新轮重新实读、原生转写、验证部分收据和导入。

旧待办因相对时间或批次边界不同产生别名时，`reconcile_group_retry_evidence.py` 必须同时验证两轮窗口哈希、唯一连续匹配、带日期的非语音文字锚点、已核实发送者角色及最终库完整原生文字，方可销账。纯语音时长匹配、歧义、无最终入库证据均拒绝；原待办证据和独立审计保留。此操作不复用未入库文字，不推进历史游标。

# 专用群聊采集启用：保留历史缺口（2026-09-18，用户明确授权）

用户确认重新登录后网页仅显示最近消息，并选择“保留历史缺口，先启用新消息采集；不把缺口标为补齐”。本节优先于下文必须完整覆盖才能启用专用脚本的旧限制。

- 群聊改由 `scripts/run_daily_collection.sh` 在原有锁内调用独立 Playwright 脚本；无需先执行 CUA 群聊前检，也不同时启动两条群聊采集通道。其他来源沿用现有入口。
- 首次启用使用 `douyin_group_collector.py collect --run-id <ID> --activate-partial`：必须取得真实、验证通过的部分收据并回到最新端复核，才写启用标记。标记明确记录 `mode=user_authorized_partial`、未解决历史缺口和原完整游标；不是全量成功凭证。
- 首次观察边界为 2026-09-17 21:01 +08，原完整游标 2026-09-16 12:12 +08（所需重叠起点 10:12）。后续每轮仍向历史端读取，若无法达到重叠范围，保持 `partial_failure`、`coverage_complete=false`，只导入已核实条目，并冻结完整游标。不可改写游标来消除缺口。
- 登录会话与浏览器本地数据保留；不清空 profile、不复制日常浏览器凭据。旧语音/卡片待办继续保留，新消息采集不等于历史缺口已补齐。
- 报告分别列出本轮新增/更新/重复、语音/卡片待办、历史覆盖缺口。采集时刻、模型和安全设置保持原样。

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

# 群聊部分入库修正（2026-09-17，优先于下文整批 ready 要求）

每轮结束即运行 `prepare_douyin_group_run.py`，即使 `group_checkpoint_status.json` 的 ready 为 false。程序仍逐窗口核验哈希、群名、作者、时间及原生转写来源；完整语音组和已解析消息可生成 `partial_ready` 收据，缺任何一段的语音组整体保留，未解析视频卡片单独保留。随后执行 `chrome_preflight_diagnostics.py validate`。不得把失败的 DOM 全覆盖阶段改写成成功；部分收据依据真实窗口验证导出子集。每日 shell 也会尝试这一导出步骤。

部分条目的 `group_capture_progress.complete=false`，入库与调度两侧都禁止推进该来源游标。`group_pending.json` 保留缺口原因；下轮从冻结游标减两小时继续，已经入库的完整组通过最终数据库账本复用。未完成时仍报告 partial_failure，并同时报告成功入库数，不能为了消除警告标为全成功。全部覆盖完成后才恢复正常推进游标。保持现有任务时刻及其他来源不变。

对旧检查点的恢复必须显式使用 `recover_verified_group_checkpoint.py --source-run <旧轮次> --after <已核对时间边界>`，原始 captured_at 保持不变，先备份、核验窗口来源并复核正文，再以历史恢复导入；不得当成本轮浏览器已刷新。

# 群聊续采修正（2026-09-17，优先于下文移位即重开的步骤）

读取最新版 `scripts/douyin_group_browser_workflow.js`。POST 被浏览器拦截时，可创建 `groupWorkflow(tab,bridge,runId,{transport:'local-get',bridgeUrl:'http://127.0.0.1:8771/group-checkpoint'})`，使用本机桥接通道；GET 会将窗口内容放进本机 URL，优先用默认 POST。不能用远程地址接收群聊数据。必须重新实读 DOM，禁止只改旧窗口的 captured_at。

索引变化后保留同轮证据。服务器使用唯一的连续重叠（至少三条，且包含非语音文本锚点）验证整体偏移，并重排已存索引、保留已有转写。纯时长重复、歧义、内容变更和不重叠仍拒绝；返回可见文本/时间边界重新观察，不删除证据强行拼接。最新端新增消息仍须返回补齐，最新端最后两次观察锚点一致后才可完成。

转写待办和消息取自同一个已保存窗口；点击前复读目标及相邻消息，并用目标原文约束实时控件。`window_changed` 表示重新调用 save 对齐后再选目标。每次滚动仅一页，下一次工具调用读取并保存；不可在同一次滚动调用中立即循环读取旧渲染结果。无法确定目标时不得继续沿用旧索引。每段原生文字出现后立即保存。

# v1.3.4 群聊断点流程（2026-09-15，受上述续采修正补充）

本节替代下文手写 `collection_evidence`、共享快照封装和仅凭 item 主键复用的旧步骤。只采已核实群主/管理员、原生转写和最终数据库权威规则不变。不是新增定时器；现有自动化每轮读取本文。

1. 生成唯一 `QUANT_RUN_ID`。每个浏览器阶段开始前运行 `.venv/bin/python scripts/chrome_preflight_diagnostics.py begin --run-id <ID> --stage <阶段> --attempt <次数>`，保存返回 token。阶段完成/报错后立即运行 `end --run-id <ID> --token <token> --status success|error --summary <实际结果>`。耗时由单调时钟实测，包含工具编排时间，不是纯浏览器延迟。未结束的开始事件和最后一次失败均不算成功。禁止事后补造零耗时成功记录。
2. 用 CUA 初始化/枚举用户已登录 Chrome，读取 `scripts/douyin_group_browser_workflow.js`，将函数定义放入授权 CUA 会话。`reconnectGroup(cua,browserId,attempt)` 每次重新枚举标签；前两次选当前聊天页，第三次在**同一个已授权 Chrome**打开新聊天页并核实群名。失败时约 3 秒、10 秒后重试，最多两次复查。若需重置工具会话，重新执行工具规定的初始化；诊断开始记录已在磁盘保留。登录/验证不可用时停止该来源，不绕过认证或改变锁屏设置。
3. 项目根目录运行 `.venv/bin/python scripts/browser_session_bridge.py --port 8771`，在授权浏览器打开 `http://127.0.0.1:8771/group-checkpoint`（端口占用先确认既有服务，不终止未知进程）。以聊天 tab、表单 tab、本轮 ID 创建 `groupWorkflow(tab,bridge,runId)`。每次 `save()` 提交当前渲染 DOM，响应必须带正确 run_id；磁盘同时写 `runs/<ID>/group_windows/`、`group_checkpoint.json` 和 `group_checkpoint_status.json`。不使用 `/group-import` 生成新轮凭证。
4. 每次滚动前保存。`older()` 向旧消息滚一页，`latest()` 返回最新端；动作后在**下一次 CUA 调用**执行 `save()`，确认渲染后的范围确有变化，不能将立即读到的旧 DOM 当作滚动完成。若无变化，用当前可见视口内的消息区坐标重新滚动并读取。窗口必须有重叠；中途移位/同索引内容改变会保存 `group_rejected_window.json` 并拒绝合并，改用新 ID 从最新端重建，不能删除证据继续拼接。
5. 保存时自动先复用最终库支持的账本。`transcribeVisible()` 每次只处理一段当前可见且仍 pending 的原生语音，并立即保存；没有可见 pending 时先定位对应窗口。同轮中断后以相同 ID 重新观察即可恢复；新轮不可使用上一轮未入库文字。完整指纹不匹配时，至少先取得旧批次最前两段原生文字作为锚点；只有同发送者/角色、同日相差不超过 180 秒、旧完整时长序列及已观察文字精确匹配且最终库候选唯一，才复用旧前缀，新尾段仍要转写。歧义留待核对，绝不按时长猜文字。
6. `ready` 由程序核验：连续索引从 0 开始、最早时间覆盖最终库游标减两小时、旧端不是半段/无日期语音批次、所有目标语音完成、至少两次最新端锚点一致且最后返回最新端。页面起初在旧端可先保存，再到最新端；未确认作者/时间的语音不算完成。新来源无游标须人工确定历史边界，不自动宣称完整。分享卡片缺实际作品链接会保留断点并明确失败；仍按下文“视频分享”规则在授权页面补证，不伪造链接。
7. 状态 ready 后运行 `.venv/bin/python scripts/prepare_douyin_group_run.py --run-id <ID>`。它重新检查每个窗口哈希、合并结果和文字来源，生成 version 2 的 `group_capture.json`、`group_items.jsonl`、`group_receipt.json`。随后记录 `processing_ledger_reuse` 和 `group_receipt` 的实际结果（这些阶段同样先 begin 后执行再 end），执行 `.venv/bin/python scripts/chrome_preflight_diagnostics.py validate --run-id <ID>` 并检查 `ready: true`。四个阶段为 `chrome_tab_enumeration`、`group_dom_read`、`processing_ledger_reuse`、`group_receipt`；DOM 阶段仅在群名、最新端、重叠均实读成功后结束为 success。
8. 用相同 `QUANT_RUN_ID` 启动 `scripts/run_daily_collection.sh`。群聊 adapter 只读本轮 `group_items.jsonl`，不受其他轮次覆盖共享快照影响。未完成断点会报告诊断路径；不冒充“没有新消息”，其他来源仍继续。已核实的语音扩展保留原主键和 external_id，由事务导入更新原记录与全文索引，并写 `group_revision_audit` 备份；报告分别使用实际 inserted_items、updated_items、skipped_duplicates。不重跑历史修复脚本。

采集仍依赖可访问的已登录 Chrome，shell 本身不能操作原生语音菜单。按 [OpenAI 官方定时任务说明](https://learn.chatgpt.com/docs/automations?surface=app)，本地项目任务需要电脑开机且桌面应用运行；此修复不承诺浏览器失联、登录过期或系统不可交互时也能采集。

# 最新范围修正（2026-09-07，以下流程细节以 v1.3.4 为准）

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
