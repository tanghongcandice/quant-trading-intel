// Run in a signed-in X profile page. Returns JSONL-compatible tweet records.
// Only rendered posts authored by the profile are read; sidebar/recommendation
// text and engagement labels are deliberately excluded from content.
async ({ username = location.pathname.split('/')[1], maxRounds = 30 } = {}) => {
  const seen = new Set();
  const rows = [];
  const expected = String(username || '').replace(/^@/, '').toLowerCase();
  const read = () => Array.from(document.querySelectorAll('article')).map((article) => {
    const link = Array.from(article.querySelectorAll('a[href*="/status/"]'))
      .find((a) => /\/status\/\d+/.test(a.getAttribute('href') || ''));
    if (!link) return null;
    const href = link.getAttribute('href') || '';
    const id = (href.match(/\/status\/(\d+)/) || [])[1];
    if (!id || seen.has(id)) return null;
    const userLink = Array.from(article.querySelectorAll('a[href^="/"]'))
      .find((a) => new RegExp(`^/${expected}(?:$|/)`, 'i').test(a.getAttribute('href') || ''));
    if (!userLink) return null;
    const textNode = article.querySelector('[data-testid="tweetText"]');
    const time = article.querySelector('time')?.getAttribute('datetime') || null;
    const imageUrls = [];
    const addImage = (src) => {
      if (!src) return;
      const matches = String(src).match(/https?:\/\/pbs\.twimg\.com\/media\/[^\s"')]+/g) || [];
      for (const url of matches) if (!imageUrls.includes(url)) imageUrls.push(url);
    };
    article.querySelectorAll('img').forEach((img) => {
      addImage(img.currentSrc || img.src || img.getAttribute('src'));
      addImage(img.getAttribute('srcset'));
      addImage(img.getAttribute('data-src') || img.getAttribute('data-image-url'));
    });
    article.querySelectorAll('[style*="pbs.twimg.com/media"], [role="img"]').forEach((el) => addImage(el.getAttribute('style')));
    const images = imageUrls.map((url) => ({ url: url.replace(/[?&]name=[^&]+/, '').concat(url.includes('?') ? '&name=orig' : '?name=orig'), type: 'image' }));
    seen.add(id);
    rows.push({
      id_str: id,
      url: `https://x.com/${expected}/status/${id}`,
      username: expected,
      rawContent: textNode?.innerText?.trim() || '',
      media: images.length ? { images } : {},
      date: time,
      _browser_session: true,
    });
    return true;
  });
  for (let round = 0; round < maxRounds; round += 1) {
    const before = seen.size; read();
    window.scrollBy(0, Math.max(600, window.innerHeight * 0.8));
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (seen.size === before && round > 4) break;
  }
  return rows;
}
