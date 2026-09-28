export const factSource = (fact) => {
  const href = fact?.source_url;
  if (!/^https:\/\//.test(href || '')) return null;
  const id = fact.id || '';
  const label = href.startsWith('https://home.treasury.gov/') ? '美国财政部'
    : href.startsWith('https://fred.stlouisfed.org/') ? 'FRED'
      : href.startsWith('https://finance.yahoo.com/') ? 'Yahoo Finance'
        : href.startsWith('https://site.financialmodelingprep.com/') ? 'FMP'
          : href.startsWith('https://www.coingecko.com/') ? 'CoinGecko'
            : href.startsWith('https://www.kraken.com/') ? 'Kraken'
              : href.startsWith('https://www-cdn.abcnews.com/') ? 'ABC News'
              : id.startsWith('index.') ? '核实报道' : '来源';
  return { href, label };
};

export const uniqueFactSources = (facts) => {
  const sources = facts.map(factSource).filter(Boolean);
  return sources.filter((source, index) => sources.findIndex((item) => item.href === source.href) === index);
};
