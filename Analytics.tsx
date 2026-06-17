import type { SIPEvent } from "../../types";
import { formatTime, sipEventLabel } from "../../utils/format";

interface Props {
  events: SIPEvent[];
  sourceIp?: string | null;
  destIp?: string | null;
}

const METHOD_COLORS: Record<string, string> = {
  INVITE:  "#1976d2",
  ACK:     "#388e3c",
  BYE:     "#d32f2f",
  CANCEL:  "#f57c00",
  TRYING:  "#757575",
  RINGING: "#7b1fa2",
  OK:      "#388e3c",
  DECLINE: "#c62828",
  BUSY:    "#e64a19",
};

function getColor(event: SIPEvent): string {
  if (event.sip_method) {
    return METHOD_COLORS[event.sip_method.toUpperCase()] || "#455a64";
  }
  const code = event.sip_response_code;
  if (!code) return "#455a64";
  if (code === 200) return "#388e3c";
  if (code === 180 || code === 183) return "#7b1fa2";
  if (code === 100) return "#757575";
  if (code >= 400) return "#c62828";
  return "#455a64";
}

function isFromSource(event: SIPEvent, sourceIp?: string | null): boolean {
  return event.source_ip === sourceIp;
}

export default function SIPLadder({ events, sourceIp, destIp }: Props) {
  if (!events.length) return <div className="ladder-empty">No SIP events recorded.</div>;

  const sortedEvents = [...events].sort((a, b) => {
    if (!a.timestamp) return 1;
    if (!b.timestamp) return -1;
    return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
  });

  const callerLabel = sourceIp || "Caller";
  const calleeLabel = destIp || "Called";

  return (
    <div className="ladder-container">
      {/* Column headers */}
      <div className="ladder-header">
        <div className="ladder-endpoint caller">
          <div className="endpoint-dot" />
          <span>{callerLabel}</span>
        </div>
        <div className="ladder-spacer" />
        <div className="ladder-endpoint callee">
          <div className="endpoint-dot" />
          <span>{calleeLabel}</span>
        </div>
      </div>

      {/* Vertical lines + arrows */}
      <div className="ladder-body">
        <div className="ladder-line left" />
        <div className="ladder-line right" />

        {sortedEvents.map((event, i) => {
          const label = sipEventLabel(event);
          const color = getColor(event);
          const fromLeft = isFromSource(event, sourceIp);

          return (
            <div key={event.id} className={`ladder-row ${fromLeft ? "left-to-right" : "right-to-left"}`}>
              <span className="ladder-time">{formatTime(event.timestamp)}</span>

              <div className="ladder-arrow-wrap">
                {/* Arrow line */}
                <div className="arrow-line" style={{ borderColor: color }}>
                  <span className="arrow-label" style={{ color }}>{label}</span>
                </div>
                {/* Arrowhead */}
                <div className={`arrow-head ${fromLeft ? "right" : "left"}`} style={{ borderLeftColor: fromLeft ? color : "transparent", borderRightColor: !fromLeft ? color : "transparent" }} />
              </div>

              <span className="ladder-seq">#{i + 1}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
