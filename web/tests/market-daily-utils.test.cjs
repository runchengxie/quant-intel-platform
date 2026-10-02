const test = require("node:test");
const assert = require("node:assert/strict");
const { summarizeMarketDaily, formatMarketDailyStatus, buildMarketDailyCharts, buildMarketDailyChartSvg } = require("../src/lib/market-daily-utils.ts");
const { toEnglishPresentation } = require("../src/lib/english-content.ts");

test("reviewed company news is translated as a complete paragraph before SVG wrapping", () => {
  const payload = { schema_version: '1.0', run_id: 'daily-2026-10-01',
    facts: [{ id: 'macro.cpi_yoy', value: 3.4, unit: 'percent', quality: 'ok', observation_date: '2026-08-01', source_url: 'https://fred.stlouisfed.org/series/CPIAUCSL' }],
    events: [{ id: 'reviewed.1' }], sections: [{ key: 'company_news', claims: ['reviewed.1'] }],
    claims: [{ claim: '埃森哲10月1日提交的财报披露，季度收入为186.8亿美元，同比增长6%；下一季度收入指引为177.5亿至184亿美元。公司预计2027财年以当地货币计的收入增长为3%至6%。这些是公司披露和指引，不构成对股价表现的判断。', evidence_ids: ['reviewed.1'], sources: ['https://www.sec.gov/Archives/edgar/data/1467373/announcement.htm'] }],
  };
  const summary = summarizeMarketDaily(payload);
  const svg = buildMarketDailyChartSvg(summary, toEnglishPresentation, 'en-US');
  const text = [...svg.matchAll(/<text\b[^>]*>(.*?)<\/text>/g)].map((match) => match[1]).join(' ');
  assert.match(text, /Accenture/);
  assert.match(text, /USD 18\.68 billion/);
  assert.match(text, /USD 17\.75/);
  assert.match(text, /18\.4 billion/);
  assert.doesNotMatch(text, /埃森哲|亿美元|CNY/);
  assert.match(text, /fiscal 2027/);
  assert.match(text, /3% to 6%/);
});

test('unknown or extended research claims retain their complete source language', () => {
  const known = '埃森哲10月1日提交的财报披露，季度收入为186.8亿美元，同比增长6%；下一季度收入指引为177.5亿至184亿美元。公司预计2027财年以当地货币计的收入增长为3%至6%。这些是公司披露和指引，不构成对股价表现的判断。';
  for (const claim of ['新公司收入为12.41亿元。', `${known}公司补充信息仍待确认。`]) {
    const summary = summarizeMarketDaily({ schema_version: '1.0', run_id: 'daily-2026-10-01',
      facts: [{ id: 'macro.cpi_yoy', value: 3.4, unit: 'percent', quality: 'ok', observation_date: '2026-08-01', source_url: 'https://fred.stlouisfed.org/series/CPIAUCSL' }],
      events: [{ id: 'reviewed.1' }], sections: [{ key: 'company_news', claims: ['reviewed.1'] }],
      claims: [{ claim, evidence_ids: ['reviewed.1'], sources: ['https://www.sec.gov/Archives/edgar/data/1467373/announcement.htm'] }],
    });
    const svg = buildMarketDailyChartSvg(summary, toEnglishPresentation, 'en-US');
    const text = [...svg.matchAll(/<text\b[^>]*>(.*?)<\/text>/g)].map((match) => match[1]).join('');
    assert.ok(text.includes(claim), 'Unmatched claims must not be partially translated, even at wrapped line boundaries');
    assert.doesNotMatch(text, /Accenture|CNY/);
  }
});

test("asset-specific gap labels remain readable in the English report", () => {
  assert.equal(toEnglishPresentation("尚缺：比特币期货行情"), "Missing: Bitcoin futures prices");
  assert.equal(toEnglishPresentation("尚缺：部分跨资产行情"), "Missing: some cross-asset prices");
});

test("optional CME futures are disclosed separately from required spot coverage", () => {
  const futures = [["brent", "BZ%3DF", "USD/barrel"], ["gold", "GC%3DF", "USD/troy_ounce"], ["silver", "SI%3DF", "USD/troy_ounce"]].flatMap(([asset, ticker, unit]) => [
    { id: `cross_asset.${asset}.close`, metric: "commodity_close", value: 100, unit },
    { id: `cross_asset.${asset}.change_percent`, metric: "daily_return", value: 1, unit: "percent" },
  ].map((fact) => ({ ...fact, source: "Yahoo Finance", source_url: `https://finance.yahoo.com/quote/${ticker}/history/`, quality: "ok", observation_date: "2026-09-24" })));
  const spot = [
    { id: "cross_asset.bitcoin_spot.close", metric: "crypto_spot_close", value: 83000, unit: "USD/bitcoin" },
    { id: "cross_asset.bitcoin_spot.change_percent", metric: "daily_return", value: 1, unit: "percent" },
  ].map((fact) => ({ ...fact, source: "Financial Modeling Prep", source_url: "https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full", instrument: "BTC/USD cryptocurrency EOD (FMP BTCUSD)", quality: "ok", observation_date: "2026-09-24" }));
  const payload = { schema_version: "1.0", run_id: "daily-2026-09-24", missing_sources: ["research", "cross_asset"], source_status: { cross_asset: { reason: "optional_futures_unavailable" } }, facts: [...futures, ...spot] };
  const summary = summarizeMarketDaily(payload);
  assert.ok(summary);
  assert.deepEqual(summary.gaps, ["研究解释"]);
  assert.deepEqual(summary.optionalGaps, ["比特币期货行情"]);
  assert.equal(summary.crossAssetRows.length, 4);
  const svg = buildMarketDailyChartSvg(summary);
  assert.match(svg, /可选数据未提供：比特币期货行情/);
  assert.doesNotMatch(svg, /尚缺：比特币期货行情/);
  assert.match(toEnglishPresentation(svg), /Optional data unavailable: Bitcoin futures prices/);
  assert.doesNotMatch(toEnglishPresentation(svg), /可选数据|未提供/);
  assert.doesNotMatch(svg, /尚缺：布伦特、金银或比特币行情/);
  const uncertain = summarizeMarketDaily({ ...payload, source_status: {} });
  assert.deepEqual(uncertain.gaps, ["研究解释", "部分跨资产行情"]);
  const fs = require("node:fs");
  const vm = require("node:vm");
  const legacyPath = require("node:path").join(__dirname, "../src/lib/market-daily-utils.js");
  const legacy = vm.runInNewContext(fs.readFileSync(legacyPath, "utf8") + ";marketDailyUtils", { URL });
  assert.equal(JSON.stringify(legacy.summarizeMarketDaily(payload).optionalGaps), JSON.stringify(summary.optionalGaps));
});

test("missing required BTC spot is not satisfied by a CME futures pair", () => {
  const facts = [
    { id: "cross_asset.bitcoin.close", metric: "crypto_futures_close", value: 83000, unit: "USD/bitcoin" },
    { id: "cross_asset.bitcoin.change_percent", metric: "daily_return", value: 1, unit: "percent" },
  ].map((fact) => ({ ...fact, source: "Yahoo Finance", source_url: "https://finance.yahoo.com/quote/BTC%3DF/history/", quality: "ok", observation_date: "2026-09-24" }));
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-24", missing_sources: [], facts });
  assert.ok(summary);
  assert.deepEqual(summary.gaps, ["比特币现货行情"]);
  assert.deepEqual(summary.optionalGaps, []);
  assert.match(buildMarketDailyChartSvg(summary), /尚缺：比特币现货行情/);
});

test("market daily keeps the observation date and lagged yield state", () => {
  const summary = summarizeMarketDaily({
    schema_version: "1.0",
    run_id: "daily-2026-09-23",
    quality_summary: { status: "degraded" },
    missing_sources: ["rates_lag", "quotes"],
    facts: [
      { id: "treasury.10y.change_bp", metric: "yield_change", value: -5, unit: "basis_points", quality: "lagged", observation_date: "2026-09-22", source_url: "https://fred.stlouisfed.org/series/DGS10" },
      { id: "macro.cpi_yoy", value: 3.4, quality: "ok", observation_date: "2026-08-01", source_url: "https://fred.stlouisfed.org/series/CPIAUCNS" },
    ],
  });

  assert.equal(summary.date, "2026-09-23");
  assert.equal(summary.rows[0].text, "10 年期美债收益率日变动 -5.00 bp");
  assert.equal(summary.rows[0].observationDate, "2026-09-22");
  assert.equal(summary.rows[0].quality, "lagged");
  assert.equal(summary.rows[1].text, "CPI 同比 3.40%");
  assert.deepEqual(summary.gaps, ["美债收益率当日变动", "指数行情"]);
  assert.equal(summary.hasTextReport, false);
});

test("same-day Treasury facts must be accepted quality before appearing in a chart", () => {
  for (const quality of ["rejected", "lagged"]) {
    const summary = summarizeMarketDaily({
      schema_version: "1.0", run_id: "daily-2026-09-24", facts: [
        { id: "treasury.2y.change_bp", metric: "yield_change", value: 10, unit: "basis_points", quality,
          observation_date: "2026-09-24", source_url: "https://fred.stlouisfed.org/series/DGS2" },
      ],
    });
    assert.equal(summary, null);
  }
});

test("a verified same-day Treasury level alone still produces a sourced image", () => {
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-24", facts: [
      { id: "treasury.2y.level_percent", metric: "yield_level", value: 4.25, unit: "percent", quality: "ok",
        observation_date: "2026-09-24", source_url: "https://fred.stlouisfed.org/series/DGS2" },
    ],
  });
  assert.ok(summary);
  const svg = buildMarketDailyChartSvg(summary);
  assert.match(svg, /fill="var\(--report-bg/);
  assert.match(svg, /fill="var\(--report-ink/);
  assert.match(svg, /4\.25%/);
  assert.match(svg, /2026-09-24/);
  assert.match(svg, /FRED/);
});

test("Treasury yield levels have their own four-tenor percent chart", () => {
  const source_url = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve";
  const facts = [["2y", 4.81], ["5y", 4.98], ["10y", 5.17], ["30y", 5.49]].map(([tenor, value]) => ({
    id: `treasury.${tenor}.level_percent`, metric: "yield_level", value, unit: "percent",
    quality: "ok", observation_date: "2026-09-25", source_url,
  }));
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-25", facts });
  const chart = buildMarketDailyCharts(summary).find((item) => item.title === "美债收益率水平");
  assert.ok(chart);
  assert.equal(chart.unit, "%");
  assert.deepEqual(chart.rows.map((row) => [row.label, row.valueText]), [
    ["2 年期美债收益率水平", "4.81%"], ["5 年期美债收益率水平", "4.98%"],
    ["10 年期美债收益率水平", "5.17%"], ["30 年期美债收益率水平", "5.49%"],
  ]);
  const svg = buildMarketDailyChartSvg(summary);
  assert.match(svg, /美债收益率水平（%）/);
  assert.match(svg, /观测日 2026-09-25/);
  assert.match(svg, /美国财政部|home\.treasury\.gov/);
  assert.doesNotMatch(svg, /\+4\.81%/);
});

test("report image combines charts with verified report prose", () => {
  const treasuryUrl = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve";
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-25", facts: [
    { id: "index.spx.change_percent", value: 0.51, quality: "reviewed", observation_date: "2026-09-25", source_url: "https://example.test/close" },
    { id: "treasury.2y.level_percent", metric: "yield_level", value: 4.81, unit: "percent", quality: "ok", observation_date: "2026-09-25", source_url: treasuryUrl },
    { id: "treasury.2y.change_bp", metric: "yield_change", value: -6, unit: "basis_points", quality: "ok", observation_date: "2026-09-25", source_url: treasuryUrl },
    { id: "cross_asset.brent.close", metric: "commodity_close", value: 104.32, unit: "USD/barrel", quality: "ok", source: "Yahoo Finance", observation_date: "2026-09-25", source_url: "https://finance.yahoo.com/quote/BZ%3DF/history/" },
    { id: "cross_asset.brent.change_percent", metric: "daily_return", value: -2.14, unit: "percent", quality: "ok", source: "Yahoo Finance", observation_date: "2026-09-25", source_url: "https://finance.yahoo.com/quote/BZ%3DF/history/" },
  ], events: [{ id: "reviewed.11" }], claims: [
    { claim: "微软上涨 3.7%，与已公布的新功能有关。", evidence_ids: ["reviewed.11"], sources: ["https://example.test/stock"] },
  ], sections: [{ key: "movers", claims: ["reviewed.11"] }] });
  const svg = buildMarketDailyChartSvg(summary);
  assert.ok(svg.indexOf("四大指数收盘涨跌") < svg.indexOf("美债收益率水平（%）"));
  assert.ok(svg.indexOf("美债收益率水平（%）") < svg.indexOf("美债收益率当日变动（bp）"));
  assert.ok(svg.indexOf("美债收益率当日变动（bp）") < svg.indexOf("跨资产日涨跌（%）"));
  assert.match(svg, /微软上涨 3\.7%/);
});

test("stock narrative is included in the report image", () => {
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-25", facts: [
    { id: "index.spx.change_percent", value: 0.51, quality: "reviewed", observation_date: "2026-09-25", source_url: "https://example.test/close" },
  ], events: [{ id: "reviewed.11" }], claims: [
    { claim: `${"中".repeat(48)}Anthropic`, evidence_ids: ["reviewed.11"], sources: ["https://example.test/stock"] },
  ], sections: [{ key: "movers", claims: ["reviewed.11"] }] });
  assert.match(buildMarketDailyChartSvg(summary), /Anthropic/);
});

test("market narrative is included in the report image", () => {
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-25", facts: [
    { id: "index.spx.change_percent", value: 0.51, quality: "reviewed", observation_date: "2026-09-25", source_url: "https://example.test/close" },
  ], events: [{ id: "reviewed.0" }], claims: [
    { claim: `${"中".repeat(47)}道指上涨 0.93%。`, evidence_ids: ["reviewed.0"], sources: ["https://example.test/close"] },
  ], sections: [{ key: "market", claims: ["reviewed.0"] }] });
  assert.match(buildMarketDailyChartSvg(summary), /0\.93%/);
});

test("image includes stock prices, macro facts, explanations and sources", () => {
  const marketDate = "2026-09-25";
  const facts = [
    { id: "index.spx.change_percent", value: 0.51, quality: "reviewed", observation_date: marketDate, source_url: "https://example.test/close" },
    ...[["close", 200.5, "stock_close", "USD/share"], ["change_percent", 1.25, "daily_return", "percent"]].map(([field, value, metric, unit]) => ({
      id: `equity.msft.${field}`, value, metric, unit, instrument: "MSFT", source: "Yahoo Finance", quality: "ok",
      observation_date: marketDate, source_url: "https://finance.yahoo.com/quote/MSFT/history/",
    })),
    { id: "macro.cpi_yoy", value: 3.4, quality: "ok", observation_date: "2026-08-01", source_url: "https://fred.stlouisfed.org/series/CPIAUCNS" },
  ];
  const sections = ["market", "movers", "drivers", "macro", "company_news"];
  const claims = sections.map((section, index) => ({ claim: `${section} 已核实的完整说明`, evidence_ids: [`reviewed.${index}`], sources: [`https://example.test/${section}`] }));
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: `daily-${marketDate}`, facts,
    events: sections.map((section, index) => ({ id: `reviewed.${index}` })), claims,
    sections: sections.map((section, index) => ({ key: section, claims: [`reviewed.${index}`] })) });
  assert.equal(summary.equityRows[0].symbol, "MSFT");
  const svg = buildMarketDailyChartSvg(summary);
  assert.match(svg, /MSFT/);
  assert.match(svg, /\+1\.25%/);
  assert.match(svg, /200\.50/);
  assert.match(svg, /CPI 同比/);
  for (const section of sections) assert.match(svg, new RegExp(`${section} 已核实的完整说明`));
  assert.match(svg, /example\.test|finance\.yahoo\.com|fred\.stlouisfed\.org|来源/);
});

test("market daily does not accept malformed or impossible stock quote facts", () => {
  const common = { instrument: "MSFT", source: "Yahoo Finance", quality: "ok",
    source_url: "https://finance.yahoo.com/quote/MSFT/history/", observation_date: "2026-09-25" };
  const pair = [
    { ...common, id: "equity.msft.close", metric: "stock_close", unit: "USD/share", value: 200.5 },
    { ...common, id: "equity.msft.change_percent", metric: "daily_return", unit: "percent", value: 1.25 },
  ];
  for (const facts of [
    [...pair, { ...common, id: "equity.msft.foo", value: 1 }],
    [{ ...pair[0], value: -1 }, pair[1]],
    [pair[0], { ...pair[1], value: 999 }],
  ]) assert.equal(summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-25", facts }), null);
  const akam = pair.map((row) => ({ ...row, id: row.id.replace("msft", "akam"), instrument: "AKAM",
    source_url: "https://finance.yahoo.com/quote/AKAM/history/" }));
  assert.equal(summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-25", facts: akam }), null);
});

test("backfill status is not presented as a next-morning verification", () => {
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-25",
    as_of: "2026-09-27T12:00:00+00:00", quality_summary: { revision: "historical_backfill" },
    facts: [{ id: "index.spx.change_percent", value: 0.51, quality: "reviewed", observation_date: "2026-09-25", source_url: "https://example.test/close" }] });
  assert.match(formatMarketDailyStatus(summary), /事后整理/);
  assert.doesNotMatch(formatMarketDailyStatus(summary), /次日核实更新/);
});

test("market daily status calls a report date a report date, including missing sources", () => {
  assert.equal(
    formatMarketDailyStatus({ date: "2026-09-23", gaps: ["指数行情"] }),
    "2026-09-23 美东报告日 · 逐项显示原始观测日。 尚缺：指数行情。",
  );
});

test("market daily hides fixture and invalid source data", () => {
  assert.equal(summarizeMarketDaily({ schema_version: "1.0", quality_summary: { status: "fixture" }, facts: [] }), null);
  assert.equal(summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-23", facts: [{ id: "macro.cpi_yoy", value: "3.4", source_url: "javascript:alert(1)" }] }), null);
  assert.equal(summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-23", facts: [{ id: "index.spx.change_percent", value: 1, quality: "reviewed", observation_date: "2026-09-23", source_url: "https://[bad]/close" }] }), null);
});

test("market daily shows reviewed index returns, Treasury rates and cited explanations", () => {
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-23",
    as_of: "2026-09-24T08:30:00+00:00", quality_summary: { status: "ok", revision: "next_morning_rechecked" },
    report_formats: ["md", "txt"],
    missing_sources: [],
    facts: [
      { id: "index.spx.change_percent", value: -0.8, quality: "reviewed", observation_date: "2026-09-23", source_url: "https://abcnews.com/amp/Business/example" },
      { id: "treasury.10y.change_bp", metric: "yield_change", value: 15, unit: "basis_points", quality: "ok", observation_date: "2026-09-23", source_url: "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve" },
    ],
    events: [{ id: "reviewed.1", source_url: "https://abcnews.com/amp/Business/example" }],
    claims: [{ claim: "美联社认为美债收益率上升带来压力。", evidence_ids: ["reviewed.1"], sources: ["https://abcnews.com/amp/Business/example"] }],
  });
  assert.equal(summary.rows[0].text, "标普 500 日涨跌 -0.80%");
  assert.equal(summary.rows[0].sourceLabel, "核实报道");
  assert.equal(summary.rows[1].text, "10 年期美债收益率日变动 15.00 bp");
  assert.equal(summary.rows[1].sourceLabel, "美国财政部");
  assert.equal(summary.claims[0].text, "美联社认为美债收益率上升带来压力。");
  assert.deepEqual(summary.gaps, []);
  assert.equal(summary.hasTextReport, true);
  assert.match(formatMarketDailyStatus(summary), /次日核实更新/);
});

test("market daily shows a complete same-day Yahoo index set with its source", () => {
  const indices = [
    ["spx", "%5EGSPC", -0.02], ["dow", "%5EDJI", -0.31],
    ["nasdaq", "%5EIXIC", 0.01], ["russell2000", "%5ERUT", 0.42],
  ].map(([key, symbol, value]) => ({
    id: `index.${key}.change_percent`, metric: "daily_return", value,
    unit: "percent", quality: "ok", source: "Yahoo Finance",
    source_url: `https://finance.yahoo.com/quote/${symbol}/history/`,
    observation_date: "2026-09-24",
  }));
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-24", facts: indices,
  });

  assert.equal(summary.rows.length, 4);
  assert.equal(summary.rows[0].sourceLabel, "Yahoo Finance");
  assert.equal(buildMarketDailyCharts(summary)[0].rows.length, 4);
  assert.equal(summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-24", facts: indices.slice(0, 3) }), null);
});

test("market daily accepts same-day Treasury levels and cross-asset futures facts only", () => {
  const treasuryUrl = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve";
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-24", as_of: "2026-09-25T11:00:00Z",
    quality_summary: { status: "ok" }, missing_sources: [], facts: [
      { id: "treasury.2y.level_percent", metric: "yield_level", value: 4.1, unit: "percent", quality: "ok", observation_date: "2026-09-24", source_url: treasuryUrl },
      { id: "treasury.2y.change_bp", metric: "yield_change", value: 5, unit: "basis_points", quality: "ok", observation_date: "2026-09-24", source_url: treasuryUrl },
      { id: "treasury.10y.level_percent", metric: "yield_level", value: 4.2, unit: "percent", quality: "ok", observation_date: "2026-09-24", source_url: treasuryUrl },
      { id: "treasury.10y.change_bp", metric: "yield_change", value: 7, unit: "basis_points", quality: "ok", observation_date: "2026-09-24", source_url: treasuryUrl },
      ...[["brent", "BZ%3DF", "USD/barrel", 71], ["gold", "GC%3DF", "USD/troy_ounce", 3900], ["silver", "SI%3DF", "USD/troy_ounce", 47], ["bitcoin", "BTC%3DF", "USD/bitcoin", 108000]].flatMap(([name, ticker, unit, price]) => [
        { id: `cross_asset.${name}.close`, metric: name === "bitcoin" ? "crypto_futures_close" : "commodity_close", value: price, unit, quality: "ok", source: "Yahoo Finance", observation_date: "2026-09-24", source_url: `https://finance.yahoo.com/quote/${ticker}/history/` },
        { id: `cross_asset.${name}.change_percent`, metric: "daily_return", value: 1.2, unit: "percent", quality: "ok", source: "Yahoo Finance", observation_date: "2026-09-24", source_url: `https://finance.yahoo.com/quote/${ticker}/history/` },
      ]),
    ],
  });

  assert.ok(summary);
  assert.equal(summary.rateRows.length, 2);
  assert.equal(summary.rateRows[1].levelValue, 4.2);
  assert.equal(summary.crossAssetRows.length, 4);
  assert.deepEqual(summary.crossAssetRows.map((row) => row.name), ["brent", "gold", "silver", "bitcoin"]);
  assert.equal(summary.crossAssetRows[3].priceValue, 108000);
  assert.equal(summary.rows.some((row) => row.id === "cross_asset.brent.close"), true);
  const svg = buildMarketDailyChartSvg(summary);
  assert.match(svg, /美债收益率水平（%）/);
  assert.match(svg, /美债收益率当日变动（bp）/);
  assert.match(svg, /4\.20%/);
  assert.match(svg, /布伦特/);
  assert.match(svg, /黄金/);
  assert.match(svg, /比特币期货/);
  assert.doesNotMatch(svg, /71\.00 美元\/桶|3,900\.00 美元\/金衡盎司|108,000\.00 美元\/BTC/);
});

test("market daily charts preserve FMP commodity provenance", () => {
  const fmpUrl = "https://site.financialmodelingprep.com/developer/docs/stable/commodities-historical-price-eod-full";
  const pair = [
    { id: "cross_asset.brent.close", metric: "commodity_close", value: 71.25, unit: "USD/barrel" },
    { id: "cross_asset.brent.change_percent", metric: "daily_return", value: 1.2, unit: "percent" },
  ].map((row) => ({ ...row, instrument: "Brent (FMP BZUSD, continuous)", source: "Financial Modeling Prep",
    source_url: fmpUrl, quality: "ok", observation_date: "2026-09-24" }));
  const payload = { schema_version: "1.0", run_id: "daily-2026-09-24", facts: pair };
  const summary = summarizeMarketDaily(payload);

  assert.ok(summary);
  assert.equal(summary.crossAssetRows[0].sourceLabel, "FMP");
  assert.match(buildMarketDailyChartSvg(summary), /FMP/);
  assert.equal(summarizeMarketDaily({ ...payload, facts: pair.map((row) => ({ ...row, instrument: "Brent (FMP GCUSD, continuous)" })) }), null);
});

test("dated commodity contracts keep the US report chart visible", () => {
  const specs = [
    ["brent", "BZX26.NYM", "USD/barrel", 104.32],
    ["gold", "GCZ26.CMX", "USD/troy_ounce", 4321.2],
    ["silver", "SIZ26.CMX", "USD/troy_ounce", 64.801],
  ];
  const facts = specs.flatMap(([asset, ticker, unit, price]) => [
    { id: `cross_asset.${asset}.close`, metric: "commodity_close", value: price, unit },
    { id: `cross_asset.${asset}.change_percent`, metric: "daily_return", value: 1.2, unit: "percent" },
  ].map((fact) => ({ ...fact, instrument: `${asset} (${ticker})`, source: "Yahoo Finance",
    source_url: `https://finance.yahoo.com/quote/${ticker}/history/`, quality: "ok", observation_date: "2026-09-25" })));
  const payload = { schema_version: "1.0", run_id: "daily-2026-09-25", facts };
  const summary = summarizeMarketDaily(payload);
  assert.ok(summary);
  assert.equal(summary.crossAssetRows.length, 3);
  assert.match(buildMarketDailyChartSvg(summary), /跨资产日涨跌/);
  const wrongMonth = facts.map((fact) => fact.id.startsWith("cross_asset.brent.")
    ? { ...fact, instrument: "brent (BZZ26.NYM)", source_url: "https://finance.yahoo.com/quote/BZZ26.NYM/history/" } : fact);
  assert.equal(summarizeMarketDaily({ ...payload, facts: wrongMonth }), null);
});

test("BTC/USD spot is shown separately from CME bitcoin futures", () => {
  const fmpUrl = "https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full";
  const fmp = { source: "Financial Modeling Prep", source_url: fmpUrl,
    instrument: "BTC/USD cryptocurrency EOD (FMP BTCUSD)", quality: "ok", observation_date: "2026-09-24" };
  const yahoo = { source: "Yahoo Finance", source_url: "https://finance.yahoo.com/quote/BTC%3DF/history/",
    instrument: "CME Bitcoin continuous futures (BTC=F)", quality: "ok", observation_date: "2026-09-24" };
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-24", facts: [
    { ...yahoo, id: "cross_asset.bitcoin.close", metric: "crypto_futures_close", value: 83500, unit: "USD/bitcoin" },
    { ...yahoo, id: "cross_asset.bitcoin.change_percent", metric: "daily_return", value: -0.8, unit: "percent" },
    { ...fmp, id: "cross_asset.bitcoin_spot.close", metric: "crypto_spot_close", value: 84093.13, unit: "USD/bitcoin" },
    { ...fmp, id: "cross_asset.bitcoin_spot.change_percent", metric: "daily_return", value: -0.35, unit: "percent" },
  ] });

  assert.ok(summary);
  assert.deepEqual(summary.crossAssetRows.map((row) => row.name), ["bitcoin", "bitcoin_spot"]);
  assert.equal(summary.crossAssetRows[1].sourceLabel, "FMP");
  assert.match(buildMarketDailyChartSvg(summary), /BTC\/USD 现货/);
});

test("authorized BTC/USD spot fallbacks retain their own attribution", () => {
  for (const [source, sourceUrl, instrument] of [
    ["Data provided by CoinGecko", "https://www.coingecko.com/en/api", "BTC/USD spot at 16:00 ET (CoinGecko bitcoin/USD)"],
    ["Kraken", "https://www.kraken.com/prices/bitcoin", "BTC/USD spot at 16:00 ET (Kraken XBT/USD)"],
  ]) {
    const pair = [
      { id: "cross_asset.bitcoin_spot.close", metric: "crypto_spot_close", value: 84012.8, unit: "USD/bitcoin" },
      { id: "cross_asset.bitcoin_spot.change_percent", metric: "daily_return", value: -0.43, unit: "percent" },
    ].map((fact) => ({ ...fact, source, source_url: sourceUrl, instrument, quality: "ok", observation_date: "2026-09-24" }));
    const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-24", facts: pair });
    assert.ok(summary);
    assert.equal(summary.crossAssetRows[0].sourceLabel, source);
    assert.equal(summary.crossAssetRows[0].sourceUrl, sourceUrl);
    assert.match(buildMarketDailyChartSvg(summary), /跨资产日涨跌/);
    assert.doesNotMatch(buildMarketDailyChartSvg(summary), /跨资产期货价格/);
    assert.equal(summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-24", facts: pair.map((fact) => ({ ...fact, source: "Yahoo Finance" })) }), null);
  }
});

test("BTC/USD spot rejects a price and return from different providers", () => {
  const shared = { quality: "ok", observation_date: "2026-09-24" };
  const facts = [
    { ...shared, id: "cross_asset.bitcoin_spot.close", metric: "crypto_spot_close", value: 84012.8, unit: "USD/bitcoin", source: "Data provided by CoinGecko", source_url: "https://www.coingecko.com/en/api", instrument: "BTC/USD spot at 16:00 ET (CoinGecko bitcoin/USD)" },
    { ...shared, id: "cross_asset.bitcoin_spot.change_percent", metric: "daily_return", value: -0.43, unit: "percent", source: "Kraken", source_url: "https://www.kraken.com/prices/bitcoin", instrument: "BTC/USD spot at 16:00 ET (Kraken XBT/USD)" },
  ];
  assert.equal(summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-24", facts }), null);
});

test("market daily rejects cross-asset facts with mismatched dates, units or sources", () => {
  for (const override of [
    { observation_date: "2026-09-23" },
    { unit: "USD/contract" },
    { source_url: "https://example.test/price" },
  ]) {
    const summary = summarizeMarketDaily({
      schema_version: "1.0", run_id: "daily-2026-09-24", facts: [
        { id: "cross_asset.bitcoin.close", metric: "crypto_futures_close", value: 108000, unit: "USD/bitcoin", quality: "ok", observation_date: "2026-09-24", source_url: "https://finance.yahoo.com/quote/BTC%3DF/history/", ...override },
      ],
    });
    assert.equal(summary, null);
  }
});

test("market daily caps visible driver and mover claims at three each", () => {
  const drivers = [1, 2, 3, 4].map((number) => `driver.${number}`);
  const movers = [1, 2, 3, 4].map((number) => `mover.${number}`);
  const ids = [...drivers, ...movers];
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-24",
    facts: [
      { id: "index.spx.change_percent", value: 0.2, unit: "percent", quality: "reviewed", observation_date: "2026-09-24", source_url: "https://example.com/close" },
      ...ids.map((id) => ({ id })),
    ],
    claims: ids.map((id) => ({ claim: id, evidence_ids: [id], sources: ["https://example.com/evidence"] })),
    sections: [
      { key: "drivers", claims: drivers },
      { key: "movers", claims: movers },
      { key: "company_news", claims: ["company.1"] },
    ],
  });

  assert.deepEqual(summary.primaryClaims.map((section) => [section.key, section.claims.length]), [
    ["drivers", 3], ["movers", 3],
  ]);
});

test("market daily groups reviewed explanations and company news by evidence section", () => {
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-23", facts: [
      { id: "index.spx.change_percent", value: -0.8, quality: "reviewed", observation_date: "2026-09-23", source_url: "https://example.test/close" },
    ],
    events: [{ id: "reviewed.1" }, { id: "reviewed.2" }],
    claims: [
      { claim: "收益率影响市场", evidence_ids: ["reviewed.1"], sources: ["https://example.test/close"] },
      { claim: "公司发布业绩", evidence_ids: ["reviewed.2"], sources: ["https://example.test/company"] },
    ],
    sections: [
      { key: "drivers", title: "市场驱动因素", claims: ["reviewed.1"] },
      { key: "company_news", title: "公司新闻", claims: ["reviewed.2"] },
    ],
  });
  assert.deepEqual(summary.claimSections.map((section) => [section.key, section.claims.map((claim) => claim.text)]), [
    ["drivers", ["收益率影响市场"]], ["company_news", ["公司发布业绩"]],
  ]);
});

test("market daily charts keep signed values and source dates in separate units", () => {
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-23", facts: [
      { id: "index.spx.change_percent", value: -0.8, quality: "reviewed", observation_date: "2026-09-23", source_url: "https://abcnews.com/amp/Business/example" },
      { id: "index.dow.change_percent", value: 0.4, quality: "reviewed", observation_date: "2026-09-23", source_url: "https://abcnews.com/amp/Business/example" },
      { id: "treasury.2y.change_bp", metric: "yield_change", value: 14, unit: "basis_points", quality: "ok", observation_date: "2026-09-23", source_url: "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve" },
      { id: "treasury.10y.change_bp", metric: "yield_change", value: 15, unit: "basis_points", quality: "ok", observation_date: "2026-09-23", source_url: "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve" },
    ],
  });
  const charts = buildMarketDailyCharts(summary);
  assert.deepEqual(charts.map((chart) => [chart.title, chart.unit, chart.rows.length]), [
    ["四大指数收盘涨跌", "%", 2], ["美债收益率当日变动", "bp", 2],
  ]);
  assert.deepEqual(charts[0].rows.map((row) => [row.valueText, row.side, row.width]), [
    ["-0.80%", "negative", 100], ["+0.40%", "positive", 50],
  ]);
  assert.deepEqual(charts[1].rows.map((row) => row.label), ["2 年期美债", "10 年期美债"]);
  assert.equal(charts[1].rows[0].valueText, "+14.00 bp");
  assert.equal(charts[1].rows[0].observationDate, "2026-09-23");
  assert.match(charts[1].rows[0].sourceUrl, /^https:\/\/home\.treasury\.gov\//);
});

test("report image retains dates, units and source references", () => {
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-23", facts: [
      { id: "index.spx.change_percent", value: -0.8, quality: "reviewed", observation_date: "2026-09-23", source_url: "https://abcnews.com/Business/close" },
      { id: "index.dow.change_percent", value: 0.4, quality: "reviewed", observation_date: "2026-09-23", source_url: "https://abcnews.com/Business/close" },
      { id: "treasury.10y.change_bp", metric: "yield_change", value: 15, unit: "basis_points", quality: "ok", observation_date: "2026-09-23", source_url: "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202609?_format=csv&field_tdr_date_value_month=202609&page=&type=daily_treasury_yield_curve" },
      { id: "treasury.2y.change_bp", metric: "yield_change", value: 14, unit: "basis_points", quality: "lagged", observation_date: "2026-09-22", source_url: "https://fred.stlouisfed.org/series/DGS2" },
    ],
  });
  const svg = buildMarketDailyChartSvg?.(summary) ?? "";
  assert.match(svg, /<svg[^>]*width="960"/);
  assert.match(svg, /2026-09-23 美东交易日/);
  assert.match(svg, /标普 500/);
  assert.match(svg, /-0\.80%/);
  assert.match(svg, /\+0\.40%/);
  assert.match(svg, /\+15\.00 bp/);
  assert.match(svg, /观测日 2026-09-23/);
  assert.match(svg, /abcnews\.com|home\.treasury\.gov|来源/);
  assert.match(svg, /2026-09-22，非报告日/);
  assert.doesNotMatch(svg, /FRED 原始数据|<script>/);
});

test("chart image can show only lagged Treasury readings without invented bars", () => {
  const summary = summarizeMarketDaily({
    schema_version: "1.0", run_id: "daily-2026-09-23", facts: [
      { id: "treasury.10y.change_bp", metric: "yield_change", value: 15, unit: "basis_points", quality: "lagged", observation_date: "2026-09-22", source_url: "https://fred.stlouisfed.org/series/DGS10" },
    ],
  });
  const svg = buildMarketDailyChartSvg(summary);
  assert.match(svg, /10 年期美债：收益率暂缺 · \+15\.00 bp/);
  assert.match(svg, /观测日 2026-09-22，非报告日/);
  assert.doesNotMatch(svg, /美债收益率当日变动（bp）/);
});

test("image discloses lagged Treasury readings without plotting them as same-day bars", () => {
  const summary = summarizeMarketDaily({ schema_version: "1.0", run_id: "daily-2026-09-25", facts: [
    { id: "index.spx.change_percent", value: 0.5, quality: "reviewed", observation_date: "2026-09-25", source_url: "https://example.test/close" },
    { id: "treasury.2y.level_percent", metric: "yield_level", value: 4.25, unit: "percent", quality: "lagged", observation_date: "2026-09-24", source_url: "https://fred.stlouisfed.org/series/DGS2" },
  ] });
  const svg = buildMarketDailyChartSvg(summary);
  assert.match(svg, /2 年期美债：4\.25%/);
  assert.match(svg, /观测日 2026-09-24，非报告日/);
  assert.doesNotMatch(svg, /美债收益率水平（%）/);
});
