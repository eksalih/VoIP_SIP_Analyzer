import type { RTPStream } from "../../types";

interface Props {
  streams: RTPStream[];
}

function qualityLabel(loss: number | null, jitter: number | null): { label: string; color: string } {
  if (loss === null || jitter === null) return { label: "Unknown", color: "#8b949e" };
  if (loss > 5 || jitter > 50)  return { label: "Poor",    color: "#f85149" };
  if (loss > 1 || jitter > 20)  return { label: "Fair",    color: "#d29922" };
  return                                { label: "Good",    color: "#3fb950" };
}

function fmt(v: number | null, decimals = 2, unit = ""): string {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(decimals)}${unit}`;
}

export default function MediaQuality({ streams }: Props) {
  if (streams.length === 0) {
    return (
      <div className="media-empty">
        <span className="media-empty-icon">📵</span>
        <p className="media-empty-title">No RTP media data available</p>
        <p className="media-empty-sub">
          Media quality metrics are only captured for ANSWERED calls
          where the PCAP file includes RTP traffic alongside SIP signaling.
        </p>
      </div>
    );
  }

  const hasOneWay = streams.some((s) => s.is_one_way);

  return (
    <div className="media-quality">
      {hasOneWay && (
        <div className="media-alert">
          <span className="media-alert-icon">⚠️</span>
          <div>
            <strong>One-way audio detected</strong>
            <p>RTP packets are flowing in only one direction — the remote party may not be able to hear the caller.</p>
          </div>
        </div>
      )}

      <div className="stream-grid">
        {streams.map((stream, i) => {
          const q = qualityLabel(stream.packet_loss_pct, stream.jitter_ms);
          const direction = stream.source_ip
            ? `${stream.source_ip}:${stream.source_port} → ${stream.destination_ip}:${stream.destination_port}`
            : `Stream ${i + 1}`;

          return (
            <div key={stream.id} className={`stream-card ${stream.is_one_way ? "stream-one-way" : ""}`}>
              {/* Header */}
              <div className="stream-card-header">
                <div className="stream-direction-wrap">
                  <span className="stream-label">Direction</span>
                  <span className="stream-direction">{direction}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                  {stream.is_one_way && (
                    <span className="one-way-badge">ONE-WAY</span>
                  )}
                  <span
                    className="quality-badge"
                    style={{
                      color: q.color,
                      borderColor: `${q.color}55`,
                      background: `${q.color}18`,
                    }}
                  >
                    ● {q.label}
                  </span>
                </div>
              </div>

              {/* Metrics grid */}
              <div className="stream-metrics">
                <div className="metric-item">
                  <span className="metric-label">Codec</span>
                  <span className="metric-value mono">{stream.codec ?? `PT${stream.payload_type}`}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Packets</span>
                  <span className="metric-value">{stream.packet_count ?? "—"}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Packet Loss</span>
                  <span
                    className="metric-value"
                    style={{ color: (stream.packet_loss_pct ?? 0) > 1 ? "#f85149" : "inherit" }}
                  >
                    {fmt(stream.packet_loss_pct, 1, "%")}
                    {!!stream.packet_loss_count && (
                      <span className="metric-sub"> ({stream.packet_loss_count} lost)</span>
                    )}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Jitter (avg)</span>
                  <span
                    className="metric-value"
                    style={{ color: (stream.jitter_ms ?? 0) > 20 ? "#d29922" : "inherit" }}
                  >
                    {fmt(stream.jitter_ms, 2, " ms")}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Jitter (max)</span>
                  <span className="metric-value">{fmt(stream.jitter_max_ms, 2, " ms")}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Duration</span>
                  <span className="metric-value">{fmt(stream.duration_seconds, 1, " s")}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">SSRC</span>
                  <span className="metric-value mono">{stream.ssrc ?? "—"}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Quality legend */}
      <div className="quality-legend">
        <span className="legend-item" style={{ color: "#3fb950" }}>● Good — loss &lt;1%, jitter &lt;20ms</span>
        <span className="legend-item" style={{ color: "#d29922" }}>● Fair — loss &lt;5%, jitter &lt;50ms</span>
        <span className="legend-item" style={{ color: "#f85149" }}>● Poor — loss &gt;5% or jitter &gt;50ms</span>
      </div>
    </div>
  );
}
