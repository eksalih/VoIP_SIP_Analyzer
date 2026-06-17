import type { Call, Analytics, UploadResult } from "../types";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  getCalls: (params?: { status?: string; search?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.search) q.set("search", params.search);
    if (params?.limit) q.set("limit", String(params.limit));
    return apiFetch<Call[]>(`/calls?${q.toString()}`);
  },

  getCall: (id: number) => apiFetch<Call>(`/calls/${id}`),

  getCallEvents: (id: number) => apiFetch<Call["events"]>(`/calls/${id}/events`),

  deleteCall: (id: number) => apiFetch<void>(`/calls/${id}`, { method: "DELETE" }),

  getAnalytics: () => apiFetch<Analytics>("/analytics"),

  uploadPcap: (file: File, expectedStatus?: string): Promise<UploadResult> => {
    const fd = new FormData();
    fd.append("file", file);
    if (expectedStatus) fd.append("expected_status", expectedStatus);
    return apiFetch<UploadResult>("/upload-pcap", { method: "POST", body: fd });
  },

  replayTest: (file: File, expectedStatus: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("expected_status", expectedStatus);
    return apiFetch<any>("/replay-test", { method: "POST", body: fd });
  },

  getTestHistory: () => apiFetch<any[]>("/replay-test/history"),

  health: () => apiFetch<{ status: string; version: string; database: string }>("/health"),
};
