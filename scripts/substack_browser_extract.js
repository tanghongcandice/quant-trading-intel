// Run in a logged-in Substack article page. Reads rendered article DOM only.
async () => {
  const article = document.querySelector('article, .body.markup, [data-testid="post-content"]');
  const title = document.querySelector('h1')?.innerText?.trim() || document.title;
  const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href;
  const published = document.querySelector('time[datetime]')?.getAttribute('datetime') || null;
  const content = article?.innerHTML || article?.innerText || '';
  return { title, url: canonical, published, content_html: content, _browser_session: true };
}
