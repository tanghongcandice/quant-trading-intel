// Run this function in an already signed-in Douyin profile page.
// It reads only rendered work cards and never accesses cookies or browser storage.
async ({ authorName = "久韭究财", profileUrl = location.origin + location.pathname } = {}) => {
  if (location.pathname !== new URL(profileUrl).pathname || document.querySelector('h1')?.innerText.trim() !== authorName) throw new Error('Douyin profile identity mismatch');
  const seen = new Set();
  const works = [];
  const links = Array.from(document.querySelectorAll('[data-e2e="user-post-list"] a[href^="/video/"]'))
    .filter((link) => !link.closest("footer"));

  for (const link of links) {
    const match = String(link.getAttribute("href") || "").match(/\/video\/(\d{15,})/);
    const awemeId = match?.[1];
    if (!awemeId || seen.has(awemeId)) continue;
    seen.add(awemeId);

    const cardText = String(link.innerText || link.getAttribute("aria-label") || "").trim();
    const paragraphText = Array.from(link.querySelectorAll("p"))
      .map((node) => String(node.innerText || "").trim())
      .filter(Boolean)
      .pop();
    const imageAlt = link.querySelector("img[alt]")?.getAttribute("alt") || "";
    if (!imageAlt.startsWith(authorName + '：')) continue;
    const title = paragraphText
      || imageAlt.replace(new RegExp(`^${authorName}：?`), "").trim()
      || cardText;
    // Do not search the whole card text: Douyin may inject page-level
    // subscription prompts into it. Only treat an explicit badge/label inside
    // the work card as restricted access.
    const accessPattern = /(专属会员|会员专属|会员专享|会员内容|会员可见|付费作品|付费内容|订阅专享)/;
    const badgeText = Array.from(link.querySelectorAll(
      '[class*="badge"], [class*="label"], [class*="tag"], [class*="vip"], [class*="member"], [data-e2e*="badge"], [aria-label]'
    ))
      .map((node) => String(node.innerText || node.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim())
      .filter((text) => text && text.length <= 40)
      .join(' ');
    const reviewOnly = accessPattern.test(badgeText);

    works.push({
      aweme_id: awemeId,
      url: `https://www.douyin.com/video/${awemeId}`,
      author: authorName,
      profile_url: profileUrl,
      ownership_verified: true,
      title,
      review_only: reviewOnly,
      access_label: reviewOnly ? (badgeText.match(accessPattern)?.[1] || "付费内容") : null,
      pinned: cardText.includes("置顶"),
      _browser_session: true,
    });
  }

  return works;
}
