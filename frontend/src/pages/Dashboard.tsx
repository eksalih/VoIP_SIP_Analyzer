import { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";
import { formatDateTime, formatDuration, shortCallId } from "../utils/format";
import StatusBadge from "../components/shared/StatusBadge";
import VendorBadge from "../components/shared/VendorBadge";
import UploadPanel from "../components/calls/UploadPanel";
import ConfirmDialog from "../components/shared/ConfirmDialog";
import CaptureFileCard from "../components/calls/CaptureFileCard";
import type { Call, CallStatus, UploadResult, BatchUploadResult, CaptureFile } from "../types";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface Props {
  onSelectCall: (id: number) => void;
}

type ViewMode = "files" | "all";

const STATUS_FILTERS: (CallStatus | "ALL")[] = ["ALL", "ANSWERED", "MISSED", "REJECTED", "FAILED", "CANCELLED"];

function isBatchResult(r: UploadResult | BatchUploadResult): r is BatchUploadResult {
  return "files_processed" in r;
}

function triggerDownload(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.click();
}

export default function Dashboard({ onSelectCall }: Props) {
  const [calls, setCalls] = useState<Call[]>([]);
  const [captureFiles, setCaptureFiles] = useState<CaptureFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [filesLoading, setFilesLoading] = useState(true);
  const [filter, setFilter] = useState<CallStatus | "ALL">("ALL");
  const [vendorFilter, setVendorFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("files");
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);

  const [uploadBanner, setUploadBanner] = useState<UploadResult | BatchUploadResult | null>(null);
  const [clearedBanner, setClearedBanner] = useState<string | null>(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [fileToDelete, setFileToDelete] = useState<CaptureFile | null>(null);
  const [knownVendors, setKnownVendors] = useState<string[]>([]);

  const loadFiles = useCallback(async () => {
    setFilesLoading(true);
    try {
      const data = await api.getCaptureFiles({ limit: 200 });
      setCaptureFiles(data);
    } catch {
      setCaptureFiles([]);
    } finally {
      setFilesLoading(false);
    }
  }, []);

  // Derive the distinct vendor list from an unfiltered call fetch, so the
  // vendor dropdown options don't disappear when a status/vendor filter is active.
  const loadKnownVendors = useCallback(async () => {
    try {
      const all = await api.getCalls({ limit: 500 });
      const vendors = Array.from(new Set(all.map(c => c.vendor).filter((v): v is string => !!v))).sort();
      setKnownVendors(vendors);
    } catch {
      setKnownVendors([]);
    }
  }, []);

  const loadCalls = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getCalls({
        status: filter !== "ALL" ? filter : undefined,
        vendor: vendorFilter !== "ALL" ? vendorFilter : undefined,
        search: search || undefined,
        limit: 200,
        captureFileId: viewMode === "files" && selectedFileId ? selectedFileId : undefined,
      });
      setCalls(data);
    } catch {
      setCalls([]);
    } finally {
      setLoading(false);
    }
  }, [filter, vendorFilter, search, viewMode, selectedFileId]);

  useEffect(() => { loadFiles(); }, [loadFiles]);
  useEffect(() => { loadCalls(); }, [loadCalls]);
  useEffect(() => { loadKnownVendors(); }, [loadKnownVendors]);

  const handleUpload = async (result: UploadResult | BatchUploadResult) => {
    setUploadBanner(result);
    setClearedBanner(null);
    await Promise.all([loadFiles(), loadCalls(), loadKnownVendors()]);
    // Auto-select the newly uploaded file (single-upload case) so results are immediately visible
    if (!isBatchResult(result) && result.capture_file_id) {
      setSelectedFileId(result.capture_file_id);
      setViewMode("files");
    } else if (isBatchResult(result)) {
      setSelectedFileId(null); // show "all from this batch" by clearing the single-file filter
      setViewMode("files");
    }
  };

  const handleClearAll = async () => {
    const result = await api.clearAllData();
    setClearedBanner(
      `Cleared ${result.deleted.calls} call(s), ${result.deleted.events} event(s), ${result.deleted.test_runs} test run(s), ${result.deleted.capture_files ?? 0} capture file(s).`
    );
    setUploadBanner(null);
    setSelectedFileId(null);
    setVendorFilter("ALL");
    await Promise.all([loadFiles(), loadCalls(), loadKnownVendors()]);
  };

  const handleDeleteFile = async () => {
    if (!fileToDelete) return;
    await api.deleteCaptureFile(fileToDelete.id);
    if (selectedFileId === fileToDelete.id) setSelectedFileId(null);
    setFileToDelete(null);
    await Promise.all([loadFiles(), loadCalls(), loadKnownVendors()]);
  };

  const totalCallsAcrossFiles = captureFiles.reduce((sum, f) => sum + (f.calls_found ?? 0), 0);
  const selectedFile = captureFiles.find((f) => f.id === selectedFileId) || null;

  return (
    <div className="page">
      <div className="page-header page-header-row">
        <div>
          <h1 className="page-title">Call Log</h1>
          <p className="page-subtitle">Upload PCAP captures to analyze SIP calls</p>
        </div>
        <div className="header-actions">
          <button
            className="export-btn csv"
            onClick={() => triggerDownload(`${BASE}/export/csv`)}
            disabled={captureFiles.length === 0}
            title="Export all calls as CSV"
          >
            ↓ CSV
          </button>
          <button
            className="export-btn pdf"
            onClick={() => triggerDownload(`${BASE}/export/pdf`)}
            disabled={captureFiles.length === 0}
            title="Export PDF compatibility report"
          >
            ↓ PDF
          </button>
          <button
            className="clear-data-btn"
            onClick={() => setShowClearConfirm(true)}
            disabled={captureFiles.length === 0}
            title="Permanently delete all calls, events, capture files, and test runs"
          >
            🗑 Clear All Data
          </button>
        </div>
      </div>

      <UploadPanel onSuccess={handleUpload} />

      {clearedBanner && (
        <div className="cleared-banner">
          <strong>✓ Cleared:</strong> {clearedBanner}
        </div>
      )}

      {uploadBanner && isBatchResult(uploadBanner) && (
        <div className="upload-result-banner">
          <strong>✓ Batch processed:</strong> {uploadBanner.files_ok}/{uploadBanner.files_processed} files
          &nbsp;·&nbsp; {uploadBanner.total_calls_processed} calls from {uploadBanner.total_packets_parsed} packets
          &nbsp;·&nbsp; {uploadBanner.execution_time}s
          {uploadBanner.files_failed > 0 && (
            <span className="stat-pill rejected">{uploadBanner.files_failed} file(s) failed</span>
          )}
          <span>
            &nbsp;·&nbsp;
            <span className="stat-pill answered">{uploadBanner.combined_summary.ANSWERED ?? 0} answered</span>
            <span className="stat-pill missed">{uploadBanner.combined_summary.MISSED ?? 0} missed</span>
            <span className="stat-pill rejected">{uploadBanner.combined_summary.REJECTED ?? 0} rejected</span>
          </span>
        </div>
      )}

      {uploadBanner && !isBatchResult(uploadBanner) && uploadBanner.status === "ok" && (
        <div className="upload-result-banner">
          <strong>✓ Processed:</strong> {uploadBanner.calls_processed} calls from {uploadBanner.packets_parsed} packets
          &nbsp;·&nbsp; {uploadBanner.execution_time}s
          {uploadBanner.summary && (
            <span>
              &nbsp;·&nbsp;
              <span className="stat-pill answered">{uploadBanner.summary.ANSWERED ?? 0} answered</span>
              <span className="stat-pill missed">{uploadBanner.summary.MISSED ?? 0} missed</span>
              <span className="stat-pill rejected">{uploadBanner.summary.REJECTED ?? 0} rejected</span>
            </span>
          )}
        </div>
      )}

      {uploadBanner && !isBatchResult(uploadBanner) && uploadBanner.status === "error" && (
        <div className="upload-error-banner">
          <strong>⚠ {uploadBanner.file}:</strong> {uploadBanner.message}
        </div>
      )}

      {/* View toggle */}
      <div className="view-toggle">
        <button className={`view-tab ${viewMode === "files" ? "active" : ""}`} onClick={() => setViewMode("files")}>
          By Capture File {captureFiles.length > 0 && `(${captureFiles.length})`}
        </button>
        <button className={`view-tab ${viewMode === "all" ? "active" : ""}`} onClick={() => { setViewMode("all"); setSelectedFileId(null); }}>
          All Calls {totalCallsAcrossFiles > 0 && `(${totalCallsAcrossFiles})`}
        </button>
      </div>

      {/* Capture file grid */}
      {viewMode === "files" && (
        filesLoading ? (
          <div className="loading-state"><div className="spinner" /><span>Loading capture files…</span></div>
        ) : captureFiles.length === 0 ? (
          <div className="empty-state"><p>No capture files uploaded yet.</p></div>
        ) : (
          <div className="capture-grid">
            {captureFiles.map((f) => (
              <CaptureFileCard
                key={f.id}
                file={f}
                selected={selectedFileId === f.id}
                onClick={() => setSelectedFileId(selectedFileId === f.id ? null : f.id)}
                onDelete={() => setFileToDelete(f)}
                onLabelChange={(id, label) => {
                  setCaptureFiles(prev => prev.map(cf =>
                    cf.id === id ? { ...cf, label } : cf
                  ));
                }}
              />
            ))}
          </div>
        )
      )}

      {/* Filters */}
      <div className="filter-bar" style={{ marginTop: viewMode === "files" ? "20px" : "0" }}>
        {viewMode === "files" && selectedFile && (
          <span className="active-file-pill">
            Showing: {selectedFile.filename}
            <button onClick={() => setSelectedFileId(null)}>✕</button>
          </span>
        )}
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
        {knownVendors.length > 0 && (
          <select
            className="vendor-select"
            value={vendorFilter}
            onChange={(e) => setVendorFilter(e.target.value)}
            title="Filter by detected vendor"
          >
            <option value="ALL">All Vendors</option>
            {knownVendors.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        )}
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
          <p>
            {viewMode === "files" && selectedFileId
              ? "No calls match this filter in the selected capture file."
              : "No calls found. Upload a PCAP file to get started."}
          </p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="calls-table">
            <thead>
              <tr>
                <th>Call-ID</th>
                <th>Caller</th>
                <th>Called</th>
                <th>Vendor</th>
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
                  <td>
                    <VendorBadge vendor={call.vendor} category={call.vendor_category} />
                  </td>
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
          message={`This will permanently delete all ${totalCallsAcrossFiles} call(s) across ${captureFiles.length} capture file(s), their SIP events, and replay test history. This cannot be undone. Use this before starting a new test session.`}
          confirmLabel="Clear Everything"
          cancelLabel="Cancel"
          danger
          onConfirm={handleClearAll}
          onClose={() => setShowClearConfirm(false)}
        />
      )}

      {fileToDelete && (
        <ConfirmDialog
          title="Delete this capture file?"
          message={`This will permanently delete "${fileToDelete.filename}" and its ${fileToDelete.calls_found ?? 0} call(s). This cannot be undone.`}
          confirmLabel="Delete File"
          cancelLabel="Cancel"
          danger
          onConfirm={handleDeleteFile}
          onClose={() => setFileToDelete(null)}
        />
      )}
    </div>
  );
}
