import type { CallStatus } from "../types";

export const STATUS_COLORS: Record<CallStatus, string> = {
  ANSWERED:  "#4caf50",
  MISSED:    "#ff9800",
  REJECTED:  "#f44336",
  FAILED:    "#9e9e9e",
  CANCELLED: "#2196f3",
  UNKNOWN:   "#607d8b",
};

export const STATUS_BG: Record<CallStatus, string> = {
  ANSWERED:  "#e8f5e9",
  MISSED:    "#fff3e0",
  REJECTED:  "#ffebee",
  FAILED:    "#f5f5f5",
  CANCELLED: "#e3f2fd",
  UNKNOWN:   "#eceff1",
};

export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function shortCallId(callId: string): string {
  return callId.length > 24 ? `${callId.slice(0, 12)}…${callId.slice(-8)}` : callId;
}

export function sipEventLabel(event: { sip_method?: string | null; sip_response_code?: number | null; sip_response_text?: string | null }): string {
  if (event.sip_response_code) {
    return `${event.sip_response_code} ${event.sip_response_text || ""}`.trim();
  }
  return event.sip_method || "?";
}
