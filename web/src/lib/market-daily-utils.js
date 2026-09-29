"use strict";
var marketDailyUtils = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // src/lib/market-daily-utils.ts
  var market_daily_utils_exports = {};
  __export(market_daily_utils_exports, {
    buildMarketDailyChartSvg: () => buildMarketDailyChartSvg,
    buildMarketDailyCharts: () => buildMarketDailyCharts,
    default: () => market_daily_utils_default,
    formatMarketDailyStatus: () => formatMarketDailyStatus,
    summarizeMarketDaily: () => summarizeMarketDaily
  });

  // src/lib/market-facts.ts
  function isRecord(value) {
    return typeof value === "object" && value !== null;
  }
  function isMarketDailyPayload(value) {
    return isRecord(value) && typeof value.schema_version === "string" && typeof value.run_id === "string" && Array.isArray(value.facts) && value.facts.every((item) => isRecord(item) && typeof item.id === "string");
  }

  // src/lib/market-daily-utils.ts
  var MARKET_DAILY_FACTS = [
    ["index.spx.change_percent", "\u6807\u666E 500 \u65E5\u6DA8\u8DCC", "%"],
    ["index.dow.change_percent", "\u9053\u6307\u65E5\u6DA8\u8DCC", "%"],
    ["index.nasdaq.change_percent", "\u7EB3\u6307\u65E5\u6DA8\u8DCC", "%"],
    ["index.russell2000.change_percent", "\u7F57\u7D20 2000 \u65E5\u6DA8\u8DCC", "%"],
    ["treasury.2y.change_bp", "2 \u5E74\u671F\u7F8E\u503A\u6536\u76CA\u7387\u65E5\u53D8\u52A8", " bp"],
    ["treasury.5y.change_bp", "5 \u5E74\u671F\u7F8E\u503A\u6536\u76CA\u7387\u65E5\u53D8\u52A8", " bp"],
    ["treasury.10y.change_bp", "10 \u5E74\u671F\u7F8E\u503A\u6536\u76CA\u7387\u65E5\u53D8\u52A8", " bp"],
    ["treasury.30y.change_bp", "30 \u5E74\u671F\u7F8E\u503A\u6536\u76CA\u7387\u65E5\u53D8\u52A8", " bp"],
    ["treasury.2y.level_percent", "2 \u5E74\u671F\u7F8E\u503A\u6536\u76CA\u7387\u6C34\u5E73", "%"],
    ["treasury.5y.level_percent", "5 \u5E74\u671F\u7F8E\u503A\u6536\u76CA\u7387\u6C34\u5E73", "%"],
    ["treasury.10y.level_percent", "10 \u5E74\u671F\u7F8E\u503A\u6536\u76CA\u7387\u6C34\u5E73", "%"],
    ["treasury.30y.level_percent", "30 \u5E74\u671F\u7F8E\u503A\u6536\u76CA\u7387\u6C34\u5E73", "%"],
    ["cross_asset.brent.close", "\u5E03\u4F26\u7279\u671F\u8D27\u6536\u76D8", " \u7F8E\u5143/\u6876"],
    ["cross_asset.brent.change_percent", "\u5E03\u4F26\u7279\u65E5\u6DA8\u8DCC", "%"],
    ["cross_asset.gold.close", "COMEX \u9EC4\u91D1\u671F\u8D27\u6536\u76D8", " \u7F8E\u5143/\u91D1\u8861\u76CE\u53F8"],
    ["cross_asset.gold.change_percent", "\u9EC4\u91D1\u65E5\u6DA8\u8DCC", "%"],
    ["cross_asset.silver.close", "COMEX \u767D\u94F6\u671F\u8D27\u6536\u76D8", " \u7F8E\u5143/\u91D1\u8861\u76CE\u53F8"],
    ["cross_asset.silver.change_percent", "\u767D\u94F6\u65E5\u6DA8\u8DCC", "%"],
    ["cross_asset.bitcoin.close", "CME \u6BD4\u7279\u5E01\u671F\u8D27\u6536\u76D8", " \u7F8E\u5143/BTC"],
    ["cross_asset.bitcoin.change_percent", "\u6BD4\u7279\u5E01\u671F\u8D27\u65E5\u6DA8\u8DCC", "%"],
    ["cross_asset.bitcoin_spot.close", "BTC/USD \u73B0\u8D27\u6536\u76D8", " \u7F8E\u5143/BTC"],
    ["cross_asset.bitcoin_spot.change_percent", "BTC/USD \u73B0\u8D27\u65E5\u6DA8\u8DCC", "%"],
    ["macro.cpi_yoy", "CPI \u540C\u6BD4", "%"],
    ["macro.pce_yoy", "PCE \u540C\u6BD4", "%"],
    ["macro.unemployment_rate", "\u5931\u4E1A\u7387", "%"],
    ["macro.payroll_change_thousands", "\u975E\u519C\u5C31\u4E1A\u6708\u53D8\u52A8", " \u5343\u4EBA"]
  ];
  var FRED_SOURCE = /^https:\/\/fred\.stlouisfed\.org\/series\/[A-Z0-9]+$/;
  var TREASURY_SOURCE = /^https:\/\/home\.treasury\.gov\/resource-center\/data-chart-center\/interest-rates\/daily-treasury-rates\.csv\/all\/\d{6}\?_format=csv&field_tdr_date_value_month=\d{6}&page=&type=daily_treasury_yield_curve$/;
  var YAHOO_SOURCES = {
    brent: /^https:\/\/finance\.yahoo\.com\/quote\/BZ%3DF\/history\/$/,
    gold: /^https:\/\/finance\.yahoo\.com\/quote\/GC%3DF\/history\/$/,
    silver: /^https:\/\/finance\.yahoo\.com\/quote\/SI%3DF\/history\/$/,
    bitcoin: /^https:\/\/finance\.yahoo\.com\/quote\/BTC%3DF\/history\/$/
  };
  var FMP_COMMODITY_URL = "https://site.financialmodelingprep.com/developer/docs/stable/commodities-historical-price-eod-full";
  var FMP_CRYPTO_URL = "https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full";
  var BTC_SPOT_SOURCES = /* @__PURE__ */ new Map([
    ["Financial Modeling Prep|" + FMP_CRYPTO_URL, "BTC/USD cryptocurrency EOD (FMP BTCUSD)"],
    ["Data provided by CoinGecko|https://www.coingecko.com/en/api", "BTC/USD spot at 16:00 ET (CoinGecko bitcoin/USD)"],
    ["Kraken|https://www.kraken.com/prices/bitcoin", "BTC/USD spot at 16:00 ET (Kraken XBT/USD)"]
  ]);
  var FMP_COMMODITY_SYMBOLS = { brent: "BZUSD", gold: "GCUSD", silver: "SIUSD" };
  var FUTURES_MONTH_CODES = "FGHJKMNQUVXZ";
  var COMMODITY_MONTHS = { gold: [2, 4, 6, 8, 12], silver: [3, 5, 7, 9, 12] };
  function datedCommoditySymbol(asset, reportDate) {
    if (!Object.hasOwn(COMMODITY_MONTHS, asset) && asset !== "brent") return null;
    const [year, month] = reportDate.split("-").map(Number);
    const offset = asset === "brent" ? 2 : Array.from({ length: 12 }, (_, i) => i + 1).find((step) => COMMODITY_MONTHS[asset]?.includes((month - 1 + step) % 12 + 1)) ?? 1;
    const absoluteMonth = month - 1 + offset;
    const deliveryMonth = absoluteMonth % 12 + 1;
    const deliveryYear = year + Math.floor(absoluteMonth / 12);
    const root = { brent: "BZ", gold: "GC", silver: "SI" }[asset];
    const exchange = asset === "brent" ? "NYM" : "CMX";
    return `${root}${FUTURES_MONTH_CODES[deliveryMonth - 1]}${String(deliveryYear % 100).padStart(2, "0")}.${exchange}`;
  }
  var YAHOO_INDEX_SOURCES = {
    spx: /^https:\/\/finance\.yahoo\.com\/quote\/%5EGSPC\/history\/$/,
    dow: /^https:\/\/finance\.yahoo\.com\/quote\/%5EDJI\/history\/$/,
    nasdaq: /^https:\/\/finance\.yahoo\.com\/quote\/%5EIXIC\/history\/$/,
    russell2000: /^https:\/\/finance\.yahoo\.com\/quote\/%5ERUT\/history\/$/
  };
  var EQUITY_ID = /^equity\.([a-z]{1,5})\.(close|change_percent)$/;
  var ALPACA_STOCK_BARS_URL = "https://docs.alpaca.markets/us/reference/stockbars";
  var CORE_EQUITIES = /* @__PURE__ */ new Set(["MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "META"]);
  var MARKET_DAILY_GAPS = {
    rates_lag: "\u7F8E\u503A\u6536\u76CA\u7387\u5F53\u65E5\u53D8\u52A8",
    quotes: "\u6307\u6570\u884C\u60C5",
    research: "\u7814\u7A76\u89E3\u91CA",
    fred: "\u90E8\u5206 FRED \u6570\u636E",
    cross_asset: "\u5E03\u4F26\u7279\u3001\u91D1\u94F6\u6216\u6BD4\u7279\u5E01\u884C\u60C5",
    equities: "\u90E8\u5206\u7F8E\u80A1\u4E2A\u80A1\u884C\u60C5"
  };
  var MARKET_DAILY_CLAIM_SECTIONS = [
    ["market", "\u5E02\u573A\u8868\u73B0"],
    ["drivers", "\u5E02\u573A\u9A71\u52A8\u56E0\u7D20"],
    ["movers", "\u4E3B\u8981\u4E2A\u80A1"],
    ["macro", "\u7ECF\u6D4E\u6570\u636E\u4E0E\u7F8E\u8054\u50A8\u52A8\u6001"],
    ["company_news", "\u516C\u53F8\u65B0\u95FB"],
    ["other", "\u5176\u4ED6\u5DF2\u6838\u5B9E\u5185\u5BB9"]
  ];
  function validHttpSource(sourceUrl) {
    try {
      const parsed = new URL(sourceUrl);
      return parsed.protocol === "https:" && Boolean(parsed.hostname);
    } catch {
      return false;
    }
  }
  function validMarketDailyFact(id, fact, reportDate) {
    const url = fact.source_url ?? "";
    const equity = id.match(EQUITY_ID);
    if (equity) {
      const [, symbol, field] = equity;
      return fact.observation_date === reportDate && fact.quality === "ok" && (field === "close" ? fact.value > 0 : Math.abs(fact.value) <= 100) && fact.instrument === symbol.toUpperCase() && (fact.source === "Yahoo Finance" && url === `https://finance.yahoo.com/quote/${symbol.toUpperCase()}/history/` || fact.source === "Alpaca SIP" && url === ALPACA_STOCK_BARS_URL) && fact.metric === (field === "close" ? "stock_close" : "daily_return") && fact.unit === (field === "close" ? "USD/share" : "percent");
    }
    if (id.startsWith("index.")) {
      const key = id.split(".")[1];
      return fact.observation_date === reportDate && (fact.quality === "reviewed" && validHttpSource(url) || fact.quality === "ok" && fact.source === "Yahoo Finance" && fact.metric === "daily_return" && fact.unit === "percent" && Boolean(YAHOO_INDEX_SOURCES[key]?.test(url)));
    }
    if (id.startsWith("treasury.")) {
      const isLevel = id.endsWith(".level_percent");
      const expectedUnit = isLevel ? "percent" : "basis_points";
      const expectedMetric = isLevel ? "yield_level" : "yield_change";
      const fresh = fact.observation_date === reportDate && ["ok", "reviewed"].includes(fact.quality);
      const lagged = fact.observation_date < reportDate && fact.quality === "lagged";
      return fact.unit === expectedUnit && fact.metric === expectedMetric && (TREASURY_SOURCE.test(url) && fresh || FRED_SOURCE.test(url) && (fresh || lagged));
    }
    if (id.startsWith("cross_asset.")) {
      const [, asset, field] = id.split(".");
      if (asset === "bitcoin_spot") return (field === "close" || field === "change_percent") && BTC_SPOT_SOURCES.has(`${fact.source}|${url}`) && fact.instrument === BTC_SPOT_SOURCES.get(`${fact.source}|${url}`) && fact.quality === "ok" && fact.observation_date === reportDate && fact.unit === (field === "close" ? "USD/bitcoin" : "percent") && fact.metric === (field === "close" ? "crypto_spot_close" : "daily_return");
      const source = YAHOO_SOURCES[asset];
      const fmpSymbol = FMP_COMMODITY_SYMBOLS[asset];
      const isClose = field === "close";
      const units = { brent: "USD/barrel", gold: "USD/troy_ounce", silver: "USD/troy_ounce", bitcoin: "USD/bitcoin" };
      const metric = isClose ? asset === "bitcoin" ? "crypto_futures_close" : "commodity_close" : "daily_return";
      const datedSymbol = datedCommoditySymbol(asset, reportDate);
      const datedValid = datedSymbol && url === `https://finance.yahoo.com/quote/${datedSymbol}/history/` && String(fact.instrument ?? "").includes(`(${datedSymbol})`);
      const yahooValid = fact.source === "Yahoo Finance" && (Boolean(source) && source.test(url) || datedValid);
      const fmpValid = Boolean(fmpSymbol) && url === FMP_COMMODITY_URL && fact.source === "Financial Modeling Prep" && String(fact.instrument ?? "").includes(`(FMP ${fmpSymbol}, continuous)`);
      return (yahooValid || fmpValid) && fact.quality === "ok" && fact.observation_date === reportDate && fact.unit === (isClose ? units[asset] : "percent") && fact.metric === metric;
    }
    if (id.startsWith("macro.")) return FRED_SOURCE.test(url);
    return false;
  }
  function summarizeMarketDaily(payload) {
    if (!isMarketDailyPayload(payload) || !/^1\./.test(payload.schema_version ?? "") || payload.quality_summary?.status === "fixture" || !/^daily-\d{4}-\d{2}-\d{2}$/.test(payload.run_id ?? "") || !Array.isArray(payload.facts)) return null;
    if (payload.facts.some((fact) => String(fact.id ?? "").startsWith("equity.") && !EQUITY_ID.test(fact.id))) return null;
    const date = payload.run_id.slice(6);
    const rows = [];
    for (const [id, label, unit] of MARKET_DAILY_FACTS) {
      const fact = payload.facts.find((item) => item.id === id);
      if (!fact) continue;
      const isIndex = id.startsWith("index.");
      const isTreasury = id.startsWith("treasury.");
      const isCrossAsset = id.startsWith("cross_asset.");
      if (typeof fact.value !== "number" || !Number.isFinite(fact.value) || !/^\d{4}-\d{2}-\d{2}$/.test(fact.observation_date ?? "") || !validMarketDailyFact(id, fact, date)) return null;
      const sourceUrl = fact.source_url;
      rows.push({
        id,
        label: label.replace(/日涨跌|收益率日变动/g, "").trim(),
        value: fact.value,
        text: `${label} ${fact.value.toFixed(2)}${unit}`,
        observationDate: fact.observation_date,
        sourceUrl,
        instrument: fact.instrument ?? "",
        sourceLabel: isIndex ? fact.source === "Yahoo Finance" ? "Yahoo Finance" : "\u6838\u5B9E\u62A5\u9053" : isTreasury && TREASURY_SOURCE.test(sourceUrl) ? "\u7F8E\u56FD\u8D22\u653F\u90E8" : isCrossAsset ? { "Financial Modeling Prep": "FMP", "Data provided by CoinGecko": "Data provided by CoinGecko", Kraken: "Kraken" }[fact.source ?? ""] ?? "Yahoo Finance" : "FRED",
        metric: fact.metric ?? "",
        unit: fact.unit ?? "",
        quality: fact.quality
      });
    }
    for (const fact of payload.facts) {
      const match = String(fact.id ?? "").match(EQUITY_ID);
      if (!match) continue;
      if (typeof fact.value !== "number" || !Number.isFinite(fact.value) || !validMarketDailyFact(fact.id, fact, date)) return null;
      rows.push({
        id: fact.id,
        label: match[1].toUpperCase(),
        value: fact.value,
        observationDate: fact.observation_date,
        sourceUrl: fact.source_url,
        sourceLabel: fact.source ?? "",
        instrument: fact.instrument ?? "",
        metric: fact.metric ?? "",
        unit: fact.unit ?? "",
        quality: fact.quality
      });
    }
    if (!rows.length) return null;
    const yahooIndexRows = rows.filter((row) => row.id.startsWith("index.") && row.quality === "ok");
    if (yahooIndexRows.length && yahooIndexRows.length !== Object.keys(YAHOO_INDEX_SOURCES).length) return null;
    const evidenceIds = new Set([...payload.facts ?? [], ...payload.events ?? []].map((item) => item.id));
    const sectionByEvidence = /* @__PURE__ */ new Map();
    for (const [key] of MARKET_DAILY_CLAIM_SECTIONS) {
      const section = (payload.sections ?? []).find((item) => item.key === key);
      for (const id of Array.isArray(section?.claims) ? section.claims : []) {
        if (typeof id === "string" && !sectionByEvidence.has(id)) sectionByEvidence.set(id, key);
      }
    }
    const claims = [];
    for (const claim of payload.claims ?? []) {
      if (typeof claim.claim !== "string" || !claim.claim.trim() || !Array.isArray(claim.evidence_ids) || !claim.evidence_ids.length || !claim.evidence_ids.every((id) => evidenceIds.has(id)) || !Array.isArray(claim.sources) || !claim.sources.length || !claim.sources.every(validHttpSource)) return null;
      const sectionKey = claim.evidence_ids.map((id) => sectionByEvidence.get(id)).find(Boolean) ?? "other";
      claims.push({ text: claim.claim, sourceUrls: claim.sources, sectionKey });
    }
    const claimSections = MARKET_DAILY_CLAIM_SECTIONS.map(([key, title]) => ({
      key,
      title,
      claims: claims.filter((claim) => claim.sectionKey === key)
    })).filter((section) => section.claims.length);
    const gaps = (payload.missing_sources ?? []).filter((item) => Object.hasOwn(MARKET_DAILY_GAPS, item)).map((item) => MARKET_DAILY_GAPS[item]);
    for (const tenor of ["2y", "5y", "10y", "30y"]) {
      const level = rows.find((row) => row.id === `treasury.${tenor}.level_percent`);
      const change = rows.find((row) => row.id === `treasury.${tenor}.change_bp`);
      if (level && change && (level.observationDate !== change.observationDate || level.sourceUrl !== change.sourceUrl || level.sourceLabel !== change.sourceLabel)) return null;
    }
    for (const asset of [...Object.keys(YAHOO_SOURCES), "bitcoin_spot"]) {
      const close = rows.find((row) => row.id === `cross_asset.${asset}.close`);
      const change = rows.find((row) => row.id === `cross_asset.${asset}.change_percent`);
      if (Boolean(close) !== Boolean(change)) return null;
      if (close && change && (close.observationDate !== change.observationDate || close.sourceUrl !== change.sourceUrl || close.sourceLabel !== change.sourceLabel || close.instrument !== change.instrument)) return null;
    }
    const rateRows = ["2y", "5y", "10y", "30y"].map((tenor) => {
      const level = rows.find((row) => row.id === `treasury.${tenor}.level_percent`);
      const change = rows.find((row) => row.id === `treasury.${tenor}.change_bp`);
      return level || change ? {
        tenor,
        label: `${tenor.slice(0, -1)} \u5E74\u671F\u7F8E\u503A`,
        levelValue: level?.value ?? null,
        changeValue: change?.value ?? null,
        observationDate: level?.observationDate ?? change?.observationDate,
        sourceUrl: level?.sourceUrl ?? change?.sourceUrl,
        sourceLabel: level?.sourceLabel ?? change?.sourceLabel
      } : null;
    }).filter((row) => Boolean(row));
    const crossAssetRows = ["brent", "gold", "silver", "bitcoin", "bitcoin_spot"].map((name) => {
      const close = rows.find((row) => row.id === `cross_asset.${name}.close`);
      const change = rows.find((row) => row.id === `cross_asset.${name}.change_percent`);
      return close && change ? {
        name,
        label: close.label,
        priceValue: close.value,
        priceUnit: close.unit,
        changeValue: change.value,
        observationDate: close.observationDate,
        sourceUrl: close.sourceUrl,
        sourceLabel: close.sourceLabel
      } : null;
    }).filter((row) => Boolean(row));
    const equityRows = [];
    for (const symbol of [...new Set(rows.filter((row) => row.id.startsWith("equity.")).map((row) => row.id.split(".")[1]))]) {
      const close = rows.find((row) => row.id === `equity.${symbol}.close`);
      const change = rows.find((row) => row.id === `equity.${symbol}.change_percent`);
      if (!close || !change || close.observationDate !== change.observationDate || close.sourceUrl !== change.sourceUrl || close.sourceLabel !== change.sourceLabel || close.instrument !== change.instrument) return null;
      equityRows.push({
        symbol: symbol.toUpperCase(),
        priceValue: close.value,
        changeValue: change.value,
        observationDate: close.observationDate,
        sourceUrl: close.sourceUrl,
        sourceLabel: close.sourceLabel
      });
    }
    const equityStatus = payload.source_status?.equities;
    if (equityStatus?.quality === "ok" && [...CORE_EQUITIES].some((symbol) => !equityRows.some((row) => row.symbol === symbol))) return null;
    const reviewedMovers = equityStatus?.reviewed_movers ?? [];
    const moverEvidence = new Set((payload.sections ?? []).filter((section) => section.key === "movers").flatMap((section) => section.claims ?? []));
    if (!Array.isArray(reviewedMovers) || reviewedMovers.length && payload.source_status?.research?.quality !== "reviewed" || reviewedMovers.some((row) => !/^[A-Z]{1,5}$/.test(row?.ticker ?? "") || !moverEvidence.has(row?.evidence_id))) return null;
    const allowedEquities = /* @__PURE__ */ new Set([...CORE_EQUITIES, ...reviewedMovers.map((row) => row.ticker)]);
    if (equityRows.some((row) => !allowedEquities.has(row.symbol))) return null;
    const hasTextReport = Array.isArray(payload.report_formats) && payload.report_formats.includes("txt") && payload.report_formats.includes("md");
    const primaryClaims = claimSections.filter((section) => ["market", "drivers", "movers"].includes(section.key)).map((section) => ({ ...section, claims: section.claims.slice(0, 3) }));
    const secondaryClaimSections = claimSections.filter((section) => !["drivers", "movers"].includes(section.key));
    const secondaryRows = rows.filter((row) => row.id.startsWith("macro."));
    return {
      date,
      rows,
      rateRows,
      crossAssetRows,
      equityRows,
      claims,
      claimSections,
      primaryClaims,
      secondaryClaimSections,
      secondaryRows,
      gaps,
      hasTextReport,
      nextMorningRevision: payload.quality_summary?.revision === "next_morning_rechecked",
      historicalBackfill: payload.quality_summary?.revision === "historical_backfill"
    };
  }
  function buildMarketDailyCharts(summary) {
    if (!summary) return [];
    const definitions = [
      { title: "\u56DB\u5927\u6307\u6570\u6536\u76D8\u6DA8\u8DCC", unit: "%", prefix: "index.", ids: [/^index\./] },
      { title: "\u7F8E\u80A1\u4E2A\u80A1\u65E5\u6DA8\u8DCC", unit: "%", prefix: "equity.", ids: [/\.change_percent$/] },
      { title: "\u7F8E\u503A\u6536\u76CA\u7387\u6C34\u5E73", unit: "%", prefix: "treasury.", ids: [/\.level_percent$/], kind: "level" },
      { title: "\u7F8E\u503A\u6536\u76CA\u7387\u5F53\u65E5\u53D8\u52A8", unit: "bp", prefix: "treasury.", ids: [/\.change_bp$/] },
      { title: "\u8DE8\u8D44\u4EA7\u65E5\u6DA8\u8DCC", unit: "%", prefix: "cross_asset.", ids: [/\.change_percent$/] }
    ];
    return definitions.map(({ title, unit, prefix, ids, kind }) => {
      const rows = summary.rows.filter((row) => row.id.startsWith(prefix) && ids.some((pattern) => pattern.test(row.id)) && row.observationDate === summary.date && row.quality !== "lagged");
      const maximum = Math.max(...rows.map((row) => Math.abs(row.value)), 0);
      return {
        title,
        unit,
        prefix,
        kind,
        rows: rows.map((row) => ({
          ...row,
          side: kind === "level" ? "level" : row.value < 0 ? "negative" : "positive",
          width: maximum ? Math.abs(row.value) / maximum * 100 : 0,
          valueText: kind === "level" ? `${row.value.toFixed(2)}%` : `${row.value >= 0 ? "+" : ""}${row.value.toFixed(2)}${unit === "%" ? "%" : " bp"}`
        }))
      };
    }).filter((chart) => chart.rows.length);
  }
  function escapeSvgText(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&apos;"
    })[character] ?? "");
  }
  function wrapSvgText(value, width = 52) {
    const tokens = String(value).replace(/\s+/g, " ").trim().match(/[A-Za-z][A-Za-z0-9./%+_-]*|[+-]?\d[\d,.%/-]*|./gu) ?? [];
    const lines = [];
    let line = "";
    for (const token of tokens) {
      if (token.length > width) {
        if (line) lines.push(line.trim());
        for (let start = 0; start < token.length; start += width) lines.push(token.slice(start, start + width));
        line = "";
        continue;
      }
      if (line.length + token.length > width && line) {
        lines.push(line.trim());
        line = "";
      }
      line += token;
    }
    if (line) lines.push(line.trim());
    return lines;
  }
  function buildMarketDailyChartSvg(summary) {
    const font = "'Source Han Sans CN', 'Noto Sans CJK SC', 'Noto Sans SC', 'PingFang SC', sans-serif";
    const charts = buildMarketDailyCharts(summary);
    const laggedRates = summary.rateRows.filter((row) => row.observationDate !== summary.date);
    if (!charts.length && !laggedRates.length && !summary.secondaryRows.length && !summary.claims.length) return null;
    let y = 118;
    const parts = [
      `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="__HEIGHT__" viewBox="0 0 960 __HEIGHT__" role="img">`,
      `<title>${escapeSvgText(summary.date)} \u7F8E\u4E1C\u4EA4\u6613\u65E5\u5E02\u573A\u56FE\u6587\u590D\u76D8</title>`,
      `<desc>\u5C55\u793A\u5DF2\u6838\u5B9E\u7684\u884C\u60C5\u56FE\u89E3\u3001\u5E02\u573A\u89E3\u8BFB\u3001\u7ECF\u6D4E\u6570\u636E\u548C\u5173\u952E\u6765\u6E90\u3002</desc>`,
      `<rect width="960" height="__HEIGHT__" fill="#fff9f2"/>`,
      `<text x="54" y="62" fill="#34271f" font-family="sans-serif" font-size="28" font-weight="700">${escapeSvgText(summary.date)} \u7F8E\u4E1C\u4EA4\u6613\u65E5</text>`,
      `<text x="54" y="91" fill="#715f52" font-family="sans-serif" font-size="15">\u7F8E\u80A1\u6536\u76D8\u590D\u76D8${summary.historicalBackfill ? " \xB7 \u4E8B\u540E\u6574\u7406" : ""} \xB7 \u56FE\u89E3\u3001\u89E3\u8BFB\u4E0E\u6765\u6E90</text>`
    ];
    for (const chart of charts) {
      parts.push(`<text x="54" y="${y}" fill="#34271f" font-family="sans-serif" font-size="19" font-weight="700">${escapeSvgText(chart.title)}\uFF08${escapeSvgText(chart.unit)}\uFF09</text>`);
      y += 34;
      for (const row of chart.rows) {
        const equity = summary.equityRows.find((item) => row.id === `equity.${item.symbol.toLowerCase()}.change_percent`);
        const asset = summary.crossAssetRows.find((item) => row.id === `cross_asset.${item.name}.change_percent`);
        const assetUnit = asset && { "USD/barrel": "\u7F8E\u5143/\u6876", "USD/troy_ounce": "\u7F8E\u5143/\u91D1\u8861\u76CE\u53F8", "USD/bitcoin": "\u7F8E\u5143/BTC" }[asset.priceUnit];
        const close = equity ? `\u6536\u76D8 ${equity.priceValue.toFixed(2)} \u7F8E\u5143` : asset ? `\u6536\u76D8 ${asset.priceValue.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${assetUnit || asset.priceUnit}` : "";
        const center = chart.kind === "level" ? 350 : 565;
        const width = Math.round(row.width * (chart.kind === "level" ? 4.3 : 2.15));
        const barX = row.side === "negative" ? center - width : center;
        const color = row.side === "negative" ? "#5c7182" : "#b64d33";
        parts.push(`<text x="54" y="${y + 5}" fill="#34271f" font-family="sans-serif" font-size="16" font-weight="600">${escapeSvgText(row.label)}</text>`);
        parts.push(`<rect x="350" y="${y - 13}" width="430" height="18" rx="3" fill="#f2e7dc"/>`);
        parts.push(`<rect x="${barX}" y="${y - 11}" width="${width}" height="14" rx="2" fill="${color}"/>`);
        parts.push(`<line x1="${center}" y1="${y - 16}" x2="${center}" y2="${y + 8}" stroke="#5d4c40" stroke-width="1"/>`);
        parts.push(`<text x="800" y="${y + 5}" fill="#34271f" font-family="monospace" font-size="16" font-weight="700">${escapeSvgText(row.valueText)}</text>`);
        parts.push(`<text x="54" y="${y + 25}" fill="#715f52" font-family="sans-serif" font-size="12">\u89C2\u6D4B\u65E5 ${escapeSvgText(row.observationDate)}${close ? ` \xB7 ${escapeSvgText(close)}` : ""} \xB7 ${escapeSvgText(row.sourceLabel)}</text>`);
        y += 58;
      }
      y += 20;
    }
    if (laggedRates.length) {
      parts.push(`<text x="54" y="${y}" fill="#34271f" font-family="sans-serif" font-size="19" font-weight="700">\u7F8E\u503A\u8F83\u65E9\u89C2\u6D4B\u503C</text>`);
      y += 30;
      for (const row of laggedRates) {
        const level = row.levelValue === null ? "\u6536\u76CA\u7387\u6682\u7F3A" : `${row.levelValue.toFixed(2)}%`;
        const change = row.changeValue === null ? "\u65E5\u53D8\u52A8\u6682\u7F3A" : `${row.changeValue >= 0 ? "+" : ""}${row.changeValue.toFixed(2)} bp`;
        parts.push(`<text x="54" y="${y}" fill="#715f52" font-family="sans-serif" font-size="14">${escapeSvgText(row.label)}\uFF1A${escapeSvgText(level)} \xB7 ${escapeSvgText(change)} \xB7 \u89C2\u6D4B\u65E5 ${escapeSvgText(row.observationDate)}\uFF0C\u975E\u62A5\u544A\u65E5</text>`);
        y += 27;
      }
      y += 12;
    }
    const addSection = (title, paragraphs) => {
      if (!paragraphs.length) return;
      y += 15;
      parts.push(`<text x="54" y="${y}" fill="#34271f" font-family="sans-serif" font-size="20" font-weight="700">${escapeSvgText(title)}</text>`);
      y += 32;
      for (const paragraph of paragraphs) {
        for (const line of wrapSvgText(paragraph)) {
          parts.push(`<text x="54" y="${y}" fill="#34271f" font-family="sans-serif" font-size="15">${escapeSvgText(line)}</text>`);
          y += 23;
        }
        y += 9;
      }
    };
    for (const section of summary.claimSections) {
      addSection(section.title, section.claims.map((claim) => `${claim.text}\uFF08${[...new Set(claim.sourceUrls.map((url) => new URL(url).hostname))].join("\u3001")}\uFF09`));
    }
    addSection("\u7ECF\u6D4E\u6570\u636E", summary.secondaryRows.map((row) => `${row.text} \xB7 \u89C2\u6D4B\u65E5 ${row.observationDate} \xB7 ${row.sourceLabel}`));
    addSection("\u6570\u636E\u72B6\u6001", [summary.historicalBackfill ? "\u5386\u53F2\u8865\u62A5\uFF1A\u4E8B\u540E\u6574\u7406\uFF0C\u5E76\u975E\u62A5\u544A\u65E5\u5F53\u5929\u53D1\u5E03\u3002" : "\u5F53\u65E5\u516C\u5F00\u590D\u76D8\u3002", ...summary.gaps.map((gap) => `\u5C1A\u7F3A\uFF1A${gap}`)]);
    const urls = [.../* @__PURE__ */ new Set([...summary.rows.map((row) => row.sourceUrl), ...summary.claims.flatMap((claim) => claim.sourceUrls)])];
    const domains = [...new Set(urls.map((url) => new URL(url).hostname))];
    addSection("\u5173\u952E\u6765\u6E90", [...domains.map((domain) => `\xB7 ${domain}`), "\u5B8C\u6574\u6765\u6E90\u94FE\u63A5\u89C1\u7F51\u9875\u62A5\u544A\u3002"]);
    const height = y + 55;
    parts.push(`<line x1="54" y1="${height - 48}" x2="906" y2="${height - 48}" stroke="#d9c7b6"/>`);
    parts.push(`<text x="54" y="${height - 22}" fill="#715f52" font-family="sans-serif" font-size="12">\u5E02\u573A\u6709\u98CE\u9669\uFF0C\u6295\u8D44\u9700\u8C28\u614E\u3002</text>`);
    parts.push("</svg>");
    return parts.join("").replaceAll("__HEIGHT__", String(height)).replaceAll('font-family="sans-serif"', `font-family="${font}"`).replaceAll('font-family="monospace"', `font-family="${font}" font-variant-numeric="tabular-nums"`);
  }
  function formatMarketDailyStatus(summary) {
    return `${summary.date} \u7F8E\u4E1C\u62A5\u544A\u65E5 \xB7 \u9010\u9879\u663E\u793A\u539F\u59CB\u89C2\u6D4B\u65E5\u3002` + (summary.historicalBackfill ? " \u4E8B\u540E\u6574\u7406\u3002" : "") + (summary.nextMorningRevision ? " \u6B21\u65E5\u6838\u5B9E\u66F4\u65B0\u3002" : "") + (summary.gaps.length ? ` \u5C1A\u7F3A\uFF1A${summary.gaps.join("\u3001")}\u3002` : "");
  }
  var market_daily_utils_default = { summarizeMarketDaily, formatMarketDailyStatus, buildMarketDailyCharts, buildMarketDailyChartSvg };
  return __toCommonJS(market_daily_utils_exports);
})();
