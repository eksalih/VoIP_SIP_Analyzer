import { useCallback, useEffect, useState } from "react";
import { api } from "../utils/api";
import { formatDateTime } from "../utils/format";
import type { AuditEntry } from "../types";

const ACTIONS = [
  "recording.play", "recording.download", "call.delete", "calls.clear_all", "capture_file.delete",
  "login", "login_failed", "user.create", "user.update", "user.delete", "password.change",
];

export default function Audit({ onSelectCall }: { onSelectCall: (id: number) => void }) {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [action, setAction] = useState("");
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await api.getAudit({ action: action || undefined, username: username.trim() || undefined }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the audit log");
    } finally {
      setLoading(false);
    }
  }, [action, username]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="page">
      <div className="page-header page-header-row">
        <div>
          <h1 className="page-title">Audit log</h1>
          <p className="page-subtitle">Who played or downloaded recordings, deleted data, and signed in (latest 200)</p>
        </div>
        <div className="header-actions">
          <button className="export-btn" onClick={load}>↻ Refresh</button>
        </div>
      </div>

      <div className="filter-bar">
        <select className="search-input" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">All actions</option>
          {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <input className="search-input" placeholder="Filter by username" value={username}
               onChange={(e) => setUsername(e.target.value)} />
      </div>

      {error && <div className="upload-error-banner">{error}</div>}
      {loading ? (
        <div className="loading-state"><div className="spinner" /><span>Loading…</span></div>
      ) : rows.length === 0 ? (
        <div className="empty-state"><p>No matching entries.</p></div>
      ) : (
        <div className="table-wrap">
          <table className="calls-table">
            <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Call</th><th>From</th><th>Detail</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.timestamp ? formatDateTime(r.timestamp) : "—"}</td>
                  <td>{r.username || "—"}</td>
                  <td>{r.action}</td>
                  <td>
                    {r.call_id != null
                      ? <a href="#" onClick={(e) => { e.preventDefault(); onSelectCall(r.call_id!); }}>#{r.call_id}</a>
                      : "—"}
                  </td>
                  <td>{r.ip || "—"}</td>
                  <td>{r.detail || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
