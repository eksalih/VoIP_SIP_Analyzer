import type { CallStatus } from "../../types";
import { STATUS_COLORS, STATUS_BG } from "../../utils/format";

interface Props {
  status: CallStatus;
  size?: "sm" | "md";
}

export default function StatusBadge({ status, size = "md" }: Props) {
  const style: React.CSSProperties = {
    display: "inline-block",
    padding: size === "sm" ? "2px 8px" : "4px 12px",
    borderRadius: "999px",
    fontSize: size === "sm" ? "11px" : "12px",
    fontWeight: 600,
    letterSpacing: "0.04em",
    color: STATUS_COLORS[status] || "#607d8b",
    background: STATUS_BG[status] || "#eceff1",
    border: `1px solid ${STATUS_COLORS[status] || "#607d8b"}30`,
    whiteSpace: "nowrap",
  };
  return <span style={style}>{status}</span>;
}
