"""Regression tests using synthetic Discord DOM, without network or credentials."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
extractor = (root / 'scripts/discord_browser_extract.js').read_text()
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
    page = browser.new_page()
    page.set_content('''<div role="article" data-list-item-id="chat-messages-1545608599848357898">
      <div id="message-reply-context-1545608599848357898"><img src="/avatars/1409412955736637571/x.png"></div>
      <img src="/avatars/999999999999999999/x.png">
      <span id="message-username-1545608599848357898" data-text="Other person"></span>
      <time id="message-timestamp-1545608599848357898" datetime="2026-09-04T00:00:00Z"></time>
      <div id="message-content-1545608599848357898">First line<br>Second line<span class="edited">（已编辑）<time>2026年9月5日星期六 04:48</time></span></div>
    </div>''')
    result = page.evaluate(f'({extractor})', {'guildId':'1','channelId':'2','maxRounds':1,'cutoffIso':'2026-09-04T01:00:00Z'})
    assert result['items'][0]['author']['id'] == '999999999999999999', result
    assert result['items'][0]['content'] == 'First line\nSecond line', result
    assert result['stop_reason'] == 'cutoff_reached', result
    page.set_content('<div>Loading</div>')
    empty = page.evaluate(f'({extractor})', {'guildId':'1','channelId':'2','maxRounds':1})
    assert not empty['items'] and empty['stop_reason'] != 'cutoff_reached'
    browser.close()
print('PASS: reply avatar excluded, multiline preserved, cutoff and empty capture distinguished')
