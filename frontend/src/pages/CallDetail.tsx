import { useState, useEffect } from "react";
import { api } from "../utils/api";
import { formatDateTime, formatDuration } from "../utils/format";
import StatusBadge from "../components/shared/StatusBadge";
import SIPLadder from "../components/calls/SIPLadder";
import MediaQuality from "../components/calls/MediaQuality";
import type { Call, SIPEvent, RTPStream } from "../types";

interface Props {
  callId: number;
  onBack: () => void;
}

type Tab = "ladder" | "media" | "packets" | "raw";

export default function CallDetail({ callId, onBack }: Props) {
  const [call, setCall]               = useState<Call | null>(null);
  const [mediaStreams, setMediaStreams] = useState<RTPStream[]>([]);
  const [loading, setLoading]         = useState(true);
  const [tab, setTab]                 = useState<Tab>("ladder");
  const [selectedEvent, setSelectedEvent] = useState<SIPEvent | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getCall(callId),
      api.getCallMedia(callId).catch(() => []),
    ]).then(([callData, media]) => {
      setCall(callData);
      setMediaStreams(media ?? []);
    }).finally(() => setLoading(false));
  }, [callId]);

  if (loading) return <div className="loading-state"><div className="spinner" /><span>Loading…</span></div>;
  if (!call)   return <div className="empty-state"><p>Call not found.</p></div>;

  const events     = call.events || [];
  const hasMedia   = mediaStreams.length > 0;
  const hasOneWay  = mediaStreams.some(s => s.is_one_way);

  const TAB_LABELS: Record<Tab, string> = {
    ladder:  "SIP Ladder",
    media:   "Media Quality",
    packets: "Packet Viewer",
    raw:     "Raw Messages",
  };

  return (
    <div className="page">
      <button className="back-btn" onClick={onBack}>← Back to Call Log</button>

      {/* Header */}
      <div className="detail-header">
        <div>
          <h2 className="page-title">Call Detail</h2>
          <code className="call-id-full">{call.call_id}</code>
        </div>
        <StatusBadge status={call.status} size="md" />
      </div>

      {/* Summary cards */}
      <div className="summary-grid">
        <div className="summary-card">
          <span className="card-label">Caller</span>
          <span className="card-value">{call.caller || "—"}</span>
          {call.display_name && <span className="card-sub">{call.display_name}</span>}
        </div>
        <div className="summary-card">
          <span className="card-label">Called</span>
          <span className="card-value">{call.called || "—"}</span>
          {call.sip_domain && <span className="card-sub">{call.sip_domain}</span>}
        </div>
        <div className="summary-card">
          <span className="card-label">Started</span>
          <span className="card-value">{formatDateTime(call.start_time)}</span>
        </div>
        <div className="summary-card">
          <span className="card-label">Ring Duration</span>
          <span className="card-value">{formatDuration(call.ring_duration)}</span>
        </div>
        <div className="summary-card">
          <span className="card-label">Talk Duration</span>
          <span className="card-value">{formatDuration(call.talk_duration)}</span>
        </div>
        <div className="summary-card">
          <span className="card-label">Total Duration</span>
          <span className="card-value">{formatDuration(call.total_duration)}</span>
        </div>
        {call.rejection_reason && (
          <div className="summary-card rejection">
            <span className="card-label">Rejection Reason</span>
            <span className="card-value">{call.sip_result_code} {call.rejection_reason}</span>
          </div>
        )}
        {call.user_agent && (
          <div className="summary-card">
            <span className="card-label">User Agent</span>
            <span className="card-value small">{call.user_agent}</span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="detail-tabs">
        {(["ladder", "media", "packets", "raw"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`tab-btn ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {TAB_LABELS[t]}
            {/* Badges */}
            {t === "media" && hasMedia && (
              <span
                className="tab-badge"
                style={{ background: hasOneWay ? "#f85149" : "#3fb950" }}
                title={hasOneWay ? "One-way audio detected" : `${mediaStreams.length} stream(s)`}
              >
                {hasOneWay ? "⚠" : mediaStreams.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "ladder" && (
        <div className="tab-panel">
          <SIPLadder events={events} sourceIp={call.source_ip} destIp={call.destination_ip} />
        </div>
      )}

      {tab === "media" && (
        <div className="tab-panel">
          <MediaQuality streams={mediaStreams} />
        </div>
      )}

      {tab === "packets" && (
        <div className="tab-panel">
          <table className="calls-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Timestamp</th>
                <th>Source</th>
                <th>Destination</th>
                <th>Method / Code</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => (
                <tr key={ev.id} className="call-row" onClick={() => setSelectedEvent(ev)}>
                  <td>{i + 1}</td>
                  <td style={{ fontSize: "12px" }}>
                    {ev.timestamp
                      ? new Date(ev.timestamp).toISOString().replace("T", " ").slice(0, 23)
                      : "—"}
                  </td>
                  <td>{ev.source_ip || "—"}</td>
                  <td>{ev.destination_ip || "—"}</td>
                  <td>
                    <strong>{ev.sip_method || `${ev.sip_response_code} ${ev.sip_response_text || ""}`}</strong>
                  </td>
                  <td style={{ color: "#58a6ff", fontSize: "12px" }}>View raw →</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "raw" && (
        <div className="tab-panel">
          {events.length === 0 ? (
            <p style={{ color: "#8b949e" }}>No raw messages available.</p>
          ) : (
            events.map((ev, i) => (
              <div key={ev.id} className="raw-message-block">
                <div className="raw-message-header">
                  <strong>#{i + 1}</strong>
                  <span>{ev.sip_method || `${ev.sip_response_code} ${ev.sip_response_text || ""}`}</span>
                  <span className="raw-ips">{ev.source_ip} → {ev.destination_ip}</span>
                </div>
                <pre className="raw-message-body">{ev.raw_message || "(no raw data)"}</pre>
              </div>
            ))
          )}
        </div>
      )}

      {/* Raw message modal */}
      {selectedEvent && (
        <div className="modal-overlay" onClick={() => setSelectedEvent(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span>Raw SIP Message</span>
              <button onClick={() => setSelectedEvent(null)}>✕</button>
            </div>
            <pre className="modal-body">{selectedEvent.raw_message || "(no raw data)"}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
