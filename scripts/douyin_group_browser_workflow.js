/* Load this function in the authorized CUA JavaScript session.
 * tab: cua.getTab(...) result; bridge: local /group-checkpoint tab.
 * No CDP, cookies, browser storage, hidden app state, or remote APIs.
 * Call one method at a time, with diagnostic begin/end outside CUA so starts
 * survive a tool kernel reset. A bridge submission must finish before scrolling.
 */
async function reconnectGroup(cua, browserId, attempt) {
  if (![1,2,3].includes(attempt)) throw new Error('At most two connection rechecks');
  const tabs = await cua.listTabs({browser:browserId,emit:false});
  const chat = tabs.find(t=>t.url === 'https://www.douyin.com/chat');
  // After bounded retries of an unresponsive tab, a fresh page in the SAME
  // authorized Chrome profile can recover a stale page connection.
  const tab = chat && attempt < 3 ? await cua.getTab(chat.id,{browser:browserId}) :
    await cua.createBrowserTab(browserId,'https://www.douyin.com/chat',{sessionName:'🔎 群聊恢复'});
  const heading = await tab.playwright.getByText(/^宇菠萝的认知圈1群[（(]\d+[)）]$/).count();
  if (!heading) {
    const group = tab.playwright.getByText('宇菠萝的认知圈1群',{exact:true});
    if (await group.count() === 1) {
      await group.click();
      await tab.playwright.domSnapshot();
    } else {
      throw new Error('Group unavailable; inspect login/verification state without bypassing it');
    }
  }
  return tab;
}

function groupWorkflow(tab, bridge, runId) {
  let lastStatus = null;
  async function observe() {
    return tab.playwright.evaluate(() => {
      const list = document.querySelector('.messageMessageListlist');
      const groupName = '宇菠萝的认知圈1群';
      const heading = Array.from(document.querySelectorAll('*')).some(e =>
        e.children.length === 0 && (e.textContent || '').trim() === groupName + '(500)');
      // Group size changes; exact group name followed by a numeric member count.
      const verified = heading || Array.from(document.querySelectorAll('*')).some(e =>
        e.children.length === 0 && /^宇菠萝的认知圈1群(?:[（(]\d+[)）])?$/.test((e.textContent || '').trim()) &&
        !e.closest('.conversationConversationListwrapper'));
      if (!verified || !list) throw new Error('Exact group heading/message list unavailable');
      const messages = Array.from(list.querySelectorAll('.messageMessageBoxmessageBox')).map(e => {
        const text = e.innerText;
        const author = e.querySelector('.MessageBoxMessageTitleavatarName')?.innerText || '';
        const role = author ? text.split('\n').find(t => ['群主','管理员'].includes(t.trim())) || '' : '';
        const system = !!e.querySelector('.MessageItemGroupNoticeGroupNoticeBox') ||
          (!author && text.includes('加入了群聊'));
        const video = !!e.querySelector('.MessageItemShareAwemecontainer');
        return {index:Number(e.closest('[data-index]').getAttribute('data-index')),
          text, author, role, time:e.querySelector('.MessageBoxTimetimeLayout')?.innerText || '',
          voice:e.querySelector('.MessageItemAudiovoiceText')?.innerText || '',
          duration:e.querySelector('.MessageItemAudioduration')?.innerText || '',
          images:Array.from(e.querySelectorAll('img')).map(i=>({url:i.getAttribute('src') || '',alt:i.getAttribute('alt')})),
          links:Array.from(e.querySelectorAll('a')).map(a=>({url:a.getAttribute('href'),text:a.innerText})),
          message_kind:system?'system_notice':video?'video_share':''};
      }).sort((a,b)=>a.index-b.index);
      const rect = list.getBoundingClientRect();
      return {group_name:groupName,captured_at:new Date().toISOString(),messages,
        at_latest:Math.abs(list.scrollTop)<2 && messages.some(m=>m.index===0),
        scroll_target:[Math.round(rect.x+rect.width/2),Math.round(rect.y+rect.height/2)]};
    });
  }
  async function save() {
    const window = await observe();
    await bridge.playwright.getByLabel('群聊窗口 JSON',{exact:true}).fill(JSON.stringify({run_id:runId,window}));
    await bridge.playwright.getByRole('button',{name:'保存窗口并检查进度',exact:true}).click();
    // Read the response before any next action. A failed submission stops work.
    const result = await bridge.playwright.locator('#checkpoint-result').innerText({timeoutMs:10000});
    lastStatus = JSON.parse(result);
    if (lastStatus.run_id !== runId) throw new Error('Checkpoint was not saved for this run');
    return lastStatus;
  }
  return {
    save,
    async older() {
      await save();
      const window = await observe();
      await tab.scroll(window.scroll_target,'up',1);
      return {status:'scrolled_older',next:'Call save in the next CUA tool invocation after rendering'};
    },
    async latest() {
      await save();
      const window = await observe();
      await tab.scroll(window.scroll_target,'down',10);
      return {status:'scrolled_latest',next:'Call save in the next CUA tool invocation; repeat if not at latest'};
    },
    async transcribeVisible() {
      await save(); // ledger reuse ALWAYS precedes native transcription
      const window = await observe();
      const pending = new Set(lastStatus.pending_voice_indexes);
      const row = [...window.messages].reverse().find(m=>pending.has(m.index));
      if (!row) return {status:'no_visible_pending',...lastStatus};
      await tab.playwright.locator('[data-index="'+row.index+'"] .MessageItemAudioaudioBox').click({button:'right'});
      const menu = tab.playwright.getByText('转文字',{exact:true});
      if (!await menu.isVisible()) throw new Error('Native transcription action unavailable');
      await menu.click();
      await tab.playwright.locator('[data-index="'+row.index+'"] .MessageItemAudiovoiceText').waitFor({state:'visible',timeoutMs:10000});
      // Saving every segment makes CUA interruption resumable within this run.
      return save();
    }
  };
}
