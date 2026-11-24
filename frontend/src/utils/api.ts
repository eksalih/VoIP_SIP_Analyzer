import type { Call, Analytics, UploadResult, BatchUploadResult, CaptureFile, AuthUser, AdminUser, AuditEntry, CaptureStatus } from "../types";
import { AUTH_EXPIRED_EVENT, getToken, setToken } from "./auth";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function withAuth(opts?: RequestInit): RequestInit {
  const token = getToken();
  if (!token) return opts ?? {};
  return { ...opts, headers: { ...(opts?.headers as Record<string, string> | undefined), Authorization: `Bearer ${token}` } };
}

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, withAuth(opts));
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    setToken(null);
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  getCalls: (params?: { status?: string; search?: string; limit?: number; captureFileId?: number; vendor?: string; source?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.search) q.set("search", params.search);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.captureFileId) q.set("capture_file_id", String(params.captureFileId));
    if (params?.vendor) q.set("vendor", params.vendor);
    if (params?.source) q.set("source", params.source);
    return apiFetch<Call[]>(`/calls?${q.toString()}`);
  },

  getCaptureStatus: () => apiFetch<CaptureStatus>("/capture/status"),

  getCall: (id: number) => apiFetch<Call>(`/calls/${id}`),

  getCallEvents: (id: number) => apiFetch<Call["events"]>(`/calls/${id}/events`),

  getCallMedia: (id: number) => apiFetch<import("../types").RTPStream[]>(`/calls/${id}/media`),

  // <audio> and <a> cannot send an Authorization header, so recordings are fetched with the
  // token and played from a blob URL (v2.3.0). Seeking works because the whole file is local.
  fetchCallAudio: async (id: number, download = false): Promise<Blob> => {
    const res = await fetch(`${BASE}/calls/${id}/audio${download ? "?download=1" : ""}`, withAuth());
    if (res.status === 401) {
      setToken(null);
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.blob();
  },

  /** Authenticated file download (CSV/PDF exports): a plain link cannot send the login token. */
  downloadFile: async (path: string): Promise<void> => {
    const res = await fetch(`${BASE}${path}`, withAuth());
    if (res.status === 401) {
      setToken(null);
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const match = /filename="?([^";]+)"?/.exec(res.headers.get("Content-Disposition") || "");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = match ? match[1] : "export";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  },

  login: (username: string, password: string) =>
    apiFetch<{ token: string; user: AuthUser }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),

  listUsers: () => apiFetch<AdminUser[]>("/users"),

  createUser: (u: { username: string; password: string; display_name?: string; role: string; extensions: string[] }) =>
    apiFetch<AdminUser>("/users", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(u),
    }),

  updateUser: (id: number, patch: { display_name?: string; role?: string; extensions?: string[]; is_active?: boolean; password?: string }) =>
    apiFetch<AdminUser>(`/users/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
    }),

  deleteUser: (id: number) => apiFetch<{ deleted: number }>(`/users/${id}`, { method: "DELETE" }),

  getAudit: (params?: { action?: string; username?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.action) q.set("action", params.action);
    if (params?.username) q.set("username", params.username);
    q.set("limit", String(params?.limit ?? 200));
    return apiFetch<AuditEntry[]>(`/audit?${q.toString()}`);
  },

  me: () => apiFetch<AuthUser>("/auth/me"),

  changePassword: (current_password: string, new_password: string) =>
    apiFetch<{ status: string }>("/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password, new_password }),
    }),

  deleteCall: (id: number) => apiFetch<void>(`/calls/${id}`, { method: "DELETE" }),

  clearAllData: () => apiFetch<{ status: string; message: string; deleted: Record<string, number> }>(
    "/calls/clear-all?confirm=true",
    { method: "DELETE" }
  ),

  getAnalytics: () => apiFetch<Analytics>("/analytics"),

  uploadPcap: (file: File, expectedStatus?: string): Promise<UploadResult> => {
    const fd = new FormData();
    fd.append("file", file);
    if (expectedStatus) fd.append("expected_status", expectedStatus);
    return apiFetch<UploadResult>("/upload-pcap", { method: "POST", body: fd });
  },

  uploadPcapBatch: (files: File[], expectedStatus?: string): Promise<BatchUploadResult> => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (expectedStatus) fd.append("expected_status", expectedStatus);
    return apiFetch<BatchUploadResult>("/upload-pcap/batch", { method: "POST", body: fd });
  },

  getCaptureFiles: (params?: { limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    return apiFetch<CaptureFile[]>(`/capture-files?${q.toString()}`);
  },

  getCaptureFile: (id: number) => apiFetch<CaptureFile>(`/capture-files/${id}`),

  patchCaptureFile: (id: number, label: string | null) =>
    apiFetch<CaptureFile>(`/capture-files/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label }),
    }),

  deleteCaptureFile: (id: number) => apiFetch<void>(`/capture-files/${id}`, { method: "DELETE" }),

  replayTest: (file: File, expectedStatus: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("expected_status", expectedStatus);
    return apiFetch<any>("/replay-test", { method: "POST", body: fd });
  },

  getTestHistory: () => apiFetch<any[]>("/replay-test/history"),

  health: () => apiFetch<{ status: string; version: string; database: string }>("/health"),
};
