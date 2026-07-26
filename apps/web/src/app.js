(function () {
  const API_BASE = window.__QUANT_INTEL_API_BASE__ || "http://127.0.0.1:8000/api";
  const fallbackRawItems = Array.isArray(window.__HIGH_QUALITY_ITEMS__) ? window.__HIGH_QUALITY_ITEMS__ : [];

  const knownTickers = [
    "MU", "MRVL", "NBIS", "MAAA", "ARM", "AMD", "AVGO", "MP", "RKLB", "VRT", "SPCX", "XLE", "BX", "IGV",
    "SPX", "QQQ", "SPY", "TAIX", "LPK", "MXL", "POET", "LITE", "COHR", "RDDT", "META", "MSFT", "CRM",
    "SNDK", "EWY", "SIVE", "RPI", "XFAB", "SOI", "AAOI", "INTC", "ASML", "ACMR", "ORCL", "TTWO",
    "NVDA", "HMAX", "MMN", "AXTI", "AEHR", "AMZN", "IREN", "XLU"
  ];

  const timezoneOffsets = {
    "Asia/Shanghai": 8,
    "America/New_York": -4,
    "UTC": 0
  };

  const state = {
    preset: "3d",
    timezone: "Asia/Shanghai",
    startAt: "",
    endAt: "",
    source: "",
    author: "",
    ticker: "",
    theme: "",
    sentiment: "",
    query: "",
    selectedId: null
  };

  const els = {
    startAt: document.getElementById("startAt"),
    endAt: document.getElementById("endAt"),
    timezone: document.getElementById("timezone"),
    sourceFilter: document.getElementById("sourceFilter"),
    authorFilter: document.getElementById("authorFilter"),
    tickerFilter: document.getElementById("tickerFilter"),
    themeFilter: document.getElementById("themeFilter"),
    sentimentFilter: document.getElementById("sentimentFilter"),
    queryInput: document.getElementById("queryInput"),
    itemsBody: document.getElementById("itemsBody"),
    tickerSummary: document.getElementById("tickerSummary"),
    statCount: document.getElementById("statCount"),
    statWindow: document.getElementById("statWindow"),
    statWindowShort: document.getElementById("statWindowShort"),
    statSources: document.getElementById("statSources"),
    statSourcesShort: document.getElementById("statSourcesShort"),
    statSourceText: document.getElementById("statSourceText"),
    statSourceTextShort: document.getElementById("statSourceTextShort"),
    statTickers: document.getElementById("statTickers"),
    statTickersShort: document.getElementById("statTickersShort"),
    statTickerText: document.getElementById("statTickerText"),
    statSelected: document.getElementById("statSelected"),
    marketBias: document.getElementById("marketBias"),
    marketBiasText: document.getElementById("marketBiasText"),
    coreTheme: document.getElementById("coreTheme"),
    coreThemeText: document.getElementById("coreThemeText"),
    riskBadge: document.getElementById("riskBadge"),
    riskSummary: document.getElementById("riskSummary"),
    fundamentalBody: document.getElementById("fundamentalBody"),
    sourceInsightTables: document.getElementById("sourceInsightTables"),
    tickerHistory: document.getElementById("tickerHistory"),
    qualityList: document.getElementById("qualityList"),
    trendCards: document.getElementById("trendCards"),
    trendPrev: document.getElementById("trendPrev"),
    trendNext: document.getElementById("trendNext"),
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
    globalCopyNotice: document.getElementById("globalCopyNotice")
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
    await loadItems();
    setPreset("3d");
    fillFilterOptions();
    render();
  }

  async function loadItems() {
    const apiItems = await fetchApiItems();
    const fallbackById = new Map(fallbackRawItems.map((item) => [item.id, item]));
    const sourceItems = apiItems ? apiItems.map((item) => fallbackById.get(item.id) || item) : fallbackRawItems;
    apiAvailable = Boolean(apiItems);
    items = sourceItems.map(normalizeItem).sort((a, b) => b.createdMs - a.createdMs);
    const validTimes = items.map((item) => item.createdMs).filter(Number.isFinite);
    minMs = validTimes.length ? Math.min(...validTimes) : Date.now();
    maxMs = validTimes.length ? Math.max(...validTimes) : Date.now();
    updateDataStatus(apiAvailable ? `API 数据 · ${items.length} 条` : `静态备份 · ${items.length} 条`);
  }

  async function fetchApiItems() {
    if (!window.fetch) return null;
    try {
      const response = await fetch(`${API_BASE}/items?limit=500`, { cache: "no-store" });
      if (!response.ok) throw new Error(`API ${response.status}`);
      const payload = await response.json();
      if (!Array.isArray(payload.items)) return null;
      return payload.items.map(apiItemToRaw);
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
        text: item.content_preview || "",
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
      relations: {},
      metrics: item.metrics || {},
      entities: (item.tickers || []).map((ticker) => ({
        type: "ticker",
        value: ticker,
        normalized_value: ticker,
        confidence: 1,
        source: "api"
      })),
      analysis: item.analysis || null,
      raw_payload: item
    };
  }

  function updateDataStatus(text) {
    const el = document.getElementById("dataStatus");
    if (el) el.textContent = text;
  }

  function normalizeItem(item) {
    const text = item.content?.text || "";
    const title = item.content?.title || "";
    const allText = `${title}\n${text}`;
    const tickers = extractTickers(item, allText);
    const sourceName = item.source?.name || item.source?.id || item.source?.type || "unknown";
    const theme = inferTheme(allText, tickers, item.source?.id || "");
    const sentiment = inferSentiment(allText, theme);
    const priceStatus = inferPriceStatus(allText);
    const author = item.author?.handle || item.author?.display_name || "unknown";
    const createdAt = item.timestamps?.created_at || item.timestamps?.collected_at || "";
    const createdMs = Date.parse(createdAt);

    return {
      raw: item,
      id: item.id,
      createdAt,
      createdMs,
      sourceType: item.source?.type || "",
      sourceId: item.source?.id || "",
      sourceName,
      author,
      authorDisplay: item.author?.display_name || item.author?.handle || "unknown",
      externalUrl: item.external?.url || "",
      externalId: item.external?.id || "",
      text,
      title,
      tickers,
      theme,
      sentiment,
      priceStatus,
      quote: extractQuote(text || title),
      reason: inferReason(text || title, theme, tickers, sentiment, sourceName),
      risk: inferRisk(text || title, theme, tickers, sentiment, priceStatus),
      metrics: item.metrics || {}
    };
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
    return Array.from(values).sort();
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

  function inferSentiment(text) {
    const lower = text.toLowerCase();
    if (hasAny(lower, ["sell", "sold", "all sold", "lock profit", "take profit", "出了", "出，", "锁利", "很软", "nooo", "bearish"])) return "看跌";
    if (hasAny(lower, ["buy", "bought", "added", "long", "undervalued", "cheap", "看涨", "买入", "加仓", "拿着", "hold", "support", "dovish", "supply constrained", "bullish"])) return "看涨";
    if (hasAny(lower, ["wait", "watch", "let’s see", "let's see", "no firm opinion", "观察", "再看", "下周再看"])) return "观望";
    return "中性";
  }

  function inferPriceStatus(text) {
    const lower = text.toLowerCase();
    if (hasAny(lower, ["tripled", "ath", "all time high", "+", "up ", "暴涨", "已涨", "锁利", "take profit", "目标", "涨"])) return "已涨";
    if (hasAny(lower, ["undervalued", "support", "buy", "bought", "added", "加仓", "低位", "未充分", "market missed"])) return "未涨/待兑现";
    return "未涨/待验证";
  }

  function fillFilterOptions() {
    fillSelect(els.sourceFilter, [["", "全部来源"], ...uniqueOptions(items.map((item) => item.sourceId), sourceLabel)]);
    fillSelect(els.authorFilter, [["", "全部作者"], ...uniqueOptions(items.map((item) => item.author), (value) => value)]);
    fillSelect(els.tickerFilter, [["", "全部标的"], ...uniqueOptions(items.flatMap((item) => item.tickers), (value) => value)]);
    fillSelect(els.themeFilter, [["", "全部题材"], ...uniqueOptions(items.map((item) => item.theme), (value) => value)]);
  }

  function bindEvents() {
    document.querySelectorAll("[data-preset]").forEach((button) => {
      button.addEventListener("click", () => {
        setPreset(button.dataset.preset);
        render();
      });
    });

    els.startAt.addEventListener("change", () => {
      state.preset = "custom";
      updatePresetButtons();
      state.startAt = els.startAt.value;
      render();
    });
    els.endAt.addEventListener("change", () => {
      state.preset = "custom";
      updatePresetButtons();
      state.endAt = els.endAt.value;
      render();
    });
    els.timezone.addEventListener("change", () => {
      state.timezone = els.timezone.value;
      setPreset(state.preset === "custom" ? "3d" : state.preset);
      render();
    });

    [
      [els.sourceFilter, "source"],
      [els.authorFilter, "author"],
      [els.tickerFilter, "ticker"],
      [els.themeFilter, "theme"],
      [els.sentimentFilter, "sentiment"]
    ].forEach(([element, key]) => {
      element.addEventListener("change", () => {
        state[key] = element.value;
        render();
      });
    });

    els.queryInput.addEventListener("input", debounce(() => {
      state.query = els.queryInput.value.trim();
      render();
    }, 120));

    els.resetFilters.addEventListener("click", () => {
      state.source = "";
      state.author = "";
      state.ticker = "";
      state.theme = "";
      state.sentiment = "";
      state.query = "";
      els.sourceFilter.value = "";
      els.authorFilter.value = "";
      els.tickerFilter.value = "";
      els.themeFilter.value = "";
      els.sentimentFilter.value = "";
      els.queryInput.value = "";
      setPreset("3d");
      render();
    });

    els.closeDrawer.addEventListener("click", closeDrawer);
    els.drawerScrim.addEventListener("click", closeDrawer);
    els.copyContext.addEventListener("click", () => copyCurrentContext("markdown"));
    els.copyJson.addEventListener("click", () => copyCurrentContext("json"));
    els.trendPrev.addEventListener("click", () => scrollTrendCards(-1));
    els.trendNext.addEventListener("click", () => scrollTrendCards(1));
  }

  function setPreset(preset) {
    state.preset = preset;
    const end = preset === "all" ? maxMs : maxMs;
    let start = minMs;
    const local = toLocalParts(end, state.timezone);
    const localDayStart = parseLocalDateTime(`${local.date}T00:00`, state.timezone).getTime();
    if (preset === "today") {
      start = localDayStart;
    } else if (preset === "24h") {
      start = end - 24 * 60 * 60 * 1000;
    } else if (preset === "3d") {
      start = localDayStart - 2 * 24 * 60 * 60 * 1000;
    } else if (preset === "7d") {
      start = localDayStart - 6 * 24 * 60 * 60 * 1000;
    }
    state.startAt = formatLocalInput(start, state.timezone);
    state.endAt = formatLocalInput(end, state.timezone);
    els.startAt.value = state.startAt;
    els.endAt.value = state.endAt;
    updatePresetButtons();
  }

  function updatePresetButtons() {
    document.querySelectorAll("[data-preset]").forEach((button) => {
      button.classList.toggle("active", button.dataset.preset === state.preset);
    });
  }

  function render() {
    filteredItems = filterItems();
    analysisPromptCache.clear();
    analysisPromptSeq = 0;
    renderStats(filteredItems);
    renderDailyTrends(filteredItems);
    renderFundamentalAnalysis(filteredItems);
    renderSourceInsights(filteredItems);
    renderTable(filteredItems);
    renderTickerSummary(filteredItems);
    renderTickerHistory(filteredItems);
    renderQualityNotes(filteredItems);
  }

  function filterItems() {
    const startMs = parseLocalDateTime(state.startAt, state.timezone).getTime();
    const endMs = parseLocalDateTime(state.endAt, state.timezone).getTime();
    const query = state.query.toLowerCase();
    return items.filter((item) => {
      if (item.createdMs < startMs || item.createdMs > endMs) return false;
      if (state.source && item.sourceId !== state.source) return false;
      if (state.author && item.author !== state.author) return false;
      if (state.ticker && !item.tickers.includes(state.ticker)) return false;
      if (state.theme && item.theme !== state.theme) return false;
      if (state.sentiment && item.sentiment !== state.sentiment) return false;
      if (query) {
        const haystack = `${item.text} ${item.title} ${item.author} ${item.sourceName} ${item.theme} ${item.tickers.join(" ")}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
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
    const groups = Array.from(groupBy(rows, (item) => item.sourceId).entries())
      .sort((a, b) => b[1].length - a[1].length)
      .slice(0, 4);
    els.sourceInsightTables.innerHTML = groups.map(([sourceId, sourceRows], index) => {
      const insights = buildSourceInsightRows(sourceRows);
      return `
        <section class="source-section">
          <div class="source-title-line">
            <h3>信息源 ${index + 1}：${escapeHtml(sourceLabel(sourceId))}</h3>
            <span class="source-badge">${escapeHtml(sourceRows[0]?.sourceType || "source")} · ${sourceRows.length} 条</span>
          </div>
          <div class="table-wrap report-table-wrap">
            <table class="report-table source-table">
              <thead>
                <tr>
                  <th class="col-theme">题材</th>
                  <th class="col-tickers">标的</th>
                  <th class="col-view">观点</th>
                  <th class="col-specific">具体标的</th>
                  <th class="col-reason">理由</th>
                  <th class="col-risk">风险</th>
                  <th class="col-quote">相关原句</th>
                  <th class="col-action">操作</th>
                </tr>
              </thead>
              <tbody>
                ${insights.map(renderInsightRow).join("")}
              </tbody>
            </table>
          </div>
        </section>
      `;
    }).join("") || `<div class="empty-state">当前筛选条件下没有信息源观点</div>`;
    bindAnalysisPromptButtons(els.sourceInsightTables);
  }

  function renderTickerHistory(rows) {
    const tickerCounts = countValues(rows.flatMap((item) => item.tickers));
    const tickers = topEntries(tickerCounts, 8).map(([ticker]) => ticker);
    els.tickerHistory.innerHTML = tickers.map((ticker) => {
      const related = rows
        .filter((item) => item.tickers.includes(ticker))
        .sort((a, b) => a.createdMs - b.createdMs);
      const timeline = related.slice(-6).map((item) => `
        <li>
          <strong>${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))}</strong>
          ${renderSentiment(item.sentiment)}
          <span>${escapeHtml(sourceShort(item.sourceId, item.sourceType))}：${escapeHtml(compactText(item.reason, 150))}</span>
          <div class="quote history-quote">${escapeHtml(item.quote)}</div>
        </li>
      `).join("");
      const conclusion = buildTickerConclusion(ticker, related);
      return `
        <article class="history-panel">
          <h3>${escapeHtml(ticker)}</h3>
          <p>${escapeHtml(conclusion)}</p>
          <ul>${timeline}</ul>
        </article>
      `;
    }).join("") || `<div class="empty-state">当前筛选条件下没有可串联的标的历史观点</div>`;
  }

  function renderQualityNotes(rows) {
    const sourceTypes = countValues(rows.map((item) => item.sourceType));
    const missingTicker = rows.filter((item) => !item.tickers.length).length;
    const sourceText = topEntries(sourceTypes, 5).map(([type, count]) => `${type || "unknown"} ${count} 条`).join("，") || "暂无来源";
    const notes = [
      `当前窗口共 ${rows.length} 条信息，来源类型分布：${sourceText}。`,
      `未识别出明确标的的信息 ${missingTicker} 条，这类内容会保留为宏观、题材或综合观察。`,
      `“已涨/未涨”仍基于文本语义推断，生产版应接入行情模块，用发布时间价格和盘前价格对比校验。`,
      `Discord/X/Substack 的真实采集完整性依赖登录状态、网络和来源权限；自动化失败时应优先检查采集运行记录。`,
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
    const themeGroups = Array.from(groupBy(rows, (item) => item.theme).entries())
      .sort((a, b) => b[1].length - a[1].length)
      .slice(0, 8);
    return themeGroups.map(([theme, themeRows]) => {
      const leadRows = themeRows.slice().sort(scoreItemForInsight).slice(0, 2);
      const tickers = uniqueSorted(themeRows.flatMap((item) => item.tickers)).slice(0, 8);
      const sentiment = dominantValue(themeRows.map((item) => item.sentiment)) || "中性";
      const relatedItems = themeRows.slice().sort(scoreItemForInsight).slice(0, 8);
      return {
        theme,
        tickers,
        sentiment,
        specific: buildSpecificTickers(themeRows, tickers),
        reason: buildEvidenceText(leadRows, theme),
        risk: buildGroupRisk(themeRows, theme),
        quote: leadRows.map((item) => item.quote).filter(Boolean).slice(0, 2).join("；") || "暂无相关原句",
        sourceId: themeRows[0]?.sourceId || "",
        sourceName: themeRows[0]?.sourceName || sourceLabel(themeRows[0]?.sourceId || ""),
        sourceType: themeRows[0]?.sourceType || "",
        itemIds: relatedItems.map((item) => item.id),
        items: relatedItems,
      };
    });
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
    els.statSelected.textContent = item.tickers[0] || item.theme;
    els.drawerTitle.textContent = `${item.tickers[0] || item.theme} · ${item.sentiment}`;
    els.openOriginal.href = item.externalUrl || "#";
    els.openOriginal.style.display = item.externalUrl ? "inline-flex" : "none";
    els.copyNotice.textContent = "";
    els.copyNotice.classList.remove("visible");

    const detail = await fetchItemDetail(itemId);
    if (detail) {
      applyDetailToItem(item, detail);
    }
    const context = buildContext(item);
    els.drawerContent.innerHTML = renderDrawerContent(item, context);
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
  }

  function closeDrawer() {
    els.drawer.classList.remove("open");
    els.drawer.setAttribute("aria-hidden", "true");
  }

  function renderDrawerContent(item, context) {
    return `
      <section class="detail-block">
        <h3>当前信息</h3>
        <p><strong>数据库 ID：</strong>${escapeHtml(item.id)}</p>
        <p><strong>发布时间：</strong>${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))}</p>
        <p><strong>来源：</strong>${escapeHtml(item.sourceName)} · ${escapeHtml(item.authorDisplay)}</p>
        <p><strong>题材/观点：</strong>${escapeHtml(item.theme)} · ${renderSentiment(item.sentiment)}</p>
        <p><strong>标的：</strong>${escapeHtml(formatSpecificTickers(item))}</p>
        <div class="quote-block">${escapeHtml(item.text || item.title || "")}</div>
      </section>
      ${renderContextList("同作者近 10 条", context.sameAuthor)}
      ${renderContextList("同标的近 10 条", context.sameTicker)}
      ${renderContextList("同题材近 10 条", context.sameTheme)}
      <section class="detail-block">
        <h3>数据库关联字段</h3>
        <p><strong>external_id：</strong>${escapeHtml(item.externalId || "-")}</p>
        <p><strong>external_url：</strong>${item.externalUrl ? `<a href="${escapeAttribute(item.externalUrl)}" target="_blank" rel="noreferrer">${escapeHtml(item.externalUrl)}</a>` : "-"}</p>
        <p><strong>source_id：</strong>${escapeHtml(item.sourceId)}</p>
        <p><strong>content_hash：</strong>${escapeHtml(item.raw.content?.hash || "-")}</p>
      </section>
    `;
  }

  function renderContextList(title, rows) {
    const list = rows.map((item) => `
      <li>
        <strong>${escapeHtml(formatDisplayTime(item.createdMs, state.timezone))}</strong>
        · ${escapeHtml(item.authorDisplay)}
        · ${escapeHtml(item.tickers.join(", ") || item.theme)}
        <br>${escapeHtml(compactText(item.text || item.title, 180))}
      </li>
    `).join("");
    return `
      <section class="detail-block">
        <h3>${escapeHtml(title)}</h3>
        <ul>${list || "<li>暂无相关上下文</li>"}</ul>
      </section>
    `;
  }

  function buildContext(item) {
    const sameAuthor = items
      .filter((candidate) => candidate.id !== item.id && candidate.author === item.author)
      .sort((a, b) => Math.abs(a.createdMs - item.createdMs) - Math.abs(b.createdMs - item.createdMs))
      .slice(0, 10);
    const sameTicker = items
      .filter((candidate) => candidate.id !== item.id && candidate.tickers.some((ticker) => item.tickers.includes(ticker)))
      .sort((a, b) => Math.abs(a.createdMs - item.createdMs) - Math.abs(b.createdMs - item.createdMs))
      .slice(0, 10);
    const sameTheme = items
      .filter((candidate) => candidate.id !== item.id && candidate.theme === item.theme)
      .sort((a, b) => Math.abs(a.createdMs - item.createdMs) - Math.abs(b.createdMs - item.createdMs))
      .slice(0, 10);
    return { sameAuthor, sameTicker, sameTheme };
  }

  function buildCodexMarkdown(item) {
    const context = buildContext(item);
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
- 具体标的: ${formatSpecificTickers(item)}

### 原文
> ${compactText(item.text || item.title, 1200).replace(/\n/g, "\n> ")}

## 数据库关联字段
- source_type: ${item.sourceType}
- source_id: ${item.sourceId}
- external_id: ${item.externalId || "-"}
- content_hash: ${item.raw.content?.hash || "-"}

## 同作者近 10 条
${context.sameAuthor.map(contextLine).join("\n") || "- 暂无"}

## 同标的近 10 条
${context.sameTicker.map(contextLine).join("\n") || "- 暂无"}

## 同题材近 10 条
${context.sameTheme.map(contextLine).join("\n") || "- 暂无"}

## 希望你输出
1. 这条信息是否构成交易信号
2. 看涨/看跌/中性/观望
3. 证据链
4. 风险和反证
5. 如果纳入盘前日报，应该放在哪个题材和标的下
`;
  }

  function contextLine(item) {
    return `- ${item.createdAt} · ${item.sourceName} · ${item.authorDisplay} · ${item.tickers.join(", ") || item.theme}: ${compactText(item.text || item.title, 260)}`;
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
- 证据/理由: ${evidence}
- 风险/反证: ${row.risk}
- 相关原句: ${row.quote}
${isSource ? `- 具体标的解释: ${row.specific}` : ""}

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
   - 原文摘录: ${compactText(item.text || item.title, 900)}`).join("\n\n");
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

  function sourceShort(sourceId, sourceType) {
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
