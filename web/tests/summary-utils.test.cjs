const test = require("node:test");
const assert = require("node:assert/strict");
const { selectVisibleSummaries, selectVisibleReports } = require("../src/legacy/summary-utils.js");
const { selectVisibleInsights, isHealthDelayed } = require("../src/legacy/summary-utils.js");

function report(date, kind) {
  return { id: `${date}-${kind}`, date, kind };
}

function note(date, eveningDate = date) {
  return {
    date,
    text: `note ${date}`,
    morning_report_id: `${date}-morning`,
    evening_report_id: `${eveningDate}-evening`,
  };
}

test("insight navigation excludes missing source reports", () => {
  const reports = [report("2026-09-14", "morning"), report("2026-09-14", "evening")];
  const records = [
    { ...note("2026-09-14"), source_report_ids: ["2026-09-14-morning", "2026-09-14-evening"] },
    { ...note("2026-09-14"), source_report_ids: ["missing"] },
  ];
  assert.deepEqual(selectVisibleInsights(records, reports, ""), [records[0]]);
});

test("default view returns summaries for at most five latest report dates", () => {
  const reports = [];
  const summaries = [];
  for (let day = 1; day <= 7; day += 1) {
    const date = `2026-09-${String(day).padStart(2, "0")}`;
    reports.push(report(date, "morning"), report(date, "evening"));
    summaries.push(note(date));
  }

  const visible = selectVisibleSummaries(summaries, reports, "");

  assert.deepEqual(visible.map((item) => item.date), [
    "2026-09-07", "2026-09-06", "2026-09-05", "2026-09-04", "2026-09-03",
  ]);
});

test("selected date returns only its summary", () => {
  const reports = [report("2026-09-14", "morning"), report("2026-09-14", "evening")];
  const summaries = [note("2026-09-14"), note("2026-09-13")];

  assert.deepEqual(
    selectVisibleSummaries(summaries, reports, "2026-09-14").map((item) => item.date),
    ["2026-09-14"],
  );
});

test("summary with missing or incorrectly typed sources is not displayed", () => {
  const reports = [report("2026-09-14", "morning"), report("2026-09-14", "evening")];
  const invalid = [
    { ...note("2026-09-14"), evening_report_id: "missing-evening" },
    { ...note("2026-09-14"), morning_report_id: "2026-09-14-evening" },
  ];

  assert.deepEqual(selectVisibleSummaries(invalid, reports, ""), []);
});

test("default report list contains only the latest date", () => {
  const reports = [
    report("2026-09-13", "morning"),
    report("2026-09-14", "morning"),
    report("2026-09-14", "evening"),
  ];

  assert.deepEqual(
    selectVisibleReports(reports, "", "all").map((item) => item.id),
    ["2026-09-14-morning", "2026-09-14-evening"],
  );
});

test("selected date and kind filter apply together", () => {
  const reports = [
    report("2026-09-13", "morning"),
    report("2026-09-14", "morning"),
    report("2026-09-14", "evening"),
  ];

  assert.deepEqual(
    selectVisibleReports(reports, "2026-09-14", "morning").map((item) => item.id),
    ["2026-09-14-morning"],
  );
});

function health(overrides = {}) {
  return {
    status: "calendar_unverified",
    latest_target_date: "2026-09-16",
    latest_source_generated_at: "2026-09-19T15:00:00+08:00",
    expected_date: null,
    max_age_hours: 72,
    ...overrides,
  };
}

test("a backfilled report becomes stale when its market date exceeds the age limit", () => {
  const reportHealth = health();
  assert.equal(isHealthDelayed(reportHealth, Date.parse("2026-09-19T15:00:00+08:00")), false);
  assert.equal(isHealthDelayed(reportHealth, Date.parse("2026-09-20T08:00:00+08:00")), true);
});

test("target-date age uses the end of the Beijing calendar day", () => {
  assert.equal(isHealthDelayed(health(), Date.parse("2026-09-19T23:59:59.999+08:00")), false);
  assert.equal(isHealthDelayed(health(), Date.parse("2026-09-20T00:00:00+08:00")), true);
  assert.equal(isHealthDelayed(health(), Date.parse("2026-09-19T16:00:00Z")), true);
});

test("source age still marks a report stale even if its target date is recent", () => {
  const reportHealth = health({
    latest_target_date: "2026-09-19",
    latest_source_generated_at: "2026-09-16T07:00:00+08:00",
  });
  assert.equal(isHealthDelayed(reportHealth, Date.parse("2026-09-19T08:00:00+08:00")), true);
});

test("server-reported gaps remain visible when report timestamps are recent", () => {
  for (const status of ["stale", "behind", "missing", "invalid_timestamp"]) {
    assert.equal(isHealthDelayed(health({ status }), Date.parse("2026-09-19T15:00:00+08:00")), true);
  }
});

test("an explicit expected date keeps the backend calendar-based freshness rule", () => {
  const reportHealth = health({ status: "current", expected_date: "2026-09-16" });
  assert.equal(isHealthDelayed(reportHealth, Date.parse("2026-09-20T08:00:00+08:00")), false);
});
