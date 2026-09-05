(function () {
  const isLocalHost = ["127.0.0.1", "localhost"].includes(window.location.hostname);
  const defaultApiBase = isLocalHost ? "http://127.0.0.1:8000/api" : `${window.location.origin}/api`;
  const API_BASE = window.__QUANT_INTEL_API_BASE__ || defaultApiBase;

  const knownTickers = [
    "MU", "MRVL", "NBIS", "MAAA", "ARM", "AMD", "AVGO", "MP", "RKLB", "VRT", "SPCX", "XLE", "BX", "IGV",
    "SPX", "QQQ", "SPY", "TAIX", "LPK", "MXL", "POET", "LITE", "COHR", "RDDT", "META", "MSFT", "CRM",
    "SNDK", "EWY", "SIVE", "RPI", "XFAB", "SOI", "AAOI", "INTC", "ASML", "ACMR", "ORCL", "TTWO",
    "NVDA", "HMAX", "MMN", "AXTI", "AEHR", "AMZN", "IREN", "XLU"
  ];
  const excludedTickers = new Set(["AXGX"]);

  const tickerSectorGroups = [
    ["光通信 / CPO", new Set(["AAOI", "SIVE", "LITE", "COHR", "AXTI", "AEHR", "POET"])],
    ["存储", new Set(["MU", "SNDK"])],
    ["Neocloud / 算力能源", new Set(["NBIS", "IREN", "CRWV", "VRT", "XLE", "XLU"])],
    ["AI 芯片与设备", new Set(["MRVL", "NVDA", "AMD", "AVGO", "ARM", "INTC", "TSM", "ASML", "ACMR", "AMAT", "SMCI", "XFAB", "SOI", "MXL"])],
    ["云计算 / 软件平台", new Set(["AMZN", "MSFT", "ORCL", "CRM", "META", "RDDT", "IGV"])],
    ["大盘与 ETF", new Set(["SPX", "SPY", "QQQ", "TAIX", "EWY"])],
    ["商业航天", new Set(["RKLB"])],
    ["先进封装 / 材料", new Set(["LPK", "RPI"])],
    ["稀土材料", new Set(["MP"])],
    ["特殊事件 / AI 平台", new Set(["SPCX"])],
    ["消费与应用", new Set(["TTWO", "MVIS"])],
    ["金融", new Set(["BX"])],
  ];

  const cnSectorDefinitions = [
    ["AI 应用 / 传媒", /AI影视|AI长剧|AI短剧|微短剧|短剧|影视|传媒|芒果|剧本|电视台/i],
    ["银行 / 红利", /银行|大行|净息差|股息|红利|中特估/i],
    ["煤炭 / 能源", /煤炭|动力煤|焦煤|煤价|煤业|煤电/i],
    ["PCB / 电子材料", /PCB|覆铜板|玻纤布|建滔|电路板/i],
    ["光通信 / 算力基础设施", /光纤|光通信|通信|光棒|光缆|光模块|CPO|液冷|服务器|算力|数据中心/i],
    ["半导体 / 存储", /半导体|芯片|存储|DRAM|NAND|晶圆|先进封装/i],
    ["消费电子", /苹果|华为|折叠屏|消费电子|手机|端侧AI/i],
    ["有色金属 / 资源", /有色|黄金|铜价|铝价|锂|稀土|紫金|洛钼/i],
    ["化工 / 新材料", /化工|新材料|涨价函|原材料|反内卷/i],
    ["地产 / 基建", /地产|房地产|建筑|建材|基建|工程/i],
    ["大盘 / 市场策略", /沪指|创业板|上证|深证|指数|成交|磨底|大盘|市场|仓位|波段/i],
    ["宏观 / 政策", /PMI|PPI|CPI|政策|流动性|利率|美联储|非农/i],
  ];

  const timezoneOffsets = {
    "Asia/Shanghai": 8,
    "America/New_York": -4,
    "UTC": 0
  };

  const state = {
    market: "us",
    view: "feed",
    timezone: "Asia/Shanghai",
    sources: new Set(),
    authors: new Set(),
    ticker: "",
    sector: "",
    sentiment: "",
    query: "",
    reviewStartDate: "",
    reviewEndDate: "",
    reviewGroup: "date",
    reviewSort: "desc",
    selectedId: null
  };

  const els = {
    marketTabs: Array.from(document.querySelectorAll("[data-market]")),
    marketKicker: document.getElementById("marketKicker"),
    marketTitle: document.getElementById("marketTitle"),
    marketDescription: document.getElementById("marketDescription"),
    marketSourceRoster: document.getElementById("marketSourceRoster"),
    usMarketCount: document.getElementById("usMarketCount"),
    cnMarketCount: document.getElementById("cnMarketCount"),
    viewTabs: Array.from(document.querySelectorAll("[data-view]")),
    viewPanels: Array.from(document.querySelectorAll("[data-view-panel]")),
    sourceFilterTrigger: document.getElementById("sourceFilterTrigger"),
    sourceFilterLabel: document.getElementById("sourceFilterLabel"),
    sourceFilterMenu: document.getElementById("sourceFilterMenu"),
    authorFilterTrigger: document.getElementById("authorFilterTrigger"),
    authorFilterLabel: document.getElementById("authorFilterLabel"),
    authorFilterMenu: document.getElementById("authorFilterMenu"),
    tickerFilter: document.getElementById("tickerFilter"),
    tickerField: document.getElementById("tickerField"),
    sectorFilter: document.getElementById("sectorFilter"),
    dailyOriginals: document.getElementById("dailyOriginals"),
    rawReviewHint: document.getElementById("rawReviewHint"),
    reviewStartDate: document.getElementById("reviewStartDate"),
    reviewEndDate: document.getElementById("reviewEndDate"),
    clearReviewRange: document.getElementById("clearReviewRange"),
    rawGroupOptions: Array.from(document.querySelectorAll("[data-raw-group]")),
    rawReviewSort: document.getElementById("rawReviewSort"),
    activeFilterSummary: document.getElementById("activeFilterSummary"),
    sourceInsightNote: document.getElementById("sourceInsightNote"),
    sourceInsightTables: document.getElementById("sourceInsightTables"),
    tickerHistory: document.getElementById("tickerHistory"),
    resetFilters: document.getElementById("resetFilters"),
    drawer: document.getElementById("analysisDrawer"),
    drawerScrim: document.getElementById("drawerScrim"),
    closeDrawer: document.getElementById("closeDrawer"),
    drawerTitle: document.getElementById("drawerTitle"),
    drawerContent: document.getElementById("drawerContent"),
    copyContext: document.getElementById("copyContext"),
    copyJson: document.getElementById("copyJson"),
    openOriginal: document.getElementById("openOriginal"),
    copyNotice: document.getElementById("copyNotice"),
    globalCopyNotice: document.getElementById("globalCopyNotice"),
    apiOfflineBanner: document.getElementById("apiOfflineBanner")
  };

  let items = [];
  let minMs = NaN;
  let maxMs = NaN;
  let filteredItems = [];
  let apiAvailable = false;
  const apiDetailCache = new Map();
  const apiContextCache = new Map();
  const analysisPromptCache = new Map();
  let analysisPromptSeq = 0;
  let globalNoticeTimer = null;

  init();

  async function init() {
    bindEvents();
    initImageLightbox();
    await loadItems();
    fillFilterOptions();
    fillReviewDateRange();
    render();
  }

  async function loadItems() {
    const apiItems = await fetchApiItems();
    const sourceItems = apiItems || [];
    apiAvailable = Boolean(apiItems);
    items = sourceItems.map(normalizeItem).sort((a, b) => b.createdMs - a.createdMs);
    const validTimes = items.map((item) => item.createdMs).filter(Number.isFinite);
    minMs = validTimes.length ? Math.min(...validTimes) : Date.now();
    maxMs = validTimes.length ? Math.max(...validTimes) : Date.now();
    updateDataStatus(
      apiAvailable ? `API 数据 · ${items.length} 条` : "API 离线 · 无法加载数据",
      apiAvailable ? "online" : "offline"
    );
  }

  async function fetchApiItems() {
    if (!window.fetch) return null;
    try {
      const pageSize = 500;
      const apiItems = [];
      let offset = 0;
      let total = Infinity;
      while (offset < total) {
        const response = await fetch(`${API_BASE}/items?limit=${pageSize}&offset=${offset}`, { cache: "no-store" });
        if (!response.ok) throw new Error(`API ${response.status}`);
        const payload = await response.json();
        if (!Array.isArray(payload.items)) return null;
        apiItems.push(...payload.items);
        total = Number.isFinite(Number(payload.total)) ? Number(payload.total) : apiItems.length;
        if (!payload.items.length || payload.items.length < pageSize) break;
        offset += payload.items.length;
      }
      return apiItems.map(apiItemToRaw);
    } catch (_error) {
      return null;
    }
  }

  function apiItemToRaw(item) {
    return {
      schema_version: "information_item.v1",
      id: item.id,
      source: item.source || {},
      external: {
        id: item.external_id || null,
        url: item.external_url || ""
      },
      author: item.author || {},
      content: {
        title: item.title || null,
        text: item.content_text || item.content_preview || "",
        html: null,
        language: item.language || null,
        hash: item.content_hash || null
      },
      timestamps: {
        created_at: item.created_at,
        collected_at: item.collected_at || item.created_at,
        edited_at: null,
        deleted_at: null
      },
      relations: item.relations || {},
      metrics: item.metrics || {},
      entities: (item.tickers || []).map((ticker) => ({
        type: "ticker",
        value: ticker,
        normalized_value: ticker,
        confidence: 1,
        source: "api"
      })),
      analysis: item.analysis || null,
      raw_payload: item,
      market: item.market || "us"
    };
  }

  function updateDataStatus(text, state = "online") {
    const el = document.getElementById("dataStatus");
    if (el) el.textContent = text;
    const dot = document.querySelector(".status-dot");
    if (dot) dot.dataset.state = state;
    if (els.apiOfflineBanner) els.apiOfflineBanner.hidden = state !== "offline";
  }

  function normalizeItem(item) {
    const text = item.content?.text || "";
    const title = item.content?.title || "";
    const translationData = item.translation || item.raw_payload?.translation || null;
    const translatedText = typeof translationData === "string"
      ? translationData
      : String(translationData?.text || "");
    const translatedTitle = typeof translationData === "object"
      ? String(translationData?.title || "")
      : "";
    const summaryData = item.summary || item.raw_payload?.summary || null;
    const summaryText = typeof summaryData === "string"
      ? summaryData
      : String(summaryData?.text || "");
    const summaryBullets = Array.isArray(summaryData?.bullets)
      ? summaryData.bullets.map((value) => String(value || "").trim()).filter(Boolean)
      : [];
    const language = item.content?.language || item.language || item.raw_payload?.language || "";
    const analysisText = translatedText || text;
    const allText = `${title}\n${text}\n${translatedTitle}\n${translatedText}`;
    const tickers = extractTickers(item, allText);
    const sourceName = item.source?.name || item.source?.id || item.source?.type || "unknown";
    const theme = inferTheme(allText, tickers, item.source?.id || "");
    const sentiment = inferSentiment(allText, theme);
    const priceStatus = inferPriceStatus(allText);
    const rawAuthor = item.author?.handle || item.author?.display_name || "unknown";
    const canonical = canonicalAuthor(rawAuthor, item.author?.display_name, item.source?.id);
    const createdAt = item.timestamps?.created_at || item.timestamps?.collected_at || "";
    const createdMs = Date.parse(createdAt);
    const analysisPolicy = item.analysis_policy || item.raw_payload?.analysis_policy || { include: true, mode: "analysis" };
    const reviewOnly = analysisPolicy.include === false;
    const mediaCandidates = item.media
      || item.raw_payload?.static_images
      || item.raw_payload?.media?.static_images
      || item.raw_payload?.media
      || [];
    const staticImages = Array.isArray(mediaCandidates)
      ? mediaCandidates.filter((media) => media && (!media.kind || media.kind === "static_image"))
      : [];
    const replyContext = normalizeReplyContext(item.reply_context || item.raw_payload?.reply_context);

    return {
      raw: item,
      id: item.id,
      market: inferMarket(item),
      createdAt,
      createdMs,
      sourceType: item.source?.type || "",
      sourceId: item.source?.id || "",
      sourceName,
      author: canonical,
      authorDisplay: canonical,
      rawAuthor,
      externalUrl: item.external?.url || "",
      externalId: item.external?.id || "",
      text,
      title,
      tickers,
      theme,
      sentiment,
      priceStatus,
      quote: extractQuote(analysisText || title),
      reason: inferReason(analysisText || title, theme, tickers, sentiment, sourceName),
      risk: inferRisk(analysisText || title, theme, tickers, sentiment, priceStatus),
      metrics: item.metrics || {},
      analysisPolicy,
      reviewOnly,
      isReply: Boolean(item.relations?.is_reply || replyContext),
      replyContext,
      staticImages,
      language,
      translatedText,
      translatedTitle,
      summaryText,
      summaryBullets
    };
  }

  function normalizeReplyContext(value) {
    if (!value || typeof value !== "object") return null;
    const author = value.author && typeof value.author === "object" ? value.author : {};
    const media = Array.isArray(value.static_images)
      ? value.static_images.filter((item) => item && (!item.kind || item.kind === "static_image"))
      : [];
    const authorName = String(author.display_name || author.handle || "");
    const unavailablePlaceholder = authorName === "消息无法加载" && !value.id && !value.content;
    return {
      id: String(value.id || ""),
      available: value.available !== false && !unavailablePlaceholder,
      url: String(value.url || ""),
      author: unavailablePlaceholder ? "原消息作者" : (authorName || "原消息作者"),
      content: String(value.content || ""),
      timestamp: String(value.timestamp || ""),
      staticImages: media
    };
  }

  function inferMarket(item) {
    const explicit = String(item.market || item.raw_payload?.market || "").toLowerCase();
    if (["cn", "a", "a_share", "ashare", "china"].includes(explicit)) return "cn";
    if (["us", "us_stock", "america"].includes(explicit)) return "us";
    const tags = item.source?.tags || [];
    if (tags.some((tag) => ["market:cn", "a_share", "ashare"].includes(String(tag).toLowerCase()))) return "cn";
    const sourceId = String(item.source?.id || "").toLowerCase();
    const sourceType = String(item.source?.type || "").toLowerCase();
    if (["douyin", "wechat"].includes(sourceType) || sourceId.includes("jiujiujiucai") || sourceId.includes("caitangping")) return "cn";
    return "us";
  }

  function canonicalAuthor(handle, displayName, sourceId) {
    const value = `${handle || ""} ${displayName || ""} ${sourceId || ""}`.toLowerCase();
    const normalizedSourceId = String(sourceId || "").toLowerCase();
    if (value.includes("haochi") || value.includes("好吃")) return "好吃";
    if (value.includes("aleabitoreddit") || value.includes("serenity")) return "Serenity";
    if (value.includes("jiujiu") || value.includes("久韭")) return "久韭究财";
    if (value.includes("panyiyoudianshen") || value.includes("潘姨有点神")) return "潘姨有点神";
    if (
      value.includes("edgerunner")
      || normalizedSourceId.startsWith("discord_club500_")
      || normalizedSourceId === "discord_tianyi_edgerunner_trades"
      || normalizedSourceId === "x_edgerunner17888"
      || normalizedSourceId === "substack_edgerunner17888"
    ) return "Edgerunner";
    return String(displayName || handle || "未知作者").trim();
  }

  function extractTickers(item, text) {
    const values = new Set();
    for (const entity of item.entities || []) {
      if (entity.type === "ticker" && entity.normalized_value) {
        values.add(String(entity.normalized_value).toUpperCase());
      }
    }

    const cashtags = text.match(/\$[A-Za-z][A-Za-z0-9]{0,5}/g) || [];
    for (const cashtag of cashtags) values.add(cashtag.slice(1).toUpperCase());

    for (const ticker of knownTickers) {
      const re = new RegExp(`(^|[^A-Za-z0-9])${escapeRegex(ticker)}([^A-Za-z0-9]|$)`, "i");
      if (re.test(text)) values.add(ticker);
    }
    return Array.from(values).filter((ticker) => !excludedTickers.has(ticker)).sort();
  }

  function inferTheme(text, tickers, sourceId) {
    const lower = text.toLowerCase();
    const has = (...words) => words.some((word) => lower.includes(word.toLowerCase()));
    const includesTicker = (...values) => values.some((value) => tickers.includes(value));

    if (has("fomc", "fed", "warsh", "dovish", "rate cut", "点阵图", "美联储")) return "宏观流动性";
    if (includesTicker("SPCX") || has("spcx")) return "特殊事件/AI平台";
    if (includesTicker("LPK") || has("glass substrate", "glass substrates", "nasdaq listing", "tam greatly")) return "先进封装/玻璃基板";
    if (has("photonics", "cw laser", "eml", "cpo", "laser capacity") || includesTicker("AAOI", "SIVE", "LITE", "COHR", "AXTI", "AEHR")) return "Photonics/CW Laser";
    if (has("memory", "dram", "nand", "samsung", "sk hynix") || includesTicker("MU", "SNDK", "EWY")) return "Memory";
    if (has("neocloud", "energy") || includesTicker("NBIS", "XLE", "XLU")) return "Neoclouds/Energy";
    if (includesTicker("MSFT", "ORCL", "CRM", "RDDT") || has("software", "软件", "saas")) return "软件/SaaS";
    if (includesTicker("AMD", "AVGO", "ARM", "MRVL", "NVDA", "INTC") || has("半导体", "ai hardware", "ai ")) return "AI 半导体";
    if (includesTicker("MP") || has("稀土")) return "稀土/材料";
    if (sourceId.includes("discord_tianyi")) return "交易动作";
    return "综合观察";
  }

  function sectorForItem(item) {
    if (item.market === "cn") {
      const text = `${item.text || ""} ${item.title || ""} ${item.translatedText || ""}`;
      return cnSectorDefinitions.find(([, pattern]) => pattern.test(text))?.[0] || "其他板块";
    }
    const sectors = uniqueSorted((item.tickers || []).map((ticker) => sectorForTicker(ticker)));
    return sectors[0] || "其他板块";
  }

  function sectorForTicker(ticker) {
    const normalized = String(ticker || "").toUpperCase();
    return tickerSectorGroups.find(([, members]) => members.has(normalized))?.[0] || "其他标的";
  }

  function inferSentiment(text) {
    const lower = String(text || "").toLowerCase();
    const bullishContextOverrides = [
      /(?:\bmu\b[^。！？；\n]{0,120}不要买中国内存|不要买中国内存[^。！？；\n]{0,120}\bmu\b)/,
      /i think i['’]?m putting my money on[^。.!?\n]{0,100}(?:jensen|nvidia)/,
      /(?:jensen|nvidia)[^。.!?\n]{0,100}(?:leading indicator|put(?:ting)? my money on)/
    ];
    if (bullishContextOverrides.some((pattern) => pattern.test(lower))) return "看涨";
    const semantic = lower
      .replace(/(?:不|不会|不再|别|不要|无需|无须)[^。！？；\n]{0,12}(?:卖出|卖|减仓|清仓|sell)/g, " 明确继续持有 ")
      .replace(/(?:not|won't|wouldn't|don't)\s+(?:recommend\s+)?sell(?:ing)?/g, " keep holding ")
      .replace(/除非[^。！？；\n]{0,36}(?:熊市|利空|风险)/g, " 条件风险 ");
    const score = (patterns) => patterns.reduce((total, pattern) => total + (pattern.test(semantic) ? 1 : 0), 0);
    const bullish = score([
      /大胆入场|低位[^。！？；\n]{0,10}(?:入场|买|加仓)|不会建议[^。！？；\n]{0,12}卖|继续持有|继续拿|拿住|持有|买入|加仓|建仓|抄底/,
      /牛市|看涨|看多|更强|走强|反弹|突破|新高|上行|利好|超预期|低估|便宜|机会/,
      /\b(?:buy|bought|added|adding|long|hold|holding|bullish|undervalued|cheap|upside|breakout|outperform)\b/,
      /support|dovish|supply constrained|keep holding/
    ]);
    const bearish = score([
      /建议[^。！？；\n]{0,10}(?:卖出|减仓|清仓)|卖出|清仓|减仓|止损|锁利|止盈|离场|看跌|看空/,
      /熊市|走弱|很软|下跌|暴跌|崩盘|破位|利空|低于预期|高估|泡沫/,
      /不建议[^。！？；\n]{0,10}(?:买入|买|入场)|不要[^。！？；\n]{0,10}(?:买入|买|追)/,
      /\b(?:sell|sold|bearish|downside|underperform|stop loss|take profit|lock profit)\b/
    ]);
    const watching = score([/观察|观望|等待|再看|等回调|不确定|没有明确观点/, /\b(?:wait|watch|neutral|no firm opinion)\b|let[’']s see/]);
    if (bullish > bearish && bullish >= watching) return "看涨";
    if (bearish > bullish && bearish >= watching) return "看跌";
    if (watching > 0 && watching >= Math.max(bullish, bearish)) return "观望";
    if (bullish > 0 && bearish === 0) return "看涨";
    if (bearish > 0 && bullish === 0) return "看跌";
    return "中性";
  }

  function inferPriceStatus(text) {
    const lower = text.toLowerCase();
    if (hasAny(lower, ["tripled", "ath", "all time high", "+", "up ", "暴涨", "已涨", "锁利", "take profit", "目标", "涨"])) return "已涨";
    if (hasAny(lower, ["undervalued", "support", "buy", "bought", "added", "加仓", "低位", "未充分", "market missed"])) return "未涨/待兑现";
    return "未涨/待验证";
  }

  function fillFilterOptions() {
    const marketItems = items.filter((item) => item.market === state.market);
    renderSourceOptions(marketItems);
    fillSelect(els.tickerFilter, [["", "全部标的"], ...uniqueOptions(marketItems.flatMap((item) => item.tickers), (value) => value)]);
    fillSelect(els.sectorFilter, [["", "全部板块"], ...uniqueOptions(marketItems.map((item) => sectorForItem(item)), (value) => value)]);
    if (els.tickerField) els.tickerField.hidden = state.market === "cn";
    const filterGrid = document.querySelector(".filter-grid");
    if (filterGrid) filterGrid.dataset.market = state.market;
    renderAuthorOptions(marketItems);
  }

  function renderSourceOptions(marketItems) {
    const sources = Array.from(new Set(marketItems.map((item) => item.sourceId))).sort((a, b) => sourceLabel(a).localeCompare(sourceLabel(b), "zh-CN"));
    state.sources = new Set(Array.from(state.sources).filter((source) => sources.includes(source)));
    els.sourceFilterMenu.innerHTML = sources.map((source) => {
      const sourceRows = marketItems.filter((item) => item.sourceId === source);
      const count = sourceRows.length;
      const type = sourceRows[0]?.sourceType || "";
      return `<label class="multi-select-option"><input type="checkbox" value="${escapeAttribute(source)}" ${state.sources.has(source) ? "checked" : ""}><span class="multi-check" aria-hidden="true">✓</span><span class="multi-source-channel">${escapeHtml(channelLabel(type))}</span><span class="multi-source-name">${escapeHtml(sourceDisplayName(source, type))}</span><small class="multi-source-count">${count} 条</small></label>`;
    }).join("");
    els.sourceFilterMenu.querySelectorAll('input[type="checkbox"]').forEach((input) => input.addEventListener("change", () => { if (input.checked) state.sources.add(input.value); else state.sources.delete(input.value); updateSourceFilterLabel(); render(); }));
    updateSourceFilterLabel();
  }

  function updateSourceFilterLabel() {
    const selected = Array.from(state.sources);
    els.sourceFilterLabel.textContent = selected.length ? selected.map((source) => sourceChannelLabel(source)).join("、") : "全部来源";
    els.sourceFilterTrigger.classList.toggle("has-value", selected.length > 0);
  }

  function renderAuthorOptions(marketItems) {
    const authors = Array.from(new Set(marketItems.map((item) => item.author))).sort((a, b) => a.localeCompare(b, "zh-CN"));
    state.authors = new Set(Array.from(state.authors).filter((author) => authors.includes(author)));
    els.authorFilterMenu.innerHTML = authors.map((author) => `
      <label class="multi-select-option">
        <input type="checkbox" value="${escapeAttribute(author)}" ${state.authors.has(author) ? "checked" : ""}>
        <span class="multi-check" aria-hidden="true">✓</span>
        <span>${escapeHtml(author)}</span>
        <small>${marketItems.filter((item) => item.author === author).length} 条</small>
      </label>`).join("");
    els.authorFilterMenu.querySelectorAll('input[type="checkbox"]').forEach((input) => {
      input.addEventListener("change", () => {
        if (input.checked) state.authors.add(input.value);
        else state.authors.delete(input.value);
        updateAuthorFilterLabel();
        render();
      });
    });
    updateAuthorFilterLabel();
  }

  function updateAuthorFilterLabel() {
    const selected = Array.from(state.authors);
    els.authorFilterLabel.textContent = selected.length ? selected.join("、") : "全部作者";
    els.authorFilterTrigger.classList.toggle("has-value", selected.length > 0);
  }

  function bindEvents() {
    els.marketTabs.forEach((button) => {
      button.addEventListener("click", () => switchMarket(button.dataset.market));
    });
    els.viewTabs.forEach((button) => {
      button.addEventListener("click", () => switchView(button.dataset.view));
    });
    document.querySelectorAll("[data-switch-view]").forEach((button) => {
      button.addEventListener("click", () => switchView(button.dataset.switchView));
    });

    els.reviewStartDate.addEventListener("change", applyReviewRange);
    els.reviewEndDate.addEventListener("change", applyReviewRange);
    els.clearReviewRange.addEventListener("click", () => {
      state.reviewStartDate = "";
      state.reviewEndDate = "";
      els.reviewStartDate.value = "";
      els.reviewEndDate.value = "";
      render();
    });
    els.rawReviewSort.addEventListener("click", () => {
      state.reviewSort = state.reviewSort === "desc" ? "asc" : "desc";
      updateRawSortControl();
      renderDailyOriginals(filterReviewItems());
    });
    els.rawGroupOptions.forEach((button) => {
      button.addEventListener("click", () => {
        state.reviewGroup = button.dataset.rawGroup === "author" ? "author" : "date";
        updateRawGroupControl();
        renderDailyOriginals(filterReviewItems());
      });
    });
    els.sourceFilterTrigger.addEventListener("click", () => {
      const open = els.sourceFilterMenu.hidden;
      els.sourceFilterMenu.hidden = !open;
      els.sourceFilterTrigger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    els.authorFilterTrigger.addEventListener("click", () => {
      const open = els.authorFilterMenu.hidden;
      els.authorFilterMenu.hidden = !open;
      els.authorFilterTrigger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".author-field")) { els.authorFilterMenu.hidden = true; els.authorFilterTrigger.setAttribute("aria-expanded", "false"); }
      if (!event.target.closest(".source-field")) { els.sourceFilterMenu.hidden = true; els.sourceFilterTrigger.setAttribute("aria-expanded", "false"); }
      const imageTrigger = event.target.closest("[data-image-preview]");
      if (imageTrigger) {
        event.preventDefault();
        openImageLightbox(imageTrigger.dataset.imagePreview, imageTrigger.dataset.imageAlt || "图片预览");
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeImageLightbox();
    });


    [
      [els.tickerFilter, "ticker"],
      [els.sectorFilter, "sector"]
    ].forEach(([element, key]) => {
      element.addEventListener("change", () => {
        state[key] = element.value;
        render();
      });
    });


    els.resetFilters.addEventListener("click", () => {
      state.sources.clear();
      state.authors.clear();
      state.ticker = "";
      state.sector = "";
            els.tickerFilter.value = "";
      els.sectorFilter.value = "";
      fillReviewDateRange();
      renderAuthorOptions(items.filter((item) => item.market === state.market));
      render();
    });

    els.closeDrawer.addEventListener("click", closeDrawer);
    els.drawerScrim.addEventListener("click", closeDrawer);
    els.copyContext.addEventListener("click", () => copyCurrentContext("markdown"));
    els.copyJson.addEventListener("click", () => copyCurrentContext("json"));
  }

  let imageZoom = 1;

  function initImageLightbox() {
    if (document.getElementById("imageLightbox")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <div id="imageLightbox" class="image-lightbox" hidden role="dialog" aria-modal="true" aria-label="图片预览">
        <div class="image-lightbox-backdrop" data-image-lightbox-close></div>
        <div class="image-lightbox-panel">
          <div class="image-lightbox-toolbar">
            <button type="button" class="secondary-btn" data-image-zoom-out aria-label="缩小">−</button>
            <button type="button" class="secondary-btn" data-image-zoom-reset>还原</button>
            <button type="button" class="secondary-btn" data-image-zoom-in aria-label="放大">＋</button>
            <button type="button" class="secondary-btn" data-image-lightbox-close>关闭</button>
          </div>
          <div class="image-lightbox-stage"><img id="imageLightboxImage" alt=""></div>
        </div>
      </div>`);
    document.getElementById("imageLightbox").addEventListener("click", (event) => {
      if (event.target.closest("[data-image-lightbox-close]")) closeImageLightbox();
      if (event.target.closest("[data-image-zoom-in]")) setImageZoom(imageZoom + 0.25);
      if (event.target.closest("[data-image-zoom-out]")) setImageZoom(imageZoom - 0.25);
      if (event.target.closest("[data-image-zoom-reset]")) setImageZoom(1);
    });
  }

  function setImageZoom(value) {
    imageZoom = Math.min(4, Math.max(0.5, value));
    const image = document.getElementById("imageLightboxImage");
    if (!image || !image.naturalWidth || !image.naturalHeight) return;
    const stage = image.closest(".image-lightbox-stage");
    const availableWidth = Math.max(320, (stage?.clientWidth || window.innerWidth) - 24);
    const availableHeight = Math.max(240, (stage?.clientHeight || window.innerHeight) - 24);
    const fitScale = Math.min(availableWidth / image.naturalWidth, availableHeight / image.naturalHeight, 1);
    const width = Math.max(1, Math.round(image.naturalWidth * fitScale * imageZoom));
    const height = Math.max(1, Math.round(image.naturalHeight * fitScale * imageZoom));
    image.style.width = `${width}px`;
    image.style.height = `${height}px`;
    image.style.maxWidth = "none";
    image.style.maxHeight = "none";
    image.style.transform = "none";
  }

  function openImageLightbox(src, alt) {
    const lightbox = document.getElementById("imageLightbox");
    const image = document.getElementById("imageLightboxImage");
    if (!lightbox || !image || !src) return;
    image.src = src;
    image.alt = alt || "图片预览";
    image.onload = () => setImageZoom(1);
    if (image.complete) setImageZoom(1);
    lightbox.hidden = false;
    document.body.classList.add("image-lightbox-open");
  }

  function closeImageLightbox() {
    const lightbox = document.getElementById("imageLightbox");
    if (!lightbox || lightbox.hidden) return;
    lightbox.hidden = true;
    document.body.classList.remove("image-lightbox-open");
  }

  function switchView(view) {
    if (!view) return;
    state.view = view;
    els.viewTabs.forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    els.viewPanels.forEach((panel) => {
      const active = panel.dataset.viewPanel === view;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function switchMarket(market) {
    if (!market || market === state.market) return;
    state.market = market;
    state.sources.clear();
    state.authors.clear();
    state.ticker = "";
    state.sector = "";
    fillFilterOptions();
    fillReviewDateRange();
    render();
  }

  function fillReviewDateRange(preserveRange = false) {
    const dates = items
      .filter((item) => item.market === state.market && Number.isFinite(item.createdMs))
      .map((item) => toLocalParts(item.createdMs, state.timezone).date)
      .sort((a, b) => b.localeCompare(a));
    const latest = dates[0] || "";
    const earliest = dates[dates.length - 1] || "";
    els.reviewStartDate.min = earliest;
    els.reviewStartDate.max = latest;
    els.reviewEndDate.min = earliest;
    els.reviewEndDate.max = latest;
    if (!preserveRange || !state.reviewStartDate || !state.reviewEndDate) {
      state.reviewStartDate = latest;
      state.reviewEndDate = latest;
    }
    els.reviewStartDate.value = state.reviewStartDate;
    els.reviewEndDate.value = state.reviewEndDate;
  }

  function applyReviewRange() {
    let start = els.reviewStartDate.value;
    let end = els.reviewEndDate.value;
    if (start && end && start > end) [start, end] = [end, start];
    state.reviewStartDate = start;
    state.reviewEndDate = end;
    els.reviewStartDate.value = start;
    els.reviewEndDate.value = end;
    render();
  }

  function reviewDateLabel() {
    const start = state.reviewStartDate;
    const end = state.reviewEndDate;
    if (!start && !end) return "全部日期";
    if (start === end) return formatTrendDate(start);
    if (!start) return `截至 ${formatTrendDate(end)}`;
    if (!end) return `${formatTrendDate(start)} 起`;
    return `${start.slice(5).replace("-", ".")} — ${end.slice(5).replace("-", ".")}`;
  }

  function updateRawSortControl() {
    const ascending = state.reviewSort === "asc";
    els.rawReviewSort.classList.toggle("is-ascending", ascending);
    els.rawReviewSort.querySelector("span").textContent = ascending ? "⇈" : "⇊";
    els.rawReviewSort.title = ascending ? "顺序 · 最早在前" : "倒序 · 最新在前";
    els.rawReviewSort.setAttribute(
      "aria-label",
      ascending ? "当前顺序：最早在前。点击切换为倒序" : "当前倒序：最新在前。点击切换为顺序"
    );
  }

  function updateRawGroupControl() {
    els.rawGroupOptions.forEach((button) => {
      const active = button.dataset.rawGroup === state.reviewGroup;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function render() {
    updateRawSortControl();
    updateRawGroupControl();
    renderMarketContext();
    filteredItems = filterItems();
    const analysisItems = filteredItems.filter((item) => !item.reviewOnly);
    analysisPromptCache.clear();
    analysisPromptSeq = 0;
    renderDailyOriginals(filterReviewItems());
    renderSourceInsights(analysisItems);
    renderTickerHistory(analysisItems);
    renderActiveFilterSummary(analysisItems);
  }

  function withinReviewRange(item) {
    const date = toLocalParts(item.createdMs, state.timezone).date;
    if (state.reviewStartDate && date < state.reviewStartDate) return false;
    if (state.reviewEndDate && date > state.reviewEndDate) return false;
    return true;
  }

  function filterReviewItems() {
    return items.filter((item) => {
      if (item.market !== state.market) return false;
      if (!withinReviewRange(item)) return false;
      if (state.sources.size && !state.sources.has(item.sourceId)) return false;
      if (state.authors.size && !state.authors.has(item.author)) return false;
      return true;
    });
  }

  function renderMarketContext() {
    const counts = {
      us: items.filter((item) => item.market === "us").length,
      cn: items.filter((item) => item.market === "cn").length
    };
    els.usMarketCount.textContent = `${counts.us} 条情报`;
    els.cnMarketCount.textContent = `${counts.cn} 条情报`;
    els.marketTabs.forEach((button) => {
      const active = button.dataset.market === state.market;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.body.dataset.market = state.market;
    if (state.market === "cn") {
      els.marketKicker.textContent = "CHINA A-SHARE";
      els.marketTitle.textContent = "A股情报";
      els.marketDescription.textContent = "先按天审阅抖音与公众号原文，再进入题材和标的分析。";
      els.sourceInsightNote.textContent = "A股观点按板块聚合，不要求原文必须给出具体标的。";
      els.marketSourceRoster.innerHTML = `
        <article class="source-ready-card">
          <span class="source-platform douyin">抖音</span>
          <strong>久韭究财</strong>
          <small>已接入 · 视频 → 转写 → 分析</small>
        </article>
        <article class="source-ready-card">
          <span class="source-platform douyin">抖音</span>
          <strong>潘姨有点神</strong>
          <small>已接入 · 视频 → 转写 → 分析</small>
        </article>
        <article class="source-ready-card">
          <span class="source-platform wechat">公众号</span>
          <strong>财躺平</strong>
          <small>链接入库 · 等待新文章链接</small>
        </article>`;
    } else {
      els.marketKicker.textContent = "US MARKET";
      els.marketTitle.textContent = "美股情报";
      els.marketDescription.textContent = "先按天审阅 X、Discord 与 Substack 原文，再进入题材和标的分析。";
      els.sourceInsightNote.textContent = "只展示当前作者和筛选条件命中的观点。";
      els.marketSourceRoster.innerHTML = `
        <article class="source-ready-card">
          <span class="source-platform x">X</span>
          <strong>3 个账号</strong>
          <small>已接入</small>
        </article>
        <article class="source-ready-card">
          <span class="source-platform discord">Discord</span>
          <strong>2 个频道</strong>
          <small>已接入</small>
        </article>
        <article class="source-ready-card">
          <span class="source-platform substack">Substack</span>
          <strong>Edgerunner</strong>
          <small>已接入</small>
        </article>`;
    }
    if (apiAvailable) {
      updateDataStatus(`${state.market === "cn" ? "A股" : "美股"} · ${counts[state.market]} 条`, "online");
    } else {
      updateDataStatus("API 离线 · 无法加载数据", "offline");
    }
  }

  function filterItems() {
    return items.filter((item) => {
      if (item.market !== state.market) return false;
      if (!withinReviewRange(item)) return false;
      if (state.sources.size && !state.sources.has(item.sourceId)) return false;
      if (state.authors.size && !state.authors.has(item.author)) return false;
      if (state.ticker && !item.tickers.includes(state.ticker)) return false;
      if (state.sector && sectorForItem(item) !== state.sector) return false;
      return true;
    });
  }

  function renderDailyOriginals(rows) {
    const direction = state.reviewSort === "asc" ? 1 : -1;
    const days = Array.from(groupBy(rows, (item) => toLocalParts(item.createdMs, state.timezone).date).entries())
      .sort((a, b) => direction * a[0].localeCompare(b[0]));
    const authorGroups = Array.from(groupBy(rows, (item) => item.author).entries())
      .sort((a, b) => {
        const aEdge = direction === 1 ? Math.min(...a[1].map((item) => item.createdMs)) : Math.max(...a[1].map((item) => item.createdMs));
        const bEdge = direction === 1 ? Math.min(...b[1].map((item) => item.createdMs)) : Math.max(...b[1].map((item) => item.createdMs));
        return direction * (aEdge - bEdge) || a[0].localeCompare(b[0], "zh-CN");
      });

    els.rawReviewHint.textContent = rows.length
      ? `${days.length} 天 · ${authorGroups.length} 位作者 · ${rows.length} 条原文 · 当前按${state.reviewGroup === "author" ? "作者" : "日期"}折叠`
      : "当前筛选条件下没有原文";

    if (!days.length) {
      els.dailyOriginals.innerHTML = `<div class="empty-state">当前筛选条件下没有可审阅的原文</div>`;
      return;
    }

    if (state.reviewGroup === "author") {
      els.dailyOriginals.innerHTML = authorGroups
        .map(([author, authorRows], authorIndex) => renderRawAuthorFold(author, authorRows, authorIndex))
        .join("");
    } else {
      els.dailyOriginals.innerHTML = days.map(([date, dayRows], dayIndex) => {
        const dayAuthorGroups = Array.from(groupBy(dayRows, (item) => item.author).entries())
          .sort((a, b) => {
            const aEdge = direction === 1 ? Math.min(...a[1].map((item) => item.createdMs)) : Math.max(...a[1].map((item) => item.createdMs));
            const bEdge = direction === 1 ? Math.min(...b[1].map((item) => item.createdMs)) : Math.max(...b[1].map((item) => item.createdMs));
            return direction * (aEdge - bEdge) || direction * (a[1].length - b[1].length);
          });
        const sourceCount = new Set(dayRows.map((item) => item.sourceId)).size;
        return `
          <details class="raw-day" ${dayIndex === 0 ? "open" : ""}>
            <summary class="raw-day-summary">
              <span class="raw-day-date">${escapeHtml(formatTrendDate(date))}</span>
              <span class="raw-day-meta">${dayRows.length} 条 · ${dayAuthorGroups.length} 位作者 · ${sourceCount} 个来源</span>
            </summary>
            <div class="raw-author-groups">
              ${dayAuthorGroups.map(([, authorRows]) => renderRawAuthorGroup(authorRows)).join("")}
            </div>
          </details>`;
      }).join("");
    }

    els.dailyOriginals.querySelectorAll("[data-raw-analyze]").forEach((button) => {
      button.addEventListener("click", () => openDrawer(button.dataset.rawAnalyze));
    });
  }

  function renderActiveFilterSummary(rows) {
    const filters = [];
    if (state.reviewStartDate || state.reviewEndDate) filters.push(reviewDateLabel());
    if (state.authors.size) filters.push(`作者：${Array.from(state.authors).join("、")}`);
    if (state.sources.size) filters.push(`来源：${Array.from(state.sources).map(sourceLabel).join("、")}`);
    if (state.ticker) filters.push(`标的：${state.ticker}`);
    if (state.sector) filters.push(`板块：${state.sector}`);
    els.activeFilterSummary.innerHTML = `
      <span class="result-count"><strong>${rows.length}</strong> 条可分析信息</span>
      ${filters.map((filter) => `<span class="filter-chip">${escapeHtml(filter)}</span>`).join("")}`;
  }

  function renderRawAuthorGroup(authorRows) {
    const direction = state.reviewSort === "asc" ? 1 : -1;
    const sortedRows = authorRows.slice().sort((a, b) => direction * (a.createdMs - b.createdMs));
    const lead = sortedRows[0];
    const channels = Array.from(new Set(sortedRows.map((item) => channelLabel(item.sourceType))));
    const sources = Array.from(new Set(sortedRows.map((item) => item.sourceName)));
    return `
      <details class="raw-author-group" open>
        <summary class="raw-author-head">
          <div>
            <h3>${escapeHtml(lead.authorDisplay)}</h3>
            <p><span class="raw-channel raw-channel-${escapeAttribute(lead.sourceType)}">${escapeHtml(channels.join(" + "))}</span>${escapeHtml(sources.join(" · "))}</p>
          </div>
          <span class="raw-author-count">${sortedRows.length} 条</span>
        </summary>
        <div class="raw-items">
          ${sortedRows.map((item) => renderRawItem(item)).join("")}
        </div>
      </details>`;
  }

  function renderRawAuthorFold(author, authorRows, authorIndex) {
    const direction = state.reviewSort === "asc" ? 1 : -1;
    const sortedRows = authorRows.slice().sort((a, b) => direction * (a.createdMs - b.createdMs));
    const channels = Array.from(new Set(sortedRows.map((item) => channelLabel(item.sourceType))));
    const sources = Array.from(new Set(sortedRows.map((item) => sourceLabel(item.sourceId))));
    const dates = sortedRows.map((item) => toLocalParts(item.createdMs, state.timezone).date).sort();
    const dateLabel = dates[0] === dates[dates.length - 1]
      ? formatTrendDate(dates[0])
      : `${formatTrendDate(dates[0])} — ${formatTrendDate(dates[dates.length - 1])}`;
    return `
      <details class="raw-author-fold" ${authorIndex === 0 ? "open" : ""}>
        <summary class="raw-author-fold-summary">
          <span class="raw-author-fold-name">${escapeHtml(author)}</span>
          <span class="raw-author-fold-meta">${sortedRows.length} 条 · ${escapeHtml(channels.join(" + "))} · ${escapeHtml(dateLabel)}</span>
        </summary>
        <div class="raw-author-fold-body">
          <p class="raw-author-source-line">${escapeHtml(sources.join(" · "))}</p>
          <div class="raw-items">${sortedRows.map((item) => renderRawItem(item)).join("")}</div>
        </div>
      </details>`;
  }

  function renderRawItem(item) {
    const originalValue = String(item.text || item.title || "").trim();
    const rawTitle = String(item.title || "").trim();
    const discordImageTitle = /^discord\s*静态图片\s*[（(]\s*\d+\s*张\s*[）)]$/i;
    const discordImagePlaceholder = /^静态图片附件\s*[（(]\s*\d+\s*张\s*[，,]?\s*无动图\s*[）)]$/i;
    const hidePlaceholderTitle = item.sourceType === "discord"
      && (/^discord\s*原文$/i.test(rawTitle) || discordImageTitle.test(rawTitle));
    const original = item.sourceType === "discord" && discordImagePlaceholder.test(originalValue) ? "" : originalValue;
    const longText = original.length > 620;
    const duplicateTitle = rawTitle && original.length >= rawTitle.length
      && original.slice(0, rawTitle.length).trim() === rawTitle.trim();
    const title = hidePlaceholderTitle || duplicateTitle ? "" : rawTitle;
    const mediaTitle = title || `${item.authorDisplay || channelLabel(item.sourceType)}内容`;
    const isSubstackSummary = item.sourceType === "substack" && Boolean(item.summaryText || item.summaryBullets.length);
    return `
      <article id="${escapeAttribute(rawItemAnchor(item.id))}" class="raw-item">
        <div class="raw-item-head">
          <div>
            <time datetime="${escapeAttribute(item.createdAt)}">${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))}</time>
            ${title ? `<h4>${escapeHtml(title)}</h4>` : ""}
          </div>
          <div class="raw-item-tags">
            ${isSubstackSummary ? "" : (item.reviewOnly ? `<span class="review-only-tag">仅原文审阅 · 订阅预览</span>` : renderSentiment(item.sentiment))}
            ${item.reviewOnly ? "" : item.tickers.slice(0, 4).map((ticker) => `<span class="tag">${escapeHtml(ticker)}</span>`).join("")}
          </div>
        </div>
        ${renderReplyContext(item.replyContext)}
        ${isSubstackSummary ? renderSubstackSummary(item) : (original ? (longText
          ? `<div class="raw-original raw-original-preview">${escapeHtml(original.slice(0, 620))}…</div>
             <details class="raw-full-details">
               <summary>展开 / 收起完整原文</summary>
               <div class="raw-original raw-original-full">${escapeHtml(original)}</div>
             </details>`
          : `<div class="raw-original raw-original-full">${escapeHtml(original)}</div>`) : "")}
        ${!isSubstackSummary && item.translatedText ? `
          <section class="raw-translation" aria-label="中文翻译">
            <div class="raw-translation-head"><span>中文翻译</span><small>Codex 上下文复核</small></div>
            <div class="raw-original raw-original-full">${escapeHtml(item.translatedText)}</div>
          </section>` : ""}
        ${isSubstackSummary ? "" : renderStaticImages(item.staticImages, mediaTitle)}
        <div class="raw-item-actions">
          ${item.reviewOnly ? "" : `<button class="secondary-btn" type="button" data-raw-analyze="${escapeAttribute(item.id)}">查看详情 / 分析</button>`}
          ${item.externalUrl ? `<a class="secondary-link" href="${escapeAttribute(item.externalUrl)}" target="_blank" rel="noreferrer">打开来源</a>` : ""}
        </div>
      </article>`;
  }

  function renderSubstackSummary(item) {
    return `
      <section class="substack-summary" aria-label="Substack 文章摘要">
        <div class="substack-summary-head"><span>Codex 摘要</span><small>全文请通过“打开来源”阅读</small></div>
        ${item.summaryText ? `<p>${escapeHtml(item.summaryText)}</p>` : ""}
        ${item.summaryBullets.length ? `<ul>${item.summaryBullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("")}</ul>` : ""}
      </section>`;
  }

  function renderReplyContext(context) {
    if (!context) return "";
    const timestampMs = Date.parse(context.timestamp);
    const timestamp = Number.isFinite(timestampMs) ? formatDisplayTime(timestampMs, state.timezone) : "时间未知";
    const content = context.available ? (context.content || (context.staticImages.length ? "" : "原回复无文字内容")) : "原回复不可用或无权查看";
    return `
      <aside class="reply-context" aria-label="被回复消息">
        <div class="reply-context-head">
          <span>回复上下文</span>
          <strong>${escapeHtml(context.author)}</strong>
          <time>${escapeHtml(timestamp)}</time>
          ${context.url ? `<a href="${escapeAttribute(context.url)}" target="_blank" rel="noreferrer">打开原消息</a>` : ""}
        </div>
        ${content ? `<div class="reply-context-text">${escapeHtml(content)}</div>` : ""}
        ${renderStaticImages(context.staticImages, `${context.author} 被回复内容`)}
      </aside>`;
  }

  function renderStaticImages(images, title) {
    if (!images.length) return "";
    return `<div class="raw-media-grid">${images.map((media, index) => {
      const src = resolveMediaUrl(media.api_url || media.url || "");
      if (!src) return "";
      const alt = `${title} 图片 ${index + 1}`;
      return `<a href="${escapeAttribute(src)}" data-image-preview="${escapeAttribute(src)}" data-image-alt="${escapeAttribute(alt)}" aria-label="${escapeAttribute(alt)}"><img src="${escapeAttribute(src)}" loading="lazy" alt="${escapeAttribute(alt)}"></a>`;
    }).join("")}</div>`;
  }

  function resolveMediaUrl(value) {
    if (!value) return "";
    if (/^https?:\/\//i.test(value)) return value;
    const apiOrigin = API_BASE.replace(/\/api\/?$/, "");
    return `${apiOrigin}${value.startsWith("/") ? "" : "/"}${value}`;
  }

  function channelLabel(sourceType) {
    const labels = {
      x: "X",
      discord: "Discord",
      substack: "Substack",
      douyin: "抖音",
      wechat: "公众号"
    };
    return labels[sourceType] || sourceType || "来源";
  }

  function renderStats(rows) {
    const sourceSet = new Set(rows.map((item) => item.sourceId));
    const tickerCounts = countValues(rows.flatMap((item) => item.tickers));
    const themeCounts = countValues(rows.map((item) => item.theme));
    const sentimentCounts = countValues(rows.map((item) => item.sentiment));
    const topTickers = Object.entries(tickerCounts).sort((a, b) => b[1] - a[1]).slice(0, 5);
    const topTheme = topTradableThemes(themeCounts, 1)[0]?.[0] || topEntries(themeCounts, 1)[0]?.[0] || "暂无题材";
    const dominantSentiment = topEntries(sentimentCounts, 1)[0]?.[0] || "中性";
    els.statCount.textContent = rows.length;
    const windowText = `${state.startAt.replace("T", " ")} 到 ${state.endAt.replace("T", " ")}`;
    els.statWindow.textContent = windowText;
    els.statWindowShort.textContent = rows.length ? `${state.startAt.slice(5, 10)} 至 ${state.endAt.slice(5, 10)}` : "-";
    els.statSources.textContent = sourceSet.size;
    els.statSourcesShort.textContent = sourceSet.size;
    const sourceText = Array.from(sourceSet).slice(0, 3).map(sourceLabel).join(" / ") || "-";
    els.statSourceText.textContent = sourceText;
    els.statSourceTextShort.textContent = sourceText;
    els.statTickers.textContent = Object.keys(tickerCounts).length;
    els.statTickersShort.textContent = Object.keys(tickerCounts).length;
    els.statTickerText.textContent = topTickers.map(([ticker, count]) => `${ticker}×${count}`).join(" / ") || "-";
    els.marketBias.innerHTML = renderSentiment(dominantSentiment);
    els.marketBiasText.textContent = buildMarketBiasText(rows, topTheme, dominantSentiment, topTickers);
    els.coreTheme.textContent = topTheme;
    els.coreThemeText.textContent = topTradableThemes(themeCounts, 4).map(([theme, count]) => `${theme} ${count} 条`).join("；") || "暂无命中题材";
    els.riskBadge.innerHTML = renderRiskBadge(rows);
    els.riskSummary.textContent = buildRiskSummary(rows, topTickers);
  }

  function renderFundamentalAnalysis(rows) {
    const sections = buildFundamentalRows(rows);
    els.fundamentalBody.innerHTML = sections.map((row) => `
      <tr>
        <td>${escapeHtml(row.direction)}</td>
        <td>${renderSentiment(row.sentiment)}</td>
        <td>${escapeHtml(row.evidence)}</td>
        <td class="quote">${escapeHtml(row.quote)}</td>
        <td>${escapeHtml(row.risk)}</td>
        <td><button class="row-btn analysis-copy-btn" data-copy-analysis="${escapeAttribute(registerAnalysisPrompt(buildAnalysisPrompt("fundamental", row)))}">分析</button></td>
      </tr>
    `).join("") || `<tr><td colspan="6" class="empty-state">当前筛选条件下没有基本面分析</td></tr>`;
    bindAnalysisPromptButtons(els.fundamentalBody);
  }

  function renderSourceInsights(rows) {
    const groups = Array.from(groupBy(rows, (item) => item.author).entries())
      .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], "zh-CN"));
    els.sourceInsightTables.innerHTML = groups.map(([author, sourceRows], index) => {
      const insights = state.market === "cn" ? buildCnSourceSectorRows(sourceRows) : buildSourceInsightRows(sourceRows);
      const sourceTypes = uniqueSorted(sourceRows.map((item) => channelLabel(item.sourceType)));
      const sourceNames = uniqueSorted(sourceRows.map((item) => sourceLabel(item.sourceId)));
      return `
        <section class="source-section">
          <div class="source-title-line">
            <div><span class="source-order">${String(index + 1).padStart(2, "0")}</span><div><h3>${escapeHtml(author)}</h3><p class="source-channel-list">${escapeHtml(sourceNames.join(" · "))}</p></div></div>
            <span class="source-badge">${escapeHtml(sourceTypes.join(" + "))} · ${sourceRows.length} 条原始信息</span>
          </div>
          <div class="insight-card-grid">${insights.map(renderInsightCard).join("")}</div>
        </section>
      `;
    }).join("") || `<div class="empty-state">当前筛选条件下没有信息源观点</div>`;
    bindAnalysisPromptButtons(els.sourceInsightTables);
    bindRawItemJumpButtons();
  }

  function renderTickerHistory(rows) {
    const sectorMap = new Map();
    for (const item of rows) {
      const sectors = state.market === "cn"
        ? new Set(cnSectorsForItem(item))
        : new Set(item.tickers.map((ticker) => sectorForTicker(ticker)));
      if (!sectors.size) continue;
      for (const sector of sectors) {
        if (!sectorMap.has(sector)) sectorMap.set(sector, []);
        sectorMap.get(sector).push(item);
      }
    }
    const sectors = Array.from(sectorMap.entries())
      .sort((a, b) => b[1].length - a[1].length);
    const preparedSectors = sectors.map(([sector, sectorRows], sectorIndex) => ({
      sector,
      sectorId: `history-sector-${sectorIndex}`,
      sectorRows,
      panelId: `history-sector-panel-${sectorIndex}`,
      groupKey: `${sectorIndex}`
    }));
    const directory = preparedSectors.length ? `
      <nav class="history-directory" aria-label="标的历史快速目录">
          <div class="history-directory-head"><strong>快速目录</strong><span>按板块跳转</span></div>
        <div class="history-directory-groups">
          ${preparedSectors.map(({ sector, sectorId }) => `
            <div class="history-directory-group">
              <a class="history-directory-sector" href="#${escapeAttribute(sectorId)}">${escapeHtml(sector)}</a>
            </div>`).join("")}
        </div>
      </nav>` : "";
    const history = preparedSectors.map(({ sector, sectorId, sectorRows, groupKey, panelId }) => {
      return `
        <section id="${escapeAttribute(sectorId)}" class="history-sector">
          <header class="history-sector-head">
            <h3>${escapeHtml(sector)}</h3>
            <span>${sectorRows.length} 条原文</span>
          </header>
          <div class="history-sector-body">
            ${renderSectorDailyHistory(sector, sectorRows, groupKey, panelId)}
          </div>
        </section>`;
    }).join("");
    els.tickerHistory.innerHTML = preparedSectors.length
      ? directory + history
      : `<div class="empty-state">当前筛选条件下没有可串联的标的历史原文</div>`;
    bindHistoryScrolling();
    bindRawItemJumpButtons(els.tickerHistory);
  }

  function renderSectorDailyHistory(sector, rows, groupKey, panelId) {
    const days = new Map();
    rows.slice().sort((a, b) => b.createdMs - a.createdMs).forEach((item) => {
      const day = new Date(item.createdMs).toISOString().slice(0, 10);
      if (!days.has(day)) days.set(day, []);
      days.get(day).push(item);
    });
    const scrollId = `history-${groupKey}-days`;
    const cards = Array.from(days.entries()).map(([day, dayRows]) => `
      <li class="timeline-event history-day-card">
        <article class="timeline-event-card">
          <div class="timeline-meta"><time>${escapeHtml(day)}</time><span>${dayRows.length} 条</span></div>
          ${dayRows.map((item) => `<div class="history-day-item"><p class="timeline-source">${escapeHtml(item.authorDisplay)} · ${escapeHtml(sourceShort(item.sourceId, item.sourceType))} ${renderSentiment(item.sentiment)}</p><blockquote>${escapeHtml(compactText(historyCardText(item), 360))}</blockquote><button type="button" class="history-source-link" data-jump-raw="${escapeAttribute(item.id)}">回到每日原文审阅</button></div>`).join("")}
        </article>
      </li>`).join("");
    return `<article id="${escapeAttribute(panelId)}" class="history-panel"><header class="history-ticker-head"><div><span class="ticker-symbol">${escapeHtml(sector)}</span><small>${rows.length} 条原文 · 按天横向排列</small></div><div class="history-scroll-actions"><button type="button" data-history-scroll="-1" aria-controls="${escapeAttribute(scrollId)}" aria-label="向左浏览">←</button><button type="button" data-history-scroll="1" aria-controls="${escapeAttribute(scrollId)}" aria-label="向右浏览">→</button></div></header><div id="${escapeAttribute(scrollId)}" class="timeline-scroll" tabindex="0"><ol>${cards}</ol></div></article>`;
  }

  function renderTickerOriginalHistory(ticker, rows, groupKey, panelId) {
    const related = rows.slice().sort((a, b) => b.createdMs - a.createdMs).slice(0, 12);
    const timeline = related.map((item) => `
      <li class="timeline-event">
        <article class="timeline-event-card">
          <div class="timeline-meta"><time>${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))}</time>${renderSentiment(item.sentiment)}</div>
          <p class="timeline-source">${escapeHtml(item.authorDisplay)} · ${escapeHtml(sourceShort(item.sourceId, item.sourceType))}</p>
          <blockquote>${escapeHtml(compactText(historyCardText(item), 520))}</blockquote>
          <button type="button" class="history-source-link" data-jump-raw="${escapeAttribute(item.id)}">回到每日原文审阅</button>
        </article>
      </li>`).join("");
    const scrollId = `history-${groupKey}-${ticker.replace(/[^A-Za-z0-9_-]/g, "-")}`;
    return `
      <article id="${escapeAttribute(panelId)}" class="history-panel">
        <header class="history-ticker-head">
          <div><span class="ticker-symbol">${escapeHtml(ticker)}</span><small>${rows.length} 条原文 · 最新在前</small></div>
          <div class="history-scroll-actions">
            <button type="button" data-history-scroll="-1" aria-controls="${escapeAttribute(scrollId)}" aria-label="向左浏览">←</button>
            <button type="button" data-history-scroll="1" aria-controls="${escapeAttribute(scrollId)}" aria-label="向右浏览">→</button>
          </div>
        </header>
        <div id="${escapeAttribute(scrollId)}" class="timeline-scroll" tabindex="0"><ol>${timeline}</ol></div>
      </article>`;
  }

  function bindHistoryScrolling() {
    els.tickerHistory.querySelectorAll("[data-history-scroll]").forEach((button) => {
      button.addEventListener("click", () => {
        const scroller = document.getElementById(button.getAttribute("aria-controls"));
        if (scroller) scroller.scrollBy({ left: Number(button.dataset.historyScroll) * Math.max(260, scroller.clientWidth * 0.72), behavior: "smooth" });
      });
    });
    els.tickerHistory.querySelectorAll(".timeline-scroll").forEach((scroller) => {
      let startX = 0;
      let startScroll = 0;
      let dragging = false;
      scroller.addEventListener("pointerdown", (event) => {
        if (event.target.closest("a, button, input, select, textarea, summary")) return;
        dragging = true;
        startX = event.clientX;
        startScroll = scroller.scrollLeft;
        scroller.classList.add("is-dragging");
        scroller.setPointerCapture(event.pointerId);
      });
      scroller.addEventListener("pointermove", (event) => {
        if (dragging) scroller.scrollLeft = startScroll - (event.clientX - startX);
      });
      const stop = () => { dragging = false; scroller.classList.remove("is-dragging"); };
      scroller.addEventListener("pointerup", stop);
      scroller.addEventListener("pointercancel", stop);
    });
  }

  function renderQualityNotes(rows) {
    const sourceTypes = countValues(rows.map((item) => item.sourceType));
    const missingTicker = rows.filter((item) => !item.tickers.length).length;
    const sourceText = topEntries(sourceTypes, 5).map(([type, count]) => `${type || "unknown"} ${count} 条`).join("，") || "暂无来源";
    const collectionNote = state.market === "cn"
      ? "A股抖音“久韭究财”和“潘姨有点神”均按视频发布时间增量采集并转写；订阅预览、无音轨或无可靠口播的作品只保留在每日原文审阅，不进入观点、题材和标的分析；公众号“财躺平”由用户提供文章链接后读取入库。"
      : "美股现有 Discord/X/Substack 采集完整性依赖登录状态、网络和来源权限；X 与 Discord 的静态图片会下载到本地，GIF、APNG 和动态 WebP 会跳过。";
    const notes = [
      `当前窗口共 ${rows.length} 条信息，来源类型分布：${sourceText}。`,
      `未识别出明确标的的信息 ${missingTicker} 条，这类内容会保留为宏观、题材或综合观察。`,
      `“已涨/未涨”仍基于文本语义推断，生产版应接入行情模块，用发布时间价格和盘前价格对比校验。`,
      collectionNote,
      `日报式观点由本地规则从原文抽取，适合作为盘前阅读索引；交易前仍应打开原文和上下文抽屉复核。`,
    ];
    els.qualityList.innerHTML = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
  }

  function renderDailyTrends(rows) {
    const buckets = buildDailyBuckets(rows);
    if (!buckets.length) {
      els.trendCards.innerHTML = `<div class="empty-state">当前时间范围内暂无每日趋势</div>`;
      return;
    }

    els.trendCards.innerHTML = buckets.map((bucket) => {
      const topTickers = topEntries(bucket.tickerCounts, 5);
      const topThemes = topEntries(bucket.themeCounts, 4);
      const topSources = topEntries(bucket.sourceCounts, 3);
      const sentimentEntries = topEntries(bucket.sentimentCounts, 1);
      const dominantSentiment = bucket.items.length ? (sentimentEntries[0]?.[0] || "中性") : "无数据";
      const dominantTheme = bucket.items.length ? (topThemes[0]?.[0] || "综合观察") : "暂无趋势";
      const summary = buildTrendSummary(bucket, dominantTheme, dominantSentiment, topTickers);
      const leadItems = bucket.items.slice().sort(scoreItemForInsight).slice(0, 2);
      const evidence = leadItems.map((item) => item.reason).join("；") || "暂无证据";
      const quote = leadItems.map((item) => item.quote).filter(Boolean).join("；") || "暂无原句";
      const risk = leadItems.map((item) => item.risk).filter(Boolean)[0] || "暂无风险";

      return `
        <article class="trend-card">
          <div class="trend-card-head">
            <div>
              <h3>${escapeHtml(bucket.displayDate)}</h3>
              <p class="trend-meta">${escapeHtml(dominantTheme)} · ${bucket.items.length ? renderSentiment(dominantSentiment) : escapeHtml(dominantSentiment)}</p>
            </div>
            <span class="trend-count">${bucket.items.length} 条</span>
          </div>
          <div class="trend-metrics">
            <div class="trend-metric"><strong>${Object.keys(bucket.sourceCounts).length}</strong><span>来源</span></div>
            <div class="trend-metric"><strong>${Object.keys(bucket.tickerCounts).length}</strong><span>标的</span></div>
            <div class="trend-metric"><strong>${Object.keys(bucket.themeCounts).length}</strong><span>题材</span></div>
          </div>
          <div class="trend-tags">${renderTrendTags(topTickers, "ticker")}${renderTrendTags(topThemes.slice(0, 2), "theme")}</div>
          <p class="trend-summary">${escapeHtml(summary)}</p>
          <dl class="trend-evidence">
            <div><dt>证据</dt><dd>${escapeHtml(evidence)}</dd></div>
            <div><dt>原句</dt><dd class="quote">${escapeHtml(quote)}</dd></div>
            <div><dt>风险</dt><dd>${escapeHtml(risk)}</dd></div>
          </dl>
          <p class="trend-source-line">${escapeHtml(topSources.map(([source, count]) => `${sourceLabel(source)}×${count}`).join(" / ") || "无来源")}</p>
        </article>
      `;
    }).join("");
  }

  function buildDailyBuckets(rows) {
    const grouped = new Map();
    for (const date of dateKeysInWindow()) {
      grouped.set(date, {
        date,
        displayDate: formatTrendDate(date),
        items: [],
        sourceCounts: {},
        tickerCounts: {},
        themeCounts: {},
        sentimentCounts: {}
      });
    }
    for (const item of rows) {
      if (!Number.isFinite(item.createdMs)) continue;
      const parts = toLocalParts(item.createdMs, state.timezone);
      const key = parts.date;
      if (!grouped.has(key) && item.createdMs >= parseLocalDateTime(state.startAt, state.timezone).getTime()) {
        grouped.set(key, {
          date: key,
          displayDate: formatTrendDate(key),
          items: [],
          sourceCounts: {},
          tickerCounts: {},
          themeCounts: {},
          sentimentCounts: {}
        });
      }
      const bucket = grouped.get(key);
      bucket.items.push(item);
      increment(bucket.sourceCounts, item.sourceId);
      increment(bucket.themeCounts, item.theme);
      increment(bucket.sentimentCounts, item.sentiment);
      for (const ticker of item.tickers) increment(bucket.tickerCounts, ticker);
    }
    return Array.from(grouped.values()).sort((a, b) => b.date.localeCompare(a.date));
  }

  function dateKeysInWindow() {
    const startDate = (state.startAt || "").split("T")[0];
    const endDate = (state.endAt || "").split("T")[0];
    if (!startDate || !endDate) return [];
    const keys = [];
    let cursor = parseLocalDateTime(`${startDate}T00:00`, state.timezone).getTime();
    const end = parseLocalDateTime(`${endDate}T00:00`, state.timezone).getTime();
    const maxDays = 45;
    while (cursor <= end && keys.length < maxDays) {
      keys.push(toLocalParts(cursor, state.timezone).date);
      cursor += 24 * 60 * 60 * 1000;
    }
    return keys;
  }

  function renderTrendTags(entries, type) {
    if (!entries.length) return "";
    return entries.map(([value, count]) => {
      const label = type === "ticker" ? value : value;
      return `<span class="tag">${escapeHtml(label)}×${count}</span>`;
    }).join("");
  }

  function buildTrendSummary(bucket, dominantTheme, dominantSentiment, topTickers) {
    if (!bucket.items.length) return "这一天没有命中当前筛选条件的数据";
    const tickerText = topTickers.length ? topTickers.map(([ticker, count]) => `${ticker}×${count}`).join("、") : "暂无明确标的";
    return `${dominantTheme} 是主线，整体观点偏 ${dominantSentiment}；高频标的：${tickerText}`;
  }

  function buildFundamentalRows(rows) {
    const themeGroups = Array.from(groupBy(rows, (item) => item.theme).entries())
      .sort((a, b) => b[1].length - a[1].length)
      .slice(0, 5);
    return themeGroups.map(([theme, themeRows]) => {
      const leadRows = themeRows.slice().sort(scoreItemForInsight).slice(0, 3);
      const sentiment = dominantValue(themeRows.map((item) => item.sentiment)) || "中性";
      const relatedItems = themeRows.slice().sort(scoreItemForInsight).slice(0, 8);
      return {
        direction: theme,
        sentiment,
        evidence: buildEvidenceText(leadRows, theme),
        quote: leadRows.map((item) => item.quote).filter(Boolean).slice(0, 2).join("；") || "暂无相关原句",
        risk: buildGroupRisk(themeRows, theme),
        tickers: uniqueSorted(themeRows.flatMap((item) => item.tickers)).slice(0, 12),
        sources: uniqueSorted(themeRows.map((item) => item.sourceId)).slice(0, 8),
        sourceTypes: uniqueSorted(themeRows.map((item) => item.sourceType).filter(Boolean)).slice(0, 6),
        itemIds: relatedItems.map((item) => item.id),
        items: relatedItems,
      };
    });
  }

  function buildSourceInsightRows(rows) {
    const tickerGroups = new Map();
    for (const item of rows) {
      const keys = item.tickers.length ? item.tickers : ["大盘 / 综合"];
      for (const ticker of keys) {
        if (!tickerGroups.has(ticker)) tickerGroups.set(ticker, []);
        tickerGroups.get(ticker).push(item);
      }
    }
    return Array.from(tickerGroups.entries())
      .sort((a, b) => b[1].length - a[1].length)
      .slice(0, 12)
      .map(([ticker, tickerRows]) => {
      const orderedRows = tickerRows.slice().sort((a, b) => b.createdMs - a.createdMs);
      const theme = ticker === "大盘 / 综合" ? (dominantValue(tickerRows.map((item) => item.theme)) || "综合观察") : sectorForTicker(ticker);
      const sentiment = ticker === "大盘 / 综合"
        ? dominantSentiment(tickerRows)
        : dominantValue(tickerRows.map((item) => inferTickerSentiment(item, ticker))) || "中性";
      return {
        theme,
        ticker,
        tickers: ticker === "大盘 / 综合" ? [] : [ticker],
        sentiment,
        reason: buildSourceTickerReason(ticker, orderedRows, theme),
        sourceId: tickerRows[0]?.sourceId || "",
        sourceName: tickerRows[0]?.sourceName || sourceLabel(tickerRows[0]?.sourceId || ""),
        sourceType: tickerRows[0]?.sourceType || "",
        itemIds: orderedRows.map((item) => item.id),
        items: orderedRows,
      };
    });
  }

  function buildCnSourceSectorRows(rows) {
    const sectorGroups = new Map();
    for (const item of rows) {
      const sectors = cnSectorsForItem(item);
      for (const sector of sectors) {
        if (!sectorGroups.has(sector)) sectorGroups.set(sector, new Map());
        sectorGroups.get(sector).set(item.id, item);
      }
    }
    return Array.from(sectorGroups.entries())
      .map(([sector, itemMap]) => [sector, Array.from(itemMap.values())])
      .sort((a, b) => b[1].length - a[1].length)
      .slice(0, 12)
      .map(([sector, sectorRows]) => {
        const orderedRows = sectorRows.slice().sort((a, b) => b.createdMs - a.createdMs);
        return {
          theme: sector,
          ticker: "",
          tickers: [],
          sentiment: dominantSentiment(orderedRows),
          reason: buildCnSectorReason(sector, orderedRows),
          sourceId: orderedRows[0]?.sourceId || "",
          sourceName: orderedRows[0]?.sourceName || sourceLabel(orderedRows[0]?.sourceId || ""),
          sourceType: orderedRows[0]?.sourceType || "",
          itemIds: orderedRows.map((item) => item.id),
          items: orderedRows,
          cardMode: "sector",
        };
      });
  }

  function cnSectorsForItem(item) {
    const text = `${item.translatedTitle || item.title || ""}\n${item.translatedText || item.text || ""}`;
    const matched = cnSectorDefinitions
      .filter(([, pattern]) => pattern.test(text))
      .map(([sector]) => sector);
    if (matched.length) return matched;
    if (item.theme && item.theme !== "综合观察") return [item.theme];
    return ["综合观察"];
  }

  function buildCnSectorReason(sector, rows) {
    const definition = cnSectorDefinitions.find(([name]) => name === sector);
    const pattern = definition?.[1];
    const excerpts = rows
      .map((item) => cnSectorContext(item, pattern))
      .filter(Boolean);
    const evidence = uniqueSorted(excerpts).slice(0, 3).map((value) => compactText(value, 180)).join("；");
    return evidence
      ? `所选区间内有 ${rows.length} 条原文涉及该板块。核心判断：${evidence}`
      : `所选区间内有 ${rows.length} 条原文涉及该板块，请结合下方原文审阅。`;
  }

  function cnSectorContext(item, pattern) {
    const source = String(item.translatedText || item.text || item.translatedTitle || item.title || "").trim();
    if (!source) return "";
    const segments = source.split(/[。！？；\n]+/).map((value) => value.trim()).filter(Boolean);
    return (pattern && segments.find((segment) => pattern.test(segment))) || segments[0] || "";
  }

  function renderInsightRow(row) {
    return `
      <tr>
        <td>${escapeHtml(row.theme)}</td>
        <td>${escapeHtml(row.tickers.join(", ") || "大盘/综合")}</td>
        <td>${renderSentiment(row.sentiment)}</td>
        <td>${escapeHtml(row.specific)}</td>
        <td>${escapeHtml(row.reason)}</td>
        <td>${escapeHtml(row.risk)}</td>
        <td class="quote">${escapeHtml(row.quote)}</td>
        <td><button class="row-btn analysis-copy-btn" data-copy-analysis="${escapeAttribute(registerAnalysisPrompt(buildAnalysisPrompt("source", row)))}">分析</button></td>
      </tr>
    `;
  }

  function renderInsightCard(row) {
    const promptId = registerAnalysisPrompt(buildAnalysisPrompt("source", row));
    const isSectorCard = row.cardMode === "sector";
    return `
      <article class="insight-card" data-sector-tone="${escapeAttribute(sectorTone(row.theme))}">
        <header>
          <div><span class="insight-theme">${escapeHtml(isSectorCard ? "板块观点" : row.theme)}</span><h4>${escapeHtml(isSectorCard ? row.theme : (row.ticker || "大盘 / 综合"))}</h4></div>
          ${renderSentiment(row.sentiment)}
        </header>
        <section class="insight-reason">
          <span>核心理由</span>
          <p>${escapeHtml(row.reason)}</p>
        </section>
        <section class="insight-originals" aria-label="所选时间区间内的相关原文">
          <div class="insight-originals-head"><span>${isSectorCard ? "区间摘要" : "区间原文"}</span><small>${row.items.length} 条 · 最新在前</small></div>
          ${row.items.map((item) => renderInsightOriginal(item, row)).join("")}
        </section>
        <button class="row-btn analysis-copy-btn" data-copy-analysis="${escapeAttribute(promptId)}">复制分析上下文</button>
      </article>`;
  }

  function renderInsightOriginal(item, row) {
    if (row?.cardMode === "sector") return renderCnInsightSummary(item, row.theme);
    const original = String(item.text || item.title || "").trim();
    const tooLong = original.length > 260;
    const preview = tooLong ? `${original.slice(0, 260)}…` : original;
    return `
      <article class="insight-original-item">
        <div><time>${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))}</time><span>${escapeHtml(item.authorDisplay)}</span></div>
        <p>${escapeHtml(preview || "无文字原文")}</p>
        ${tooLong ? `<button type="button" class="insight-raw-jump" data-jump-raw="${escapeAttribute(item.id)}">到每日原文审阅阅读全文</button>` : ""}
      </article>`;
  }

  function renderCnInsightSummary(item, sector) {
    const title = String(item.translatedTitle || item.title || "").trim();
    const summary = buildCnInsightItemSummary(item, sector);
    return `
      <article class="insight-original-item insight-summary-item">
        <div><time>${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))}</time><span>${escapeHtml(item.authorDisplay)}</span></div>
        ${title ? `<h5>${escapeHtml(title)}</h5>` : ""}
        <p>${escapeHtml(summary || "当前原文暂无可提炼摘要")}</p>
        <button type="button" class="insight-raw-jump" data-jump-raw="${escapeAttribute(item.id)}">到每日原文审阅查看原文</button>
      </article>`;
  }

  function buildCnInsightItemSummary(item, sector) {
    if (item.summaryText) return compactText(item.summaryText, 220);
    const source = String(item.translatedText || item.text || item.translatedTitle || item.title || "").trim();
    if (!source) return "";
    const pattern = cnSectorDefinitions.find(([name]) => name === sector)?.[1];
    const segments = source
      .split(/[。！？；\n]+/)
      .map((value) => value.replace(/\s+/g, " ").trim())
      .filter((value) => value.length >= 8);
    const matched = pattern ? segments.filter((segment) => pattern.test(segment)) : [];
    const selected = (matched.length ? matched : segments).slice(0, 2);
    return compactText(selected.join("；"), 220);
  }

  function buildSourceTickerReason(ticker, rows, theme) {
    if (!rows.length) return "当前筛选条件下没有足够证据。";
    if (ticker === "大盘 / 综合") return buildEvidenceText(rows.slice(0, 2), theme);
    const contexts = uniqueSorted(rows.map((item) => tickerContext(item, ticker)).filter(Boolean)).slice(0, 3);
    const evidence = contexts.map((value) => compactText(value, 180)).join("；");
    return evidence
      ? `所选区间内 ${rows.length} 条原文直接提到 ${ticker}。重点：${evidence}`
      : `所选区间内 ${rows.length} 条原文直接提到 ${ticker}，请结合下方完整原文审阅。`;
  }

  function tickerContext(item, ticker) {
    const source = String(item.translatedText || item.text || item.translatedTitle || item.title || "").replace(/\s+/g, " ").trim();
    if (!source) return "";
    const segments = source.split(/(?=\s*\d+\.\s*)|[。！？；\n]+/).map((value) => value.trim()).filter(Boolean);
    const pattern = new RegExp(`(^|[^A-Za-z0-9])\\$?${escapeRegex(ticker)}([^A-Za-z0-9]|$)`, "i");
    return segments.find((segment) => pattern.test(segment)) || "";
  }

  function inferTickerSentiment(item, ticker) {
    const context = tickerContext(item, ticker);
    if (/❌|财报前\s*(\d+(?:\.\d+)?)[^。；\n]{0,30}财报后\s*(\d+(?:\.\d+)?)/i.test(context)) {
      const prices = context.match(/财报前\s*(\d+(?:\.\d+)?)[^。；\n]{0,30}财报后\s*(\d+(?:\.\d+)?)/i);
      if (/❌/.test(context) || (prices && Number(prices[2]) < Number(prices[1]))) return "看跌";
    }
    if (/✅/.test(context)) return "看涨";
    return inferSentiment(context || item.translatedText || item.text || item.title || "");
  }

  function historyCardText(item) {
    return item.translatedText || item.translatedTitle || item.text || item.title || "";
  }

  function rawItemAnchor(itemId) {
    return `raw-item-${String(itemId || "").replace(/[^A-Za-z0-9_-]/g, "-")}`;
  }

  function bindRawItemJumpButtons(root = els.sourceInsightTables) {
    root.querySelectorAll("[data-jump-raw]").forEach((button) => {
      button.addEventListener("click", () => jumpToRawItem(button.dataset.jumpRaw));
    });
  }

  function jumpToRawItem(itemId) {
    if (state.view !== "feed") switchView("feed");
    const target = document.getElementById(rawItemAnchor(itemId));
    if (!target) return;
    const day = target.closest("details.raw-day");
    if (day) day.open = true;
    target.classList.remove("raw-item-highlight");
    void target.offsetWidth;
    target.classList.add("raw-item-highlight");
    if (typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    window.setTimeout(() => target.classList.remove("raw-item-highlight"), 2200);
  }

  function sectorTone(theme) {
    const value = String(theme || "");
    if (/ai 应用|传媒|短剧|影视/i.test(value)) return "violet";
    if (/银行|红利/i.test(value)) return "amber";
    if (/煤炭/i.test(value)) return "green";
    if (/pcb|电子材料|覆铜板/i.test(value)) return "terracotta";
    if (/有色|黄金|资源/i.test(value)) return "terracotta";
    if (/消费电子/i.test(value)) return "indigo";
    if (/地产|基建/i.test(value)) return "rose";
    if (/光通信|cpo|photonics|laser/i.test(value)) return "sky";
    if (/存储|memory/i.test(value)) return "violet";
    if (/neocloud|算力能源|能源/i.test(value)) return "green";
    if (/ai 芯片|ai 半导体|芯片|半导体|先进封装/i.test(value)) return "amber";
    if (/云计算|软件|saas/i.test(value)) return "indigo";
    if (/特殊事件|ai 平台/i.test(value)) return "rose";
    if (/稀土|材料/i.test(value)) return "terracotta";
    if (/大盘|etf|宏观|流动性/i.test(value)) return "slate";
    if (/交易动作/i.test(value)) return "teal";
    return "neutral";
  }

  function buildEvidenceText(rows, theme) {
    if (!rows.length) return "当前筛选条件下没有足够证据。";
    return rows.map((item) => item.reason || `${sourceShort(item.sourceId, item.sourceType)} 提到 ${theme}`).join("；");
  }

  function buildSpecificTickers(rows, tickers) {
    if (!tickers.length) return rows[0]?.theme === "宏观流动性" ? "SPY、QQQ（AI补充标的）" : "相关 ETF（AI补充标的）";
    const priceByTicker = new Map();
    for (const item of rows) {
      for (const ticker of item.tickers) {
        if (!priceByTicker.has(ticker)) priceByTicker.set(ticker, item.priceStatus);
      }
    }
    return tickers.map((ticker) => `${ticker}（${priceByTicker.get(ticker) || "待验证"}）`).join("、");
  }

  function buildGroupRisk(rows, theme) {
    const risks = rows.map((item) => item.risk).filter(Boolean);
    const highRun = rows.some((item) => item.priceStatus === "已涨");
    const sellSignal = rows.some((item) => item.sentiment === "看跌");
    if (sellSignal) return risks.find((risk) => risk.includes("止盈") || risk.includes("卖出") || risk.includes("偏弱")) || "出现看跌或锁利信号，需要区分短线止盈和中期主题。";
    if (highRun) return "部分标的已经大涨，短线追高风险上升，需要等待回撤或新催化。";
    if (theme.includes("宏观")) return "宏观判断需要后续政策和市场利率验证，短线可能先按点阵图或估值回撤。";
    return risks[0] || "信息仍需行情、成交量和后续消息验证。";
  }

  function buildMarketBiasText(rows, topTheme, sentiment, topTickers) {
    if (!rows.length) return "当前筛选条件下暂无可分析信息。";
    const tickerText = topTickers.length ? topTickers.map(([ticker]) => ticker).slice(0, 6).join("、") : "暂无明确标的";
    return `当前窗口主线是 ${topTheme}，整体观点偏 ${sentiment}；高频标的包括 ${tickerText}。`;
  }

  function renderRiskBadge(rows) {
    const hasRunUp = rows.some((item) => item.priceStatus === "已涨");
    const hasSell = rows.some((item) => item.sentiment === "看跌");
    if (hasSell) return `<span class="view-tag bearish">锁利/偏弱</span>`;
    if (hasRunUp) return `<span class="view-tag neutral">追高</span>`;
    return `<span class="view-tag watch">待验证</span>`;
  }

  function buildRiskSummary(rows, topTickers) {
    if (!rows.length) return "暂无风险判断。";
    const runUp = rows.filter((item) => item.priceStatus === "已涨").flatMap((item) => item.tickers);
    const runUpText = uniqueSorted(runUp).slice(0, 5).join("、");
    if (runUpText) return `${runUpText} 等标的文本语义显示已涨或需要锁利，追高前需要结合行情。`;
    const tickerText = topTickers.map(([ticker]) => ticker).slice(0, 5).join("、");
    return `${tickerText || "核心标的"} 仍需用实时行情、成交量和后续消息确认。`;
  }

  function buildTickerConclusion(ticker, rows) {
    const sentiment = dominantValue(rows.map((item) => item.sentiment)) || "中性";
    const theme = dominantTheme(rows);
    const sources = uniqueSorted(rows.map((item) => sourceShort(item.sourceId, item.sourceType))).slice(0, 3).join("、");
    const hasRunUp = rows.some((item) => item.priceStatus === "已涨");
    const risk = hasRunUp ? "但文本显示已有上涨或锁利语义，短线不宜无脑追高" : "仍需用行情和后续消息确认";
    return `${ticker} 当前归入 ${theme}，综合观点偏 ${sentiment}，主要来自 ${sources || "当前来源"}；${risk}。`;
  }

  function inferReason(text, theme, tickers, sentiment, sourceName) {
    const clean = compactText(text, 520);
    const lower = clean.toLowerCase();
    const tickerText = tickers.length ? tickers.slice(0, 5).join("、") : "相关标的";
    if (theme === "宏观流动性") return "文本集中提到 Fed/FOMC、Warsh、dovish/rate cut 等流动性线索，影响大盘风险偏好。";
    if (theme === "Memory") return `${tickerText} 关联存储周期、DRAM/NAND 或供需叙事，属于 Memory 主线证据。`;
    if (theme === "Photonics/CW Laser") return `${tickerText} 关联 photonics、CW laser、CPO 或光通信供应约束，指向 AI 硬件瓶颈。`;
    if (theme === "Neoclouds/Energy") return `${tickerText} 关联 neocloud、energy 或算力能源方向，属于 AI 基建链证据。`;
    if (theme === "软件/SaaS") return `${tickerText} 关联软件/SaaS basket，文本语气可用于判断软件链强弱。`;
    if (theme === "先进封装/玻璃基板") return `${tickerText} 涉及 glass substrate、NASDAQ listing、TAM 或量产 ramp，属于先进封装线索。`;
    if (theme === "交易动作") return "来源包含直接买入、加仓、卖出或成本价信息，属于高信号交易动作。";
    if (lower.includes("buy") || lower.includes("bought") || lower.includes("added") || lower.includes("买")) return `${tickerText} 出现买入/加仓表述，观点偏 ${sentiment}。`;
    if (lower.includes("sell") || lower.includes("sold") || lower.includes("出") || lower.includes("锁利")) return `${tickerText} 出现卖出/锁利表述，短线风险权重更高。`;
    return `${sourceName || "当前来源"} 提到 ${tickerText}，文本主题归入 ${theme}。`;
  }

  function inferRisk(text, theme, tickers, sentiment, priceStatus) {
    const lower = String(text || "").toLowerCase();
    if (sentiment === "看跌") return "文本出现卖出、锁利或偏弱信号，需要防止把短线止盈误读成中期趋势。";
    if (priceStatus === "已涨") return "文本语义显示已经上涨或接近目标，短线追高风险较高。";
    if (theme === "宏观流动性") return "宏观判断仍需政策落地和利率走势确认，市场可能先反向交易。";
    if (theme === "先进封装/玻璃基板") return "小票或海外标的信息真实性、流动性和上市节奏需要二次验证。";
    if (lower.includes("rumor") || lower.includes("report") || lower.includes("meeting notes")) return "线索来自报告、传闻或纪要，需要后续公告和订单验证。";
    if (!tickers.length) return "缺少明确标的，需要结合板块 ETF 或后续信息定位。";
    return "仍需结合实时价格、成交量和后续消息验证。";
  }

  function extractQuote(text) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    if (!clean) return "";
    const quoted = clean.match(/[“\"]([^”\"]{12,220})[”\"]/);
    if (quoted) return `“${quoted[1]}”`;
    const sentences = clean.split(/(?<=[.!?。！？])\s+/).filter(Boolean);
    const best = sentences.find((sentence) => sentence.length >= 24) || clean;
    return `“${compactText(best, 260)}”`;
  }

  function scrollTrendCards(direction) {
    const card = els.trendCards.querySelector(".trend-card");
    const amount = card ? card.getBoundingClientRect().width + 12 : 320;
    els.trendCards.scrollBy({ left: direction * amount, behavior: "smooth" });
  }

  function renderTable(rows) {
    if (!rows.length) {
      els.itemsBody.innerHTML = `<tr><td colspan="8" class="empty-state">当前筛选条件下没有数据</td></tr>`;
      return;
    }

    els.itemsBody.innerHTML = rows.map((item) => `
      <tr>
        <td>${escapeHtml(item.theme)}</td>
        <td><div class="tag-row">${renderTickerTags(item.tickers)}</div></td>
        <td>${renderSentiment(item.sentiment)}</td>
        <td>${escapeHtml(formatSpecificTickers(item))}<br><span class="row-meta">${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))} · ${escapeHtml(sourceShort(item.sourceId, item.sourceType))} · ${escapeHtml(item.authorDisplay)}</span></td>
        <td>${escapeHtml(item.reason)}</td>
        <td>${escapeHtml(item.risk)}</td>
        <td><div class="quote text-preview">${escapeHtml(item.quote || compactText(item.text || item.title, 420))}</div></td>
        <td><button class="row-btn" data-analyze="${escapeHtml(item.id)}">分析</button></td>
      </tr>
    `).join("");

    els.itemsBody.querySelectorAll("[data-analyze]").forEach((button) => {
      button.addEventListener("click", () => openDrawer(button.dataset.analyze));
    });
  }

  function renderTickerSummary(rows) {
    const tickerCounts = countValues(rows.flatMap((item) => item.tickers));
    const cards = Object.entries(tickerCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
      .map(([ticker, count]) => {
        const related = rows.filter((item) => item.tickers.includes(ticker));
        const sentiments = countValues(related.map((item) => item.sentiment));
        const dominant = Object.entries(sentiments).sort((a, b) => b[1] - a[1])[0]?.[0] || "中性";
        const theme = dominantTheme(related);
        const lead = related.slice().sort(scoreItemForInsight)[0];
        return `
          <article class="ticker-card">
            <h3>${escapeHtml(ticker)}</h3>
            <p>${renderSentiment(dominant)} <span>${count} 条 · ${escapeHtml(theme)}</span></p>
            <p><strong>证据：</strong>${escapeHtml(compactText(lead?.reason || "", 120))}</p>
            <p><strong>风险：</strong>${escapeHtml(compactText(buildGroupRisk(related, theme), 120))}</p>
          </article>
        `;
      }).join("");
    els.tickerSummary.innerHTML = cards || `<div class="empty-state">暂无标的聚合</div>`;
  }

  async function openDrawer(itemId) {
    const item = items.find((candidate) => candidate.id === itemId);
    if (!item) return;
    state.selectedId = itemId;
    els.drawerTitle.textContent = `原文详情 · ${item.sentiment}`;
    els.openOriginal.href = item.externalUrl || "#";
    els.openOriginal.style.display = item.externalUrl ? "inline-flex" : "none";
    els.copyNotice.textContent = "";
    els.copyNotice.classList.remove("visible");

    const detail = await fetchItemDetail(itemId);
    if (detail) {
      applyDetailToItem(item, detail);
    }
    els.drawerContent.innerHTML = renderDrawerContent(item);
    els.drawer.classList.add("open");
    els.drawer.setAttribute("aria-hidden", "false");
  }

  async function fetchItemDetail(itemId) {
    if (!apiAvailable || !window.fetch) return null;
    if (apiDetailCache.has(itemId)) return apiDetailCache.get(itemId);
    try {
      const response = await fetch(`${API_BASE}/items/${encodeURIComponent(itemId)}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`API ${response.status}`);
      const payload = await response.json();
      apiDetailCache.set(itemId, payload);
      return payload;
    } catch (_error) {
      return null;
    }
  }

  function applyDetailToItem(item, detail) {
    if (!detail?.item) return;
    item.raw = detail.item;
    item.text = detail.item.content?.text || item.text;
    item.title = detail.item.content?.title || item.title;
    item.externalId = detail.item.external?.id || item.externalId;
    item.externalUrl = detail.item.external?.url || item.externalUrl;
    item.isReply = Boolean(detail.item.relations?.is_reply || detail.item.raw_payload?.reply_context);
    item.replyContext = normalizeReplyContext(detail.item.raw_payload?.reply_context) || item.replyContext;
    const translation = detail.item.raw_payload?.translation || null;
    item.translatedText = typeof translation === "string" ? translation : String(translation?.text || item.translatedText || "");
    item.translatedTitle = typeof translation === "object" ? String(translation?.title || item.translatedTitle || "") : item.translatedTitle;
  }

  function closeDrawer() {
    els.drawer.classList.remove("open");
    els.drawer.setAttribute("aria-hidden", "true");
  }

  function renderDrawerContent(item) {
    return `
      <section class="detail-block">
        <h3>当前信息</h3>
        <p><strong>数据库 ID：</strong>${escapeHtml(item.id)}</p>
        <p><strong>发布时间：</strong>${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))}</p>
        <p><strong>来源：</strong>${escapeHtml(item.sourceName)} · ${escapeHtml(item.authorDisplay)}</p>
        <p><strong>题材/观点：</strong>${escapeHtml(item.theme)} · ${renderSentiment(item.sentiment)}</p>
        <h4>原文</h4>
        <div class="quote-block">${escapeHtml(item.text || item.title || "")}</div>
        ${renderReplyContext(item.replyContext)}
        ${item.translatedText ? `<h4>中文翻译</h4><div class="quote-block translation-block">${escapeHtml(item.translatedText)}</div>` : ""}
      </section>
      <section class="detail-block">
        <h3>数据库关联字段</h3>
        <p><strong>external_id：</strong>${escapeHtml(item.externalId || "-")}</p>
        <p><strong>external_url：</strong>${item.externalUrl ? `<a href="${escapeAttribute(item.externalUrl)}" target="_blank" rel="noreferrer">${escapeHtml(item.externalUrl)}</a>` : "-"}</p>
        <p><strong>source_id：</strong>${escapeHtml(item.sourceId)}</p>
        <p><strong>content_hash：</strong>${escapeHtml(item.raw.content?.hash || "-")}</p>
      </section>
    `;
  }

  function buildCodexMarkdown(item) {
    return `# 数据进阶分析请求

请基于以下本地数据库上下文，分析这条信息对盘前交易的意义。

## 当前信息
- item_id: ${item.id}
- 发布时间: ${item.createdAt}
- 来源: ${item.sourceName}
- 作者: ${item.authorDisplay} (${item.author})
- 链接: ${item.externalUrl || "-"}
- 题材: ${item.theme}
- 初步观点: ${item.sentiment}

### 原文
> ${compactText(item.text || item.title, 1200).replace(/\n/g, "\n> ")}
${item.translatedText ? `\n### 中文翻译\n> ${compactText(item.translatedText, 1200).replace(/\n/g, "\n> ")}` : ""}
${item.replyContext ? `\n## 被回复消息（仅作上下文，不视为当前作者观点）
- 作者: ${item.replyContext.author}
- 发布时间: ${item.replyContext.timestamp || "未知"}
- 链接: ${item.replyContext.url || "-"}

> ${compactText(item.replyContext.available ? (item.replyContext.content || "原回复无文字内容") : "原回复不可用", 1200).replace(/\n/g, "\n> ")}` : ""}

## 数据库关联字段
- source_type: ${item.sourceType}
- source_id: ${item.sourceId}
- external_id: ${item.externalId || "-"}
- content_hash: ${item.raw.content?.hash || "-"}

## 希望你输出
1. 这条信息是否构成交易信号
2. 看涨/看跌/中性/观望
3. 证据链
4. 风险和反证
5. 如果纳入盘前日报，应该放在哪个题材和标的下
`;
  }

  async function copyCurrentContext(format) {
    const item = items.find((candidate) => candidate.id === state.selectedId);
    if (!item) return;
    let text = "";
    if (format === "json") {
      const detail = await fetchItemDetail(item.id);
      if (detail) applyDetailToItem(item, detail);
      text = JSON.stringify(item.raw, null, 2);
    } else {
      text = await fetchCodexContext(item.id) || buildCodexMarkdown(item);
    }
    const copied = await copyText(text);
    els.copyNotice.textContent = copied
      ? (format === "json" ? "已复制原始 JSON" : "已复制进阶分析上下文，可直接粘贴给 Codex")
      : "浏览器限制了复制，请改用本地服务打开页面后重试";
    els.copyNotice.classList.add("visible");
  }

  async function fetchCodexContext(itemId) {
    if (!apiAvailable || !window.fetch) return null;
    if (apiContextCache.has(itemId)) return apiContextCache.get(itemId);
    try {
      const response = await fetch(`${API_BASE}/context/item/${encodeURIComponent(itemId)}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`API ${response.status}`);
      const payload = await response.json();
      const text = payload.copy_text || null;
      apiContextCache.set(itemId, text);
      return text;
    } catch (_error) {
      return null;
    }
  }

  async function copyText(text) {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_error) {
        // file:// and some local browser contexts can reject clipboard access.
      }
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    textarea.setAttribute("readonly", "");
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (_error) {
      copied = false;
    }
    textarea.remove();
    return copied;
  }

  function registerAnalysisPrompt(text) {
    const id = `analysis_${analysisPromptSeq += 1}`;
    analysisPromptCache.set(id, text);
    return id;
  }

  function bindAnalysisPromptButtons(root) {
    root.querySelectorAll("[data-copy-analysis]").forEach((button) => {
      button.addEventListener("click", async () => {
        const prompt = analysisPromptCache.get(button.dataset.copyAnalysis);
        if (!prompt) {
          showGlobalCopyNotice("未找到这条分析上下文，请刷新后重试");
          return;
        }
        const copied = await copyText(prompt);
        showGlobalCopyNotice(copied ? "已复制分析提示词，可粘贴给另一个 Codex 对话" : "浏览器限制了复制，请改用本地服务打开页面后重试");
      });
    });
  }

  function showGlobalCopyNotice(message) {
    if (!els.globalCopyNotice) return;
    window.clearTimeout(globalNoticeTimer);
    els.globalCopyNotice.textContent = message;
    els.globalCopyNotice.classList.add("visible");
    globalNoticeTimer = window.setTimeout(() => {
      els.globalCopyNotice.classList.remove("visible");
    }, 2600);
  }

  function buildAnalysisPrompt(kind, row) {
    const isSource = kind === "source";
    const title = isSource ? "信息源观点" : "基本面分析";
    const theme = isSource ? row.theme : row.direction;
    const tickers = isSource ? row.tickers : row.tickers || [];
    const evidence = isSource ? row.reason : row.evidence;
    const sourceIds = isSource ? [row.sourceId].filter(Boolean) : row.sources || [];
    const sourceTypes = isSource ? [row.sourceType].filter(Boolean) : row.sourceTypes || [];
    const sourceNames = isSource
      ? [row.sourceName || sourceLabel(row.sourceId)].filter(Boolean)
      : sourceIds.map(sourceLabel);
    const relatedItems = row.items || [];

    return `# 数据进阶分析请求

请基于以下本地 quant-trading-intel 数据库上下文，继续分析这组${title}信息对盘前交易的意义。请优先使用 item_id、source_id、source_type、标的和原文内容进行判断。

## 分析对象
- 模块: ${title}
- 题材/方向: ${theme}
- 初步观点: ${row.sentiment}
- 具体标的: ${(tickers || []).join(", ") || "大盘/综合"}
- 信息源: ${sourceNames.join(" / ") || "多个来源"}
- 数据库 item_id: ${(row.itemIds || []).join(", ") || "-"}
- source_id: ${sourceIds.join(", ") || "-"}
- source_type: ${sourceTypes.join(", ") || "-"}

## 当前页面结论
${isSource
  ? `- 核心理由: ${evidence}`
  : `- 证据/理由: ${evidence}\n- 风险/反证: ${row.risk}\n- 相关原句: ${row.quote}`}

## 关联原始信息
${formatPromptItems(relatedItems)}

## 希望你输出
1. 这组信息是否构成交易信号
2. 看涨/看跌/中性/观望，以及理由
3. 证据链：哪些 item_id 支撑结论，哪些只是噪音
4. 风险和反证：需要查哪些价格、财报、公告或后续信息
5. 如果纳入盘前日报，应该放在哪个题材和标的下
`;
  }

  function formatPromptItems(rows) {
    if (!rows.length) return "- 暂无关联原始信息";
    return rows.map((item, index) => `${index + 1}. item_id: ${item.id}
   - 发布时间: ${item.createdAt || "-"}
   - 来源: ${item.sourceName} (${item.sourceType || "-"} / ${item.sourceId || "-"})
   - 作者: ${item.authorDisplay} (${item.author})
   - 标的: ${item.tickers.join(", ") || "大盘/综合"}
   - 题材/观点: ${item.theme} / ${item.sentiment}
   - external_id: ${item.externalId || "-"}
   - url: ${item.externalUrl || "-"}
   - 页面理由: ${item.reason}
   - 风险: ${item.risk}
   - 原文摘录: ${compactText(item.text || item.title, 900)}${item.translatedText ? `\n   - 中文翻译: ${compactText(item.translatedText, 900)}` : ""}`).join("\n\n");
  }

  function renderTickerTags(tickers) {
    if (!tickers.length) return `<span class="tag">无明确标的</span>`;
    return tickers.slice(0, 5).map((ticker) => `<span class="tag">${escapeHtml(ticker)}</span>`).join("");
  }

  function renderSentiment(sentiment) {
    const cls = sentiment === "看涨" ? "bullish" : sentiment === "看跌" ? "bearish" : sentiment === "观望" ? "watch" : "neutral";
    return `<span class="view-tag ${cls}">${escapeHtml(sentiment)}</span>`;
  }

  function formatSpecificTickers(item) {
    if (!item.tickers.length) {
      const fallback = item.theme === "宏观流动性" ? "QQQ（AI补充标的）" : "相关 ETF（AI补充标的）";
      return fallback;
    }
    return item.tickers.map((ticker) => `${ticker}（${item.priceStatus}）`).join("、");
  }

  function uniqueOptions(values, labeler) {
    return Array.from(new Set(values.filter(Boolean)))
      .sort((a, b) => String(labeler(a)).localeCompare(String(labeler(b)), "zh-Hans-CN"))
      .map((value) => [value, labeler(value)]);
  }

  function fillSelect(select, options) {
    select.innerHTML = options.map(([value, label]) => `<option value="${escapeAttribute(value)}">${escapeHtml(label)}</option>`).join("");
  }

  function sourceLabel(sourceId) {
    const found = items.find((item) => item.sourceId === sourceId);
    return found ? found.sourceName : sourceId;
  }

  function sourceDisplayName(sourceId, sourceType) {
    const name = sourceLabel(sourceId);
    const channel = channelLabel(sourceType);
    return name.replace(new RegExp(`^${channel}\\s+`, "i"), "").trim() || name;
  }

  function sourceChannelLabel(sourceId) {
    const found = items.find((item) => item.sourceId === sourceId);
    return found ? `${channelLabel(found.sourceType)} ${sourceDisplayName(sourceId, found.sourceType)}` : sourceLabel(sourceId);
  }

  function sourceShort(sourceId, sourceType) {
    if (sourceId.includes("jiujiujiucai")) return "抖音 久韭究财";
    if (sourceId.includes("panyiyoudianshen")) return "抖音 潘姨有点神";
    if (sourceId.includes("caitangping")) return "公众号 财躺平";
    if (sourceId.includes("haochi")) return sourceType === "discord" ? "Discord 好吃" : "X 好吃";
    if (sourceId.includes("aleabitoreddit")) return "X Serenity";
    if (sourceId.includes("edgerunner") || sourceId.includes("tianyi")) return sourceType === "substack" ? "Substack Edgerunner" : "Edgerunner";
    return sourceLabel(sourceId);
  }

  function dominantTheme(rows) {
    const themes = countValues(rows.map((item) => item.theme));
    return Object.entries(themes).sort((a, b) => b[1] - a[1])[0]?.[0] || "综合观察";
  }

  function dominantValue(values) {
    return topEntries(countValues(values), 1)[0]?.[0] || "";
  }

  function dominantSentiment(rows) {
    const directional = rows
      .filter((item) => item.sentiment === "看涨" || item.sentiment === "看跌")
      .sort((a, b) => b.createdMs - a.createdMs);
    if (directional.length) {
      const counts = countValues(directional.map((item) => item.sentiment));
      if ((counts["看涨"] || 0) === (counts["看跌"] || 0)) return directional[0].sentiment;
      return (counts["看涨"] || 0) > (counts["看跌"] || 0) ? "看涨" : "看跌";
    }
    if (rows.some((item) => item.sentiment === "观望")) return "观望";
    return "中性";
  }

  function uniqueSorted(values) {
    return Array.from(new Set(values.filter(Boolean))).sort((a, b) => String(a).localeCompare(String(b), "zh-Hans-CN"));
  }

  function groupBy(values, keyFn) {
    const grouped = new Map();
    for (const value of values) {
      const key = keyFn(value) || "unknown";
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(value);
    }
    return grouped;
  }

  function scoreItemForInsight(a, b) {
    const score = (item) => {
      let value = 0;
      if (item.quote) value += 4;
      if (item.tickers.length) value += 3;
      if (item.sentiment !== "中性") value += 2;
      if (item.sourceType === "substack" || item.sourceType === "discord") value += 1;
      value += Math.min(4, Math.floor((item.text || "").length / 180));
      return value;
    };
    return score(b) - score(a) || b.createdMs - a.createdMs;
  }

  function countValues(values) {
    return values.filter(Boolean).reduce((acc, value) => {
      acc[value] = (acc[value] || 0) + 1;
      return acc;
    }, {});
  }

  function topEntries(counts, limit) {
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), "zh-Hans-CN"))
      .slice(0, limit);
  }

  function topTradableThemes(counts, limit) {
    return Object.entries(counts)
      .filter(([theme]) => theme !== "综合观察")
      .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), "zh-Hans-CN"))
      .slice(0, limit);
  }

  function increment(counts, value) {
    if (!value) return;
    counts[value] = (counts[value] || 0) + 1;
  }

  function parseLocalDateTime(value, timezone) {
    if (!value) return new Date(NaN);
    const [date, time = "00:00"] = value.split("T");
    const [year, month, day] = date.split("-").map(Number);
    const [hour, minute] = time.split(":").map(Number);
    const offset = timezoneOffsets[timezone] ?? 0;
    return new Date(Date.UTC(year, month - 1, day, hour - offset, minute || 0, 0));
  }

  function formatLocalInput(ms, timezone) {
    const parts = toLocalParts(ms, timezone);
    return `${parts.date}T${parts.time}`;
  }

  function toLocalParts(ms, timezone) {
    const offset = timezoneOffsets[timezone] ?? 0;
    const local = new Date(ms + offset * 60 * 60 * 1000);
    const year = local.getUTCFullYear();
    const month = pad(local.getUTCMonth() + 1);
    const day = pad(local.getUTCDate());
    const hour = pad(local.getUTCHours());
    const minute = pad(local.getUTCMinutes());
    return { date: `${year}-${month}-${day}`, time: `${hour}:${minute}` };
  }

  function formatDisplayTime(ms, timezone) {
    const parts = toLocalParts(ms, timezone);
    return `${parts.date.slice(5)} ${parts.time}`;
  }

  function formatTrendDate(value) {
    const [year, month, day] = value.split("-");
    return `${month}-${day} · ${year}`;
  }

  function compactText(text, limit) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean;
  }

  function hasAny(text, values) {
    return values.some((value) => text.includes(value));
  }

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function escapeRegex(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replace(/`/g, "&#096;");
  }

  function debounce(fn, wait) {
    let timeout = null;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => fn(...args), wait);
    };
  }
})();
