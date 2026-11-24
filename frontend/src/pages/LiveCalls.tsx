import { useCallback, useEffect, useState } from "react";
import { api } from "../utils/api";
import { useAuth } from "../utils/AuthContext";
import { formatDateTime, formatDuration, shortCallId } from "../utils/format";
import StatusBadge from "../components/shared/StatusBadge";
import type { Call, CaptureStatus } from "../types";

const REFRESH_MS = 3000;

function stage(c: Call): string {
  if (c.answer_time) return "Talking";
  if (c.ring_time) return "Ringing";
  return "Dialing";
}

function StatusBanner({ s }: { s: CaptureStatus }) {
  if (s.state === "running") {
    return (
      <div className="live-banner ok">
        ● Capturing on <strong>{s.interface}</strong> · {s.packets?.toLocaleString()} packets
        {s.dropped ? <span className="live-warn"> · {s.dropped.toLocaleString()} dropped</span> : null}
        {s.errors ? <span className="live-warn"> · {s.errors} errors</span> : null}
        {s.recording_enabled === false && " · recording off"}
      </div>
    );
  }
  const text: Record<string, string> = {
    stale: "The capture service has stopped reporting. Check that the capture container is running.",
    stopped: "The capture service is stopped.",
    not_configured: "Live capture is not set up. Start it with: docker compose --profile capture up -d",
  };
  return <div className="live-banner bad">⚠ {text[s.state] ?? "Capture status unknown."}</div>;
}

export default function LiveCalls({ onSelectCall }: { onSelectCall: (id: number) => void }) {
  const { can } = useAuth();
  const viewAll = can("calls.view_all");
  const [active, setActive] = useState<Call[]>([]);
  const [recent, setRecent] = useState<Call[]>([]);
  const [status, setStatus] = useState<CaptureStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const [live, finished] = await Promise.all([
        api.getCalls({ status: "IN_PROGRESS", source: "live", limit: 100 }),
        api.getCalls({ source: "live", limit: 30 }),
      ]);
      setActive(live);
      setRecent(finished.filter((c) => c.status !== "IN_PROGRESS").slice(0, 15));
      if (viewAll) setStatus(await api.getCaptureStatus());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not refresh");
    } finally {
      setLoaded(true);
    }
  }, [viewAll]);

  useEffect(() => {
    load();
    const timer = setInterval(() => { if (!document.hidden) load(); }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const rows = (calls: Call[], live: boolean) => calls.map((c) => (
    <tr key={c.id} className="call-row" onClick={() => onSelectCall(c.id)}>
      <td>{formatDateTime(c.start_time)}</td>
      <td>{c.caller || "—"}</td>
      <td>{c.called || "—"}</td>
      <td>{live ? <span className="live-stage">{stage(c)}</span> : <StatusBadge status={c.status} size="sm" />}</td>
      {!live && <td>{formatDuration(c.total_duration)}</td>}
      {!live && <td>{c.has_audio ? "🔊" : ""}</td>}
      <td style={{ opacity: 0.6 }}>{shortCallId(c.call_id)}</td>
    </tr>
  ));

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Live Calls</h1>
        <p className="page-subtitle">
          {viewAll ? "Calls on the monitored lines right now" : "Live calls for your extensions"} · refreshes every few seconds
        </p>
      </div>

      {viewAll && status && <StatusBanner s={status} />}
      {error && <div className="upload-error-banner">{error}</div>}

      {!loaded ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : active.length === 0 && recent.length === 0 ? (
        <div className="empty-state">
          <p>No calls yet. Live calls appear here as soon as one starts.</p>
        </div>
      ) : (
        <>
          {active.length > 0 && (
            <>
              <h3 className="live-heading">In progress ({active.length})</h3>
              <div className="table-wrap">
                <table className="calls-table">
                  <thead><tr><th>Started</th><th>From</th><th>To</th><th>State</th><th>Call-ID</th></tr></thead>
                  <tbody>{rows(active, true)}</tbody>
                </table>
              </div>
            </>
          )}
          {recent.length > 0 && (
            <>
              <h3 className="live-heading">Just finished</h3>
              <div className="table-wrap">
                <table className="calls-table">
                  <thead><tr><th>Started</th><th>From</th><th>To</th><th>Result</th><th>Duration</th><th>Rec</th><th>Call-ID</th></tr></thead>
                  <tbody>{rows(recent, false)}</tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
