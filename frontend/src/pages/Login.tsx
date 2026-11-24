import { useState } from "react";
import { api } from "../utils/api";
import { setToken } from "../utils/auth";
import type { AuthUser } from "../types";

interface Props {
  onLoggedIn: (user: AuthUser) => void;
  notice?: string;
}

export default function Login({ onLoggedIn, notice }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { token, user } = await api.login(username.trim(), password);
      setToken(token);
      onLoggedIn(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">📡 SIP Analyzer</div>
        {notice && <div className="login-notice">{notice}</div>}
        <label>
          Username
          <input className="search-input" autoFocus autoComplete="username"
                 value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          Password
          <input className="search-input" type="password" autoComplete="current-password"
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="login-error">{error}</div>}
        <button className="export-btn login-btn" type="submit" disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
