// Run this function in an already signed-in Douyin profile page.
// It reads only rendered work cards and never accesses cookies or browser storage.
async ({ authorName = "久韭究财" } = {}) => {
  const seen = new Set();
  const works = [];
  const links = Array.from(document.querySelectorAll('a[href^="/video/"]'))
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
    const title = paragraphText
      || imageAlt.replace(new RegExp(`^${authorName}：?`), "").trim()
      || cardText;
    // Do not search the whole card text: Douyin may inject page-level
    // subscription prompts into it. Only treat an explicit badge/label inside
    // the work card as restricted access.
    const badgeText = Array.from(link.querySelectorAll('[class*="badge"], [class*="label"], [class*="vip"], [class*="member"]'))
      .map((node) => String(node.innerText || '').trim()).filter(Boolean).join(' ');
    const reviewOnly = /^(专属会员|会员专属|付费作品|付费内容)$/.test(badgeText);

    works.push({
      aweme_id: awemeId,
      url: `https://www.douyin.com/video/${awemeId}`,
      author: authorName,
      title,
      review_only: reviewOnly,
      access_label: reviewOnly ? (cardText.includes("专属会员") ? "专属会员" : "付费") : null,
      pinned: cardText.includes("置顶"),
      _browser_session: true,
    });
  }

  return works;
}
