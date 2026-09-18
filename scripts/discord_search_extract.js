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
    const replyLink = reply?.querySelector('a[href*="/channels/"]');
    // Discord sometimes renders the reply jump target on a non-anchor node or
    // only exposes the snowflake through an accessibility/data attribute.
    // Inspect rendered descendant attributes, never hidden application state.
    const replyAttributeValues = reply ? Array.from(reply.querySelectorAll('*')).flatMap((node) =>
      ['href', 'data-list-item-id', 'aria-controls', 'aria-describedby', 'id']
        .map((name) => node.getAttribute(name)).filter(Boolean)
    ) : [];
    const referencedAttributeId = replyAttributeValues.flatMap((value) =>
      Array.from(value.matchAll(/(?:message-content-|message-username-|chat-messages-|\/channels\/[^/]+\/[^/]+\/)(\d{15,})/g), (match) => match[1])
    ).find((candidate) => candidate !== messageId) || null;
    const referencedId = (referencedContentNode?.id.match(/message-content-(\d{15,})/) || [])[1]
      || (replyLink?.getAttribute('href')?.match(/(\d{15,})(?:\?.*)?$/) || [])[1]
      || referencedAttributeId
      || null;
    const referencedContent = referencedContentNode?.innerText?.trim() || null;
    const referencedAuthorNode = reply?.querySelector(
      '[id^="message-username-"][data-text], [id^="message-username-"] [data-text]',
    );
    const referencedAuthor = referencedAuthorNode?.getAttribute('data-text')?.trim()
      || reply?.querySelector('[id^="message-username-"]')?.innerText?.trim()
      || null;
    const item = { id: messageId, url: link, timestamp, content, author: { name: author, displayName: author }, channel_id: channelId, _browser_search: true };
    if (reply) {
      item.reference = { messageId: referencedId, channelId, unavailable: !referencedId };
      item.referencedMessage = referencedId ? {
        id: referencedId,
        content: referencedContent,
        author: { name: referencedAuthor, displayName: referencedAuthor },
      } : null;
      item._reply_unavailable = !referencedId;
    }
    return item;
  }).filter(Boolean);
  return { items, page, has_next: Boolean(document.querySelector('button[aria-label*="下一步"], button[aria-label*="Next"]')) };
}
