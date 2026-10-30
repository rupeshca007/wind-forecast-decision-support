import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

type Metrics = {
  interval_count: number;
  matched_intervals: number;
  unmatched_intervals: number;
  missing_actual_intervals: number;
  missing_forecast_intervals: number;
  incomplete_actual_intervals: number;
  invalid_intervals: number;
  coverage: number | null;
  actual_mean_mw: number | null;
  forecast_mean_mw: number | null;
  mae_mw: number | null;
  rmse_mw: number | null;
  bias_mw: number | null;
  wape: number | null;
  p95_absolute_error_mw: number | null;
  max_absolute_error_mw: number | null;
};

type DailyMetric = Metrics & { delivery_date: string };

type SeriesPoint = {
  delivery_time: string;
  delivery_date: string;
  actual_generation_mw: number | null;
  forecast_generation_mw: number | null;
  forecast_publish_time: string | null;
  forecast_lead_hours: number | null;
  match_status: string;
  signed_error_mw: number | null;
  absolute_error_mw: number | null;
};

type AnalysisResponse = {
  metadata: {
    source?: string;
    analysis_grain?: string;
    forecast_selection?: string;
    query_start: string;
    query_end: string;
  };
  metrics: Metrics;
  daily_metrics: DailyMetric[];
  series: SeriesPoint[];
};

type ChartPoint = SeriesPoint & { label: string };

const monthStart = "2026-01-01";
const monthEnd = "2026-01-31";

const numberFormatter = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const oneDecimalFormatter = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 1,
});

function formatMw(value: number | null, decimals = 0): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${decimals ? oneDecimalFormatter.format(value) : numberFormatter.format(value)} MW`;
}

function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(new Date(value));
}

function signedClass(value: number | null): string {
  if (value === null || value === 0) return "neutral";
  return value > 0 ? "positive" : "negative";
}

async function loadAnalysis(start: string, end: string): Promise<AnalysisResponse> {
  const params = new URLSearchParams({ start, end });
  const response = await fetch(`${API_BASE_URL}/api/analysis?${params.toString()}`);
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the useful HTTP status when the server did not return JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<AnalysisResponse>;
}

function App() {
  const [startDate, setStartDate] = useState(monthStart);
  const [endDate, setEndDate] = useState(monthEnd);
  const [appliedRange, setAppliedRange] = useState({ start: monthStart, end: monthEnd });
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    setError(null);
    loadAnalysis(appliedRange.start, appliedRange.end)
      .then(setAnalysis)
      .catch((requestError: Error) => setError(requestError.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
    // The query is intentionally refreshed only when the applied range changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appliedRange.start, appliedRange.end]);

  const chartData = useMemo<ChartPoint[]>(
    () =>
      (analysis?.series ?? []).map((point) => ({
        ...point,
        label: formatTime(point.delivery_time),
      })),
    [analysis],
  );

  const submitRange = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (startDate > endDate) {
      setError("Start date must be on or before end date.");
      return;
    }
    setAppliedRange({ start: startDate, end: endDate });
  };

  const showFullMonth = () => {
    setStartDate(monthStart);
    setEndDate(monthEnd);
    setAppliedRange({ start: monthStart, end: monthEnd });
  };

  const metrics = analysis?.metrics;
  const metadata = analysis?.metadata;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">W</div>
          <div>
            <p className="brand-name">Northstar energy</p>
            <p className="brand-context">Wind forecast review</p>
          </div>
        </div>
        <div className="data-status">
          <span className={`status-dot ${loading ? "is-loading" : error ? "is-error" : ""}`} aria-hidden="true" />
          <span>{loading ? "Updating analysis" : error ? "API unavailable" : "Dataset ready"}</span>
        </div>
      </header>

      <section className="hero-row">
        <div>
          <p className="eyebrow">Operations intelligence · January 2026</p>
          <h1>Was the wind forecast ready for the day ahead?</h1>
          <p className="hero-copy">
            Compare the day-ahead wind-generation signal with what actually reached the grid, and spot where forecast error may have mattered most.
          </p>
        </div>
        <div className="hero-note">
          <span className="note-kicker">Decision lens</span>
          <strong>Latest eligible forecast</strong>
          <p>Only publications available by the previous day at 23:59 UTC are included.</p>
        </div>
      </section>

      <section className="control-panel" aria-label="Analysis controls">
        <form className="date-form" onSubmit={submitRange}>
          <div className="field-group">
            <label htmlFor="start-date">From</label>
            <input id="start-date" type="date" min={monthStart} max={monthEnd} value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </div>
          <span className="date-arrow" aria-hidden="true">→</span>
          <div className="field-group">
            <label htmlFor="end-date">To</label>
            <input id="end-date" type="date" min={monthStart} max={monthEnd} value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </div>
          <button className="button button-primary" type="submit">Apply range</button>
          <button className="button button-quiet" type="button" onClick={showFullMonth}>Full month</button>
        </form>
        <div className="control-meta">
          <span className="live-pill"><span className="live-dot" /> Elexon data</span>
          <span>{metadata?.analysis_grain ?? "hourly"} resolution</span>
        </div>
      </section>

      {error && (
        <section className="error-banner" role="alert">
          <div>
            <strong>Could not load the analysis</strong>
            <p>{error}. Check that the FastAPI server is running at {API_BASE_URL}.</p>
          </div>
          <button className="button button-light" type="button" onClick={refresh}>Retry</button>
        </section>
      )}

      {loading && !analysis ? (
        <section className="loading-panel" aria-live="polite">
          <div className="spinner" />
          <div>
            <strong>Loading January wind performance</strong>
            <p>Fetching interval accuracy and daily summaries…</p>
          </div>
        </section>
      ) : analysis && metrics ? (
        <>
          <section className="summary-grid" aria-label="Summary metrics">
            <MetricCard label="Forecast coverage" value={formatPercent(metrics.coverage)} detail={`${metrics.matched_intervals} of ${metrics.interval_count} intervals matched`} accent="teal" />
            <MetricCard label="Mean absolute error" value={formatMw(metrics.mae_mw)} detail="Average distance from actual generation" accent="blue" />
            <MetricCard label="RMSE" value={formatMw(metrics.rmse_mw)} detail="Weights larger misses more heavily" accent="purple" />
            <MetricCard label="Mean bias" value={formatMw(metrics.bias_mw)} detail={metrics.bias_mw !== null && metrics.bias_mw > 0 ? "Forecast tended to overstate output" : "Forecast tended to understate output"} accent={metrics.bias_mw !== null && metrics.bias_mw > 0 ? "amber" : "green"} signed={metrics.bias_mw} />
          </section>

          <section className="chart-card primary-chart-card">
            <div className="section-heading">
              <div>
                <p className="section-kicker">Generation profile</p>
                <h2>Forecast vs actual wind output</h2>
              </div>
              <div className="chart-legend-note"><span className="legend-line forecast-line" /> Forecast <span className="legend-line actual-line" /> Actual</div>
            </div>
            <div className="chart-wrap chart-wrap-large">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="#e5edf1" vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: "#738596", fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={46} />
                  <YAxis tick={{ fill: "#738596", fontSize: 11 }} tickLine={false} axisLine={false} width={58} tickFormatter={(value: number) => `${Math.round(value / 1000)}k`} />
                  <Tooltip content={<ChartTooltip />} />
                  <Legend content={() => null} />
                  <Line type="monotone" dataKey="forecast_generation_mw" name="Forecast" stroke="#287d83" strokeWidth={2} dot={false} connectNulls={false} />
                  <Line type="monotone" dataKey="actual_generation_mw" name="Actual" stroke="#17324d" strokeWidth={2} dot={false} connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="chart-footnote">Hourly average actual generation · selected date range {formatDate(appliedRange.start)} to {formatDate(appliedRange.end)}</p>
          </section>

          <section className="two-column-grid">
            <div className="chart-card">
              <div className="section-heading compact-heading">
                <div>
                  <p className="section-kicker">Forecast error</p>
                  <h2>Signed error by interval</h2>
                </div>
                <span className="muted-label">Forecast − actual</span>
              </div>
              <div className="chart-wrap chart-wrap-small">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 12, right: 8, left: 4, bottom: 4 }}>
                    <CartesianGrid stroke="#e5edf1" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: "#738596", fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={50} />
                    <YAxis tick={{ fill: "#738596", fontSize: 10 }} tickLine={false} axisLine={false} width={48} tickFormatter={(value: number) => `${Math.round(value / 1000)}k`} />
                    <Tooltip content={<ChartTooltip error />} />
                    <ReferenceLine y={0} stroke="#9aabb7" />
                    <Bar dataKey="signed_error_mw" name="Signed error" fill="#e4a24b" maxBarSize={8} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="insight-card">
              <p className="section-kicker">Readout</p>
              <h2>What stands out</h2>
              <div className="insight-row">
                <span className="insight-icon teal-icon">↗</span>
                <div><strong>{formatPercent(metrics.wape)} weighted error</strong><p>Across all matched hourly intervals.</p></div>
              </div>
              <div className="insight-row">
                <span className="insight-icon purple-icon">95</span>
                <div><strong>{formatMw(metrics.p95_absolute_error_mw)} p95 miss</strong><p>Only 5% of intervals exceeded this error.</p></div>
              </div>
              <div className="insight-row">
                <span className="insight-icon amber-icon">!</span>
                <div><strong>{formatMw(metrics.max_absolute_error_mw)} largest miss</strong><p>Maximum absolute difference in the range.</p></div>
              </div>
            </div>
          </section>

          <section className="table-card">
            <div className="section-heading">
              <div>
                <p className="section-kicker">Daily review</p>
                <h2>Where did the forecast drift?</h2>
              </div>
              <span className="muted-label">{analysis.daily_metrics.length} delivery days</span>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr><th>Date</th><th>Actual average</th><th>Forecast average</th><th>MAE</th><th>Bias</th><th>Coverage</th></tr>
                </thead>
                <tbody>
                  {analysis.daily_metrics.map((day) => (
                    <tr key={day.delivery_date}>
                      <td className="date-cell">{formatDate(day.delivery_date)}</td>
                      <td>{formatMw(day.actual_mean_mw)}</td>
                      <td>{formatMw(day.forecast_mean_mw)}</td>
                      <td>{formatMw(day.mae_mw)}</td>
                      <td className={signedClass(day.bias_mw)}>{formatMw(day.bias_mw)}</td>
                      <td><span className="coverage-chip">{formatPercent(day.coverage)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <footer className="page-footer">
            <span>Source: {metadata?.source ?? "Elexon Insights API"}</span>
            <span>Forecast rule: latest publication available by previous day 23:59 UTC</span>
          </footer>
        </>
      ) : null}
    </main>
  );
}

function MetricCard({ label, value, detail, accent, signed }: { label: string; value: string; detail: string; accent: string; signed?: number | null }) {
  return (
    <article className={`metric-card accent-${accent}`}>
      <div className="metric-topline"><span>{label}</span><span className="metric-mark" /></div>
      <strong className={signedClass(signed ?? null)}>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function ChartTooltip({ active, payload, label, error = false }: { active?: boolean; payload?: Array<{ value?: number; name?: string; color?: string }>; label?: string; error?: boolean }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((entry) => <span key={entry.name} style={{ color: entry.color }}>{entry.name}: {formatMw(entry.value ?? null)}</span>)}
      {error && <small>Positive values mean forecast was higher than actual.</small>}
    </div>
  );
}

export default App;
