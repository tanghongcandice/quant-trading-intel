"""Synthetic duplicate-ID DOM: never substitute a quoted preview for its parent."""
import unittest
from playwright.sync_api import sync_playwright
from discord_exporter_project import read_reply_context

class ResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop()
    def test_original_message_wins_over_earlier_quote(self):
        page=self.browser.new_page()
        try:
            page.set_content('''<div role="article" data-list-item-id="chat-messages-2">
            <span id="message-username-1">Quoted</span><div id="message-content-1">Clipped preview</div></div>
            <div role="article" data-list-item-id="chat-messages-1">
            <span id="message-username-1">Author</span><div id="message-content-1">Full parent message</div></div>''')
            self.assertEqual(read_reply_context(page,'1'),('Full parent message','Author'))
        finally:page.close()
    def test_quote_only_stays_unresolved(self):
        page=self.browser.new_page()
        try:
            page.set_content('<div role="article" data-list-item-id="chat-messages-2"><div id="message-content-1">Preview</div></div>')
            self.assertEqual(read_reply_context(page,'1'),('',''))
        finally:page.close()

if __name__=='__main__':unittest.main()
