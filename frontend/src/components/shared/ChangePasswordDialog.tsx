import { useState } from "react";
import { api } from "../../utils/api";

export default function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const mismatch = again !== "" && next !== again;
  const valid = current !== "" && next.length >= 8 && next === again;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(current, next);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="modal-box form-box" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="modal-header"><span>Change password</span><button type="button" onClick={onClose}>✕</button></div>
        <div className="form-body">
          {done ? (
            <>
              <div>Your password was changed.</div>
              <button type="button" className="export-btn" onClick={onClose}>Close</button>
            </>
          ) : (
            <>
              <label>Current password
                <input className="search-input" type="password" autoComplete="current-password" autoFocus
                       value={current} onChange={(e) => setCurrent(e.target.value)} />
              </label>
              <label>New password (at least 8 characters)
                <input className="search-input" type="password" autoComplete="new-password"
                       value={next} onChange={(e) => setNext(e.target.value)} />
              </label>
              <label>Repeat new password
                <input className="search-input" type="password" autoComplete="new-password"
                       value={again} onChange={(e) => setAgain(e.target.value)} />
              </label>
              {mismatch && <div className="login-error">The passwords do not match.</div>}
              {error && <div className="login-error">{error}</div>}
              <button className="export-btn" type="submit" disabled={!valid || busy}>
                {busy ? "Saving…" : "Change password"}
              </button>
            </>
          )}
        </div>
      </form>
    </div>
  );
}
