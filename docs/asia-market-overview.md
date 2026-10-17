# Asia evening facts

The public evening refresh now appends the same Asia market module on ordinary A-share sessions and A-share holidays. The A-share review stays in its existing section; the Asia module contains exactly Hong Kong / Hang Seng, Japan / Nikkei 225 and Korea / KOSPI.

## Markdown consumer contract

The module starts with `### 亚洲市场概览` and uses columns `市场 | 指数 | 数据日期 | 收盘 | 涨跌幅 | 状态`. Market/index pairs are `香港 / 恒生指数`, `日本 / 日经225` and `韩国 / KOSPI`.

A closed observation uses `已收盘`, an ISO session date, a positive finite close and signed percentage return. Other statuses are `休市`, `未收盘` and `当日数据缺失`; all three numeric/date cells are em dashes. A market failure does not suppress other markets.

Each observed row has a following source note in the same section:

```markdown
- [香港收盘数据](https://finance.yahoo.com/quote/^HSI/history/)；2026-10-16T08:00:00+00:00；证据：`asia.close.<sha256>`
```

`source_time` means the exchange calendar's actual session close, including timezone and special close schedules. It is not a claimed Yahoo publication timestamp. `source_time_kind=exchange_session_close` and separate `retrieved_at` make that distinction explicit. Yahoo daily bar timestamps label local opening/session dates.

## Inputs and validation

The authoritative SSE calendar determines the A-share session. Independent XHKG, XTKS and XKRX calendars determine overseas holidays, the expected preceding session and the actual target-session close. Live daily bars must have a timezone, a current target-session bar and the immediately preceding exchange-session bar. HTTP success alone is insufficient. Each source request starts only after that market closes; retrieved_at must be timezone-aware, at or after the actual close, and no later than artifact generation. Prices must be finite and positive. V2 retains the actual preceding session date and close and rechecks the percentage return when consuming the artifact. An incomplete, stale or failed symbol becomes missing and produces a symbol-specific reason_code plus observed and expected dates, without provider exception text. Retained pre-close pending rows become missing once the market has closed when refreshing the public report.

The `python -m a_share_daily.asia_session --calendar CALENDAR --date YYYYMMDD --report-output OUTPUT` CLI produces `market_intel.asia_evening.v2` on ordinary days and A-share holidays. Public refresh validates and consumes a dated retained artifact when present; otherwise it builds the same session facts. Historical holiday-only v1 reports remain readable by the legacy renderer and Pages. Public refresh refuses v1 fact artifacts and requires rebuilding v2 with verified close/retrieval and preceding-bar evidence. Newly generated all-missing facts remain explicit rather than making valid A-share review unavailable. Legacy v1 validation retains its existing fail-closed behavior.

The benchmark universe includes `^HSI`. Cross-market live and retained snapshot diagnostics propagate nested equity errors to the top-level errors list; overseas benchmark dates also produce stale-date warnings. The separate daily_messenger HK integration is not used.

## Offline validation and operations boundary

Tests inject quote facts and do not call live sources. Preview artifacts belong outside Git, under the owning project's task data directory. Historical retained manifest previews must identify missing Hong Kong data rather than filling it from a new request. Tests of v2 producer retrieval validate the preceding session; a retained legacy snapshot may not contain its raw preceding bar and cannot establish that additional evidence.

This change does not publish, send, deploy, install a scheduler or modify retained owner artifacts. Deployment is a separate operation after provider and Pages consumer PRs are integrated.
