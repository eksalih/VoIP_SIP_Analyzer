import { useCallback, useEffect, useState } from "react";
import { api } from "../utils/api";
import { useAuth } from "../utils/AuthContext";
import { formatDateTime } from "../utils/format";
import ConfirmDialog from "../components/shared/ConfirmDialog";
import type { AdminUser } from "../types";

const ROLES = [
  { id: "admin", label: "Admin", help: "Everything, including users, settings and deleting" },
  { id: "supervisor", label: "Supervisor", help: "All calls; play and download recordings" },
  { id: "user", label: "User", help: "Only calls of their own extensions; play recordings" },
];

interface DialogProps {
  existing: AdminUser | null;       // null = create
  onClose: () => void;
  onSaved: () => void;
}

function UserDialog({ existing, onClose, onSaved }: DialogProps) {
  const [username, setUsername] = useState(existing?.username ?? "");
  const [displayName, setDisplayName] = useState(existing?.display_name ?? "");
  const [role, setRole] = useState<string>(existing?.role ?? "user");
  const [extensions, setExtensions] = useState((existing?.extensions ?? []).join(", "));
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const exts = extensions.split(",").map((e) => e.trim()).filter(Boolean);
  const pwOk = existing ? password === "" || password.length >= 8 : password.length >= 8;
  const valid = (existing || username.trim() !== "") && pwOk;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (existing) {
        await api.updateUser(existing.id, {
          display_name: displayName, role, extensions: exts,
          ...(password ? { password } : {}),
        });
      } else {
        await api.createUser({ username: username.trim(), password, display_name: displayName || undefined, role, extensions: exts });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="modal-box form-box" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="modal-header">
          <span>{existing ? `Edit ${existing.username}` : "New user"}</span>
          <button type="button" onClick={onClose}>✕</button>
        </div>
        <div className="form-body">
          {!existing && (
            <label>Username
              <input className="search-input" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
          )}
          <label>Display name
            <input className="search-input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <label>Role
            <select className="search-input" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
            <span className="form-help">{ROLES.find((r) => r.id === role)?.help}</span>
          </label>
          {role === "user" && (
            <label>Extensions (comma separated)
              <input className="search-input" placeholder="1001, 1002" value={extensions}
                     onChange={(e) => setExtensions(e.target.value)} />
              <span className="form-help">The user sees calls to or from these extensions only.</span>
            </label>
          )}
          <label>{existing ? "New password (leave empty to keep)" : "Password (at least 8 characters)"}
            <input className="search-input" type="password" autoComplete="new-password"
                   value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <div className="login-error">{error}</div>}
          <button className="export-btn" type="submit" disabled={!valid || busy}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null);
  const [toDelete, setToDelete] = useState<AdminUser | null>(null);

  const load = useCallback(async () => {
    try { setUsers(await api.listUsers()); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load users"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggleActive = async (u: AdminUser) => {
    try { await api.updateUser(u.id, { is_active: !u.is_active }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not update"); }
  };

  return (
    <div className="page">
      <div className="page-header page-header-row">
        <div>
          <h1 className="page-title">Users</h1>
          <p className="page-subtitle">Accounts, roles and the extensions each user may see</p>
        </div>
        <div className="header-actions">
          <button className="export-btn" onClick={() => setEditing("new")}>+ New user</button>
        </div>
      </div>

      {error && <div className="upload-error-banner">{error}</div>}

      <div className="table-wrap">
        <table className="calls-table">
          <thead>
            <tr><th>Username</th><th>Name</th><th>Role</th><th>Extensions</th><th>Last login</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}{u.id === me.id && " (you)"}</td>
                <td>{u.display_name || "—"}</td>
                <td style={{ textTransform: "capitalize" }}>{u.role}</td>
                <td>{u.role === "user" ? (u.extensions.join(", ") || "none") : "all"}</td>
                <td>{u.last_login ? formatDateTime(u.last_login) : "never"}</td>
                <td>{u.is_active ? "Active" : "Disabled"}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="capture-card-action-btn" onClick={() => setEditing(u)}>Edit</button>{" "}
                  {u.id !== me.id && (
                    <>
                      <button className="capture-card-action-btn" onClick={() => toggleActive(u)}>
                        {u.is_active ? "Disable" : "Enable"}
                      </button>{" "}
                      <button className="capture-card-action-btn pdf" onClick={() => setToDelete(u)}>Delete</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <UserDialog existing={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={load} />
      )}
      {toDelete && (
        <ConfirmDialog
          title="Delete user"
          message={`Delete "${toDelete.username}"? Their past activity stays in the audit log. This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={async () => { await api.deleteUser(toDelete.id); await load(); }}
          onClose={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
