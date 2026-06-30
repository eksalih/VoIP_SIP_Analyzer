import { useState, useEffect } from "react";
import { api } from "../utils/api";
import { formatDuration } from "../utils/format";
import type { Analytics } from "../types";

function jitterColor(v: number | null): string {
  if (v === null) return "inherit";
  if (v > 50) return "#f85149";
  if (v > 20) return "#d29922";
  return "#3fb950";
}
function lossColor(v: number | null): string {
  if (v === null) return "inherit";
  if (v > 5) return "#f85149";
  if (v > 1) return "#d29922";
  return "#3fb950";
}

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAnalytics().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading-state"><div className="spinner" /><span>Loading analytics…</span></div>;
  if (!data)   return <div className="empty-state"><p>Could not load analytics.</p></div>;

  const maxDay  = Math.max(...data.calls_by_day.map((d) => d.count), 1);
  const maxDist = Math.max(...data.status_distribution.map((d) => d.count), 1);
  const hasRtp  = data.rtp_streams_total > 0;

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Analytics</h1>
        <p className="page-subtitle">Aggregate call and media quality statistics across all captures</p>
      </div>

      {/* Call KPIs */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <span className="kpi-value">{data.total_calls}</span>
          <span className="kpi-label">Total Calls</span>
        </div>
        <div className="kpi-card answered">
          <span className="kpi-value">{data.answered}</span>
          <span className="kpi-label">Answered</span>
        </div>
        <div className="kpi-card missed">
          <span className="kpi-value">{data.missed}</span>
          <span className="kpi-label">Missed</span>
        </div>
        <div className="kpi-card rejected">
          <span className="kpi-value">{data.rejected}</span>
          <span className="kpi-label">Rejected</span>
        </div>
        <div className="kpi-card failed">
          <span className="kpi-value">{data.failed}</span>
          <span className="kpi-label">Failed</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-value">{data.success_rate}%</span>
          <span className="kpi-label">Success Rate</span>
        </div>
      </div>

      {/* Duration KPIs */}
      <div className="kpi-grid" style={{ marginTop: "12px" }}>
        <div className="kpi-card">
          <span className="kpi-value">{formatDuration(data.avg_ring_duration)}</span>
          <span className="kpi-label">Avg Ring Duration</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-value">{formatDuration(data.avg_talk_duration)}</span>
          <span className="kpi-label">Avg Talk Duration</span>
        </div>
      </div>

      {/* RTP / Media Quality KPIs */}
      {hasRtp && (
        <>
          <div className="section-divider">
            <span>Media Quality</span>
          </div>
          <div className="kpi-grid">
            <div className="kpi-card">
              <span className="kpi-value">{data.rtp_streams_total}</span>
              <span className="kpi-label">RTP Streams</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-value" style={{ color: jitterColor(data.rtp_avg_jitter_ms) }}>
                {data.rtp_avg_jitter_ms != null ? `${data.rtp_avg_jitter_ms} ms` : "—"}
              </span>
              <span className="kpi-label">Avg Jitter</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-value" style={{ color: lossColor(data.rtp_avg_loss_pct) }}>
                {data.rtp_avg_loss_pct != null ? `${data.rtp_avg_loss_pct}%` : "—"}
              </span>
              <span className="kpi-label">Avg Packet Loss</span>
            </div>
            <div className="kpi-card" style={data.rtp_one_way_count > 0 ? { borderColor: "#f8514944" } : {}}>
              <span className="kpi-value" style={{ color: data.rtp_one_way_count > 0 ? "#f85149" : "#3fb950" }}>
                {data.rtp_one_way_count > 0 ? `⚠ ${data.rtp_one_way_count}` : "✓ None"}
              </span>
              <span className="kpi-label">One-Way Audio</span>
            </div>
          </div>
        </>
      )}

      {/* Charts */}
      <div className="charts-grid" style={{ marginTop: "24px" }}>
        <div className="chart-card">
          <h3 className="chart-title">Status Distribution</h3>
          {data.status_distribution.map((item) => (
            <div key={item.status} className="bar-row">
              <span className="bar-label">{item.status}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(item.count / maxDist) * 100}%`, background: item.color }} />
              </div>
              <span className="bar-count">{item.count}</span>
            </div>
          ))}
        </div>

        <div className="chart-card">
          <h3 className="chart-title">Calls by Day</h3>
          {data.calls_by_day.length === 0 ? (
            <p style={{ color: "#8b949e", fontSize: "14px" }}>No data available.</p>
          ) : (
            <div className="day-chart">
              {data.calls_by_day.map((day) => (
                <div key={day.date} className="day-bar-col" title={`${day.date}: ${day.count} calls`}>
                  <div className="day-bar" style={{ height: `${Math.max(4, (day.count / maxDay) * 120)}px` }} />
                  <span className="day-label">{day.date.slice(5)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
