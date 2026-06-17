import { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";
import { formatDateTime, formatDuration, shortCallId } from "../utils/format";
import StatusBadge from "../components/shared/StatusBadge";
import UploadPanel from "../components/calls/UploadPanel";
import ConfirmDialog from "../components/shared/ConfirmDialog";
import type { Call, CallStatus, UploadResult } from "../types";

interface Props {
  onSelectCall: (id: number) => void;
}

const STATUS_FILTERS: (CallStatus | "ALL")[] = ["ALL", "ANSWERED", "MISSED", "REJECTED", "FAILED", "CANCELLED"];

export default function Dashboard({ onSelectCall }: Props) {
  const [calls, setCalls] = useState<Call[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<CallStatus | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearedBanner, setClearedBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getCalls({
        status: filter !== "ALL" ? filter : undefined,
        search: search || undefined,
        limit: 200,
      });
      setCalls(data);
    } catch {
      setCalls([]);
    } finally {
      setLoading(false);
    }
  }, [filter, search]);

  useEffect(() => { load(); }, [load]);

  const handleUpload = async (result: UploadResult) => {
    setUploadResult(result);
    setClearedBanner(null);
    await load();
  };

  const handleClearAll = async () => {
    const result = await api.clearAllData();
    setClearedBanner(
      `Cleared ${result.deleted.calls} call(s), ${result.deleted.events} event(s), ${result.deleted.test_runs} test run(s).`
    );
    setUploadResult(null);
    await load();
  };

  return (
    <div className="page">
      <div className="page-header page-header-row">
        <div>
          <h1 className="page-title">Call Log</h1>
          <p className="page-subtitle">Upload a PCAP capture to analyze SIP calls</p>
        </div>
        <button
          className="clear-data-btn"
          onClick={() => setShowClearConfirm(true)}
          disabled={calls.length === 0 && !uploadResult}
          title="Permanently delete all calls, events, and test runs"
        >
          🗑 Clear All Data
        </button>
      </div>

      <UploadPanel onSuccess={handleUpload} />

      {clearedBanner && (
        <div className="cleared-banner">
          <strong>✓ Cleared:</strong> {clearedBanner}
        </div>
      )}

      {uploadResult && uploadResult.status === "ok" && (
        <div className="upload-result-banner">
          <strong>✓ Processed:</strong> {uploadResult.calls_processed} calls from {uploadResult.packets_parsed} packets
          &nbsp;·&nbsp; {uploadResult.execution_time}s
          {uploadResult.summary && (
            <span>
              &nbsp;·&nbsp;
              <span className="stat-pill answered">{uploadResult.summary.ANSWERED ?? 0} answered</span>
              <span className="stat-pill missed">{uploadResult.summary.MISSED ?? 0} missed</span>
              <span className="stat-pill rejected">{uploadResult.summary.REJECTED ?? 0} rejected</span>
            </span>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="filter-bar">
        <div className="filter-tabs">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              className={`filter-tab ${filter === s ? "active" : ""}`}
              onClick={() => setFilter(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <input
          className="search-input"
          placeholder="Search caller, called, or Call-ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Table */}
      {loading ? (
        <div className="loading-state">
          <div className="spinner" />
          <span>Loading calls…</span>
        </div>
      ) : calls.length === 0 ? (
        <div className="empty-state">
          <p>No calls found. Upload a PCAP file to get started.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="calls-table">
            <thead>
              <tr>
                <th>Call-ID</th>
                <th>Caller</th>
                <th>Called</th>
                <th>Start Time</th>
                <th>Ring</th>
                <th>Talk</th>
                <th>Status</th>
                <th>SIP Code</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((call) => (
                <tr
                  key={call.id}
                  className="call-row"
                  onClick={() => onSelectCall(call.id)}
                >
                  <td className="call-id-cell" title={call.call_id}>
                    {shortCallId(call.call_id)}
                  </td>
                  <td>{call.caller || "—"}</td>
                  <td>{call.called || "—"}</td>
                  <td>{formatDateTime(call.start_time)}</td>
                  <td>{formatDuration(call.ring_duration)}</td>
                  <td>{formatDuration(call.talk_duration)}</td>
                  <td><StatusBadge status={call.status} /></td>
                  <td>{call.sip_result_code ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showClearConfirm && (
        <ConfirmDialog
          title="Clear all call data?"
          message={`This will permanently delete all ${calls.length} call(s), their SIP events, and replay test history. This cannot be undone. Use this before starting a new test session.`}
          confirmLabel="Clear Everything"
          cancelLabel="Cancel"
          danger
          onConfirm={handleClearAll}
          onClose={() => setShowClearConfirm(false)}
        />
      )}
    </div>
  );
}
