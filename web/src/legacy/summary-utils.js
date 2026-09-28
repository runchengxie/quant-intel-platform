function selectVisibleSummaries(summaries, reports, selectedDate, limit = 5) {
  const reportsById = new Map(reports.map((report) => [report.id, report]));
  const publicDates = [...new Set(reports.map((report) => report.date))]
    .sort((left, right) => right.localeCompare(left))
    .slice(0, limit);
  const allowedDates = selectedDate ? [selectedDate] : publicDates;

  return summaries
    .filter((summary) => {
      const morning = reportsById.get(summary.morning_report_id);
      const evening = reportsById.get(summary.evening_report_id);
      return morning?.kind === "morning"
        && evening?.kind === "evening"
        && summary.date === morning.date
        && evening.date <= morning.date
        && allowedDates.includes(summary.date);
    })
    .sort((left, right) => right.date.localeCompare(left.date));
}

function selectVisibleReports(reports, selectedDate, kind) {
  const latestDate = [...new Set(reports.map((report) => report.date))]
    .sort((left, right) => right.localeCompare(left))[0];
  const targetDate = selectedDate || latestDate;
  return reports
    .filter((report) => report.date === targetDate && (kind === "all" || report.kind === kind))
    .sort((left, right) => {
      if (left.kind !== right.kind) return left.kind === "morning" ? -1 : 1;
      return left.id.localeCompare(right.id);
    });
}

function selectVisibleInsights(insights, reports, selectedDate) {
  const ids = new Set(reports.map((report) => report.id));
  return selectVisibleSummaries(insights, reports, selectedDate)
    .filter((insight) => Array.isArray(insight.source_report_ids)
      && insight.source_report_ids.every((id) => ids.has(id)));
}

function isHealthDelayed(health, now = Date.now()) {
  const elapsed = (now - Date.parse(health.latest_source_generated_at)) / 3600000;
  // Match pipeline_health's target-day fallback in Beijing, independent of the browser timezone.
  const targetEnd = Date.parse(`${health.latest_target_date}T23:59:59.999+08:00`);
  const targetAge = (now - targetEnd) / 3600000;
  return ["stale", "behind", "missing", "invalid_timestamp"].includes(health.status)
    || (Number.isFinite(elapsed) && elapsed > health.max_age_hours)
    || (!health.expected_date && Number.isFinite(targetAge) && targetAge > health.max_age_hours);
}

const summaryUtils = { selectVisibleSummaries, selectVisibleReports, selectVisibleInsights, isHealthDelayed };
if (typeof module !== "undefined" && module.exports) {
  module.exports = summaryUtils;
} else {
  window.marketIntelUtils = summaryUtils;
}
