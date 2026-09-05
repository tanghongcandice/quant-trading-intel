// Run this function in the already signed-in Discord channel page.
// It only reads rendered messages. It never reads cookies, localStorage, or tokens.
async ({ guildId, channelId, existingIds = [], cutoffIso = null, maxRounds = 40, anchorLatest = true, checkpoint = false }) => {
  const messageSelector = '[role="article"][data-list-item-id^="chat-messages"]';
  const existing = new Set(existingIds.map(String));
  const collected = new Map();
  let currentAuthor = null;
  let currentAuthorId = null;

  const attachmentType = (filename) => {
    const extension = String(filename || "").split(".").pop().toLowerCase();
    return ({ jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", avif: "image/avif" })[extension] || "";
  };

  const readRows = () => { currentAuthor = null; currentAuthorId = null; return Array.from(document.querySelectorAll(messageSelector)).map((element) => {
    const listId = element.getAttribute("data-list-item-id") || "";
    const messageId = (listId.match(/(\d{15,})$/) || [])[1];
    if (!messageId) return null;

    // Discord changes the username node shape between grouped/ungrouped
    // messages.  The data-text attribute may be on the node itself (not a
    // descendant), so support both forms and never fall back to a generic
    // data-text node from reply context.
    const usernameNode = element.querySelector(
      `[id="message-username-${messageId}"][data-text], [id="message-username-${messageId}"] [data-text]`,
    );
    const username = usernameNode?.getAttribute("data-text")?.trim() || null;
    if (username) { currentAuthor = username; currentAuthorId = null; }
    const authorName = (username || currentAuthor || "Unknown Discord author").split("\n")[0].split(",")[0].trim();

    const avatarUrl = Array.from(element.querySelectorAll('img[src*="/avatars/"]'))
      .filter((image) => !image.closest('[id^="message-reply-context-"]'))
      .map((image) => image.currentSrc || image.src)
      .find(Boolean) || "";
    const explicitAuthorId = (avatarUrl.match(/\/avatars\/(\d+)\//) || [])[1] || null;
    if (explicitAuthorId) currentAuthorId = explicitAuthorId;
    const authorId = explicitAuthorId || currentAuthorId;

    const timestamp = element.querySelector(`time[id="message-timestamp-${messageId}"]`)?.getAttribute("datetime")
      || element.querySelector(`time[datetime][id$="-${messageId}"]`)?.getAttribute("datetime")
      || null;
    const contentNode = element.querySelector(`[id="message-content-${messageId}"]`) || document.getElementById(`message-content-${messageId}`);
    const accessories = element.querySelector(`[id="message-accessories-${messageId}"]`) || document.getElementById(`message-accessories-${messageId}`);
    // Forwarded Discord messages often put the actual text in accessories,
    // while the message-content node is absent. Read only direct text nodes
    // and links from the message body; this excludes author/date/reactions/UI.
    const readBody = (node) => {
      if (!node) return "";
      const parts = [];
      for (const child of node.childNodes) {
        if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) parts.push(child.textContent.trim());
        else if (child.nodeType === Node.ELEMENT_NODE && (child.tagName === "A" || child.matches("[data-slate-string]"))) {
          const value = (child.innerText || child.textContent || "").trim();
          if (value) parts.push(value);
        }
      }
      return parts.join(" ").replace(/\s+/g, " ").trim();
    };
    const cleanBody = (node) => {
      if (!node) return "";
      const clone = node.cloneNode(true);
      clone.querySelectorAll('time, [role="tooltip"], [class*="timestamp"], [class*="edited"], [class*="Timestamp"]').forEach(child => child.remove());
      const textOf = (child) => {
        if (child.nodeType === Node.TEXT_NODE) return child.textContent;
        if (child.nodeType !== Node.ELEMENT_NODE) return "";
        if (child.tagName === "BR") return "\n";
        return Array.from(child.childNodes).map(textOf).join("") + (/^(DIV|P|LI|BLOCKQUOTE)$/.test(child.tagName) ? "\n" : "");
      };
      return textOf(clone).trim();
    };
    const content = cleanBody(contentNode) || (() => {
      const combined = [cleanBody(accessories)].filter(Boolean).join("\n");
      const lines = String(combined).split("\n").map((line) => line.trim()).filter(Boolean);
      return lines.find((line) => !["已转发", "添加反应"].includes(line) && !/^\d+$/.test(line) && !line.startsWith("Club 500")) || "";
    })() || null;

    const attachmentLinks = Array.from(element.querySelectorAll('a[href*="cdn.discordapp.com/attachments/"], a[href*="media.discordapp.net/attachments/"]'));
    const attachments = Array.from(new Map(attachmentLinks.map((link) => {
      const url = link.href;
      const filename = String(url.split("?", 1)[0].split("/").pop() || "");
      return [url, { url, fileName: filename, contentType: attachmentType(filename) }];
    })).values());

    const reply = element.querySelector(`[id="message-reply-context-${messageId}"]`);
    let reference = null;
    let referencedMessage = null;
    if (reply) {
      const repliedContent = reply.querySelector('[id^="message-content-"]');
      const replyLink = reply.querySelector('a[href*="/channels/"]');
      const referencedId = (repliedContent?.id.match(/(\d{15,})$/) || [])[1]
        || (replyLink?.getAttribute("href")?.match(/(\d{15,})(?:\?.*)?$/) || [])[1]
        || null;
      const repliedAuthorNode = reply.querySelector(
        '[id^="message-username-"][data-text], [id^="message-username-"] [data-text]',
      );
      const repliedAuthor = repliedAuthorNode?.getAttribute("data-text")?.trim()
        || reply.querySelector('[id^="message-username-"]')?.innerText?.trim() || null;
      const repliedText = cleanBody(repliedContent) || null;
      const unavailable = repliedAuthor === "消息无法加载" || (!referencedId && !repliedText);
      reference = { messageId: referencedId, channelId, unavailable };
      referencedMessage = unavailable ? null : {
        id: referencedId,
        content: repliedText,
        author: { displayName: repliedAuthor, name: repliedAuthor },
      };
    }

    return {
      id: messageId,
      url: `https://discord.com/channels/${guildId}/${channelId}/${messageId}`,
      timestamp,
      content,
      author: {
        id: authorId,
        name: authorName,
        displayName: authorName,
      },
      attachments,
      reference,
      referencedMessage,
      _reply_unavailable: Boolean(reply && reference?.unavailable),
      _browser_session: true,
    };
  }).filter(Boolean); };
  let encounteredExistingId = null;
  const cutoffMs = cutoffIso ? Date.parse(cutoffIso) : null;
  let reachedCutoff = false;
  // A persistent Discord profile can reopen at the last viewed position,
  // which may be days old. Always anchor at the live bottom first so the
  // incremental capture starts from the newest rendered messages.
  const findScroller = () => {
    let node = document.querySelector(messageSelector);
    while (node) {
      if (node.scrollHeight > node.clientHeight + 50 && /auto|scroll/.test(getComputedStyle(node).overflowY)) return node;
      node = node.parentElement;
    }
    return null;
  };
  const liveScroller = findScroller();
  if (liveScroller && anchorLatest) {
    liveScroller.scrollTop = liveScroller.scrollHeight;
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  let stagnant = 0;
  let previousOldest = null;
  for (let round = 0; round < maxRounds; round += 1) {
    for (const doc of readRows()) {
      collected.set(String(doc.id), doc);
      if (existing.has(String(doc.id))) encounteredExistingId = String(doc.id);
      const timestampMs = doc.timestamp ? Date.parse(doc.timestamp) : NaN;
      if (cutoffMs && Number.isFinite(timestampMs) && timestampMs <= cutoffMs) reachedCutoff = true;
    }
    if (checkpoint && round % 10 === 0) await window.discordCheckpoint(Array.from(collected.values()));
    if (encounteredExistingId || reachedCutoff) break;
    const oldest = Array.from(collected.keys()).sort()[0];
    stagnant = oldest === previousOldest ? stagnant + 1 : 0;
    previousOldest = oldest;
    if (stagnant >= 15) break;
    const scroller = findScroller();
    if (!scroller) break;
    const before = scroller.scrollTop;
    const step = Math.max(scroller.clientHeight * 0.8, 600);
    scroller.scrollBy(0, -step);
    scroller.scrollTop = Math.max(0, before - step);
    await new Promise((resolve) => setTimeout(resolve, 600));
    if (scroller.scrollTop === before && before <= 1) await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  if (checkpoint) await window.discordCheckpoint(Array.from(collected.values()));
  return {
    items: Array.from(collected.values()),
    stop_reason: encounteredExistingId ? "existing_id_reached" : (reachedCutoff ? "cutoff_reached" : "scroll_limit_or_end"),
    encountered_existing_id: encounteredExistingId,
  };
}
