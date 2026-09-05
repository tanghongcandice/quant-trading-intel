// Run in a Discord author-search results page. Reads rendered results only.
// The caller should paginate and pass the selected author label.
async ({ guildId, channelId = null, authorLabel, page = 1 }) => {
  const rows = Array.from(document.querySelectorAll('[id^="search-result-"]'));
  const items = rows.map((element) => {
    const messageId = (element.id.match(/search-result-(\d{15,})/) || [])[1] || null;
    if (!messageId) return null;
    const heading = element.querySelector('h2, h3, [role="heading"]');
    const author = heading?.querySelector('button')?.innerText?.trim() || authorLabel || null;
    const link = element.querySelector('a[href*="/channels/"]')?.href || null;
    const timestamp = element.querySelector('time[datetime]')?.getAttribute('datetime') || null;
    const contentNode = element.querySelector(`#message-content-${messageId}`);
    const content = contentNode?.innerText?.trim() || null;
    if (!author || (authorLabel && !author.includes(authorLabel))) return null;
    const reply = element.querySelector(`#message-reply-context-${messageId}`);
    const referencedContentNode = reply?.querySelector('[id^="message-content-"]');
    const referencedId = (referencedContentNode?.id.match(/message-content-(\d{15,})/) || [])[1] || null;
    const referencedContent = referencedContentNode?.innerText?.trim() || null;
    const item = { id: messageId, url: link, timestamp, content, author: { name: author, displayName: author }, channel_id: channelId, _browser_search: true };
    if (reply) {
      item.reference = { messageId: referencedId, channelId, unavailable: !referencedId };
      item.referencedMessage = referencedId ? { id: referencedId, content: referencedContent, author: { name: null, displayName: null } } : null;
      item._reply_unavailable = !referencedId;
    }
    return item;
  }).filter(Boolean);
  return { items, page, has_next: Boolean(document.querySelector('button[aria-label*="下一步"], button[aria-label*="Next"]')) };
}
