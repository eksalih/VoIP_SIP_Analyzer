import { useCallback, useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard";
import CallDetail from "./pages/CallDetail";
import Analytics from "./pages/Analytics";
import ReplayTest from "./pages/ReplayTest";
import Login from "./pages/Login";
import Users from "./pages/Users";
import Audit from "./pages/Audit";
import Sidebar from "./components/shared/Sidebar";
import { api } from "./utils/api";
import { AUTH_EXPIRED_EVENT, can, getToken, setToken } from "./utils/auth";
import { AuthContext } from "./utils/AuthContext";
import type { AuthUser } from "./types";
import "./App.css";

export type Page = "dashboard" | "analytics" | "replay" | "users" | "audit";

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(() => getToken() !== null);
  const [notice, setNotice] = useState<string | undefined>();
  const [page, setPage] = useState<Page>("dashboard");
  const [selectedCallId, setSelectedCallId] = useState<number | null>(null);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setSelectedCallId(null);
    setPage("dashboard");
  }, []);

  // Restore the session from a saved token
  useEffect(() => {
    if (!getToken()) return;
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setChecking(false));
  }, []);

  // The server rejected our token (expired / account disabled)
  useEffect(() => {
    const onExpired = () => { logout(); setNotice("Your session has ended. Please sign in again."); };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [logout]);

  if (checking) return null;
  if (!user) {
    return <Login notice={notice} onLoggedIn={(u) => { setNotice(undefined); setUser(u); }} />;
  }

  // Pages a role may not use are never offered; fall back to the call log.
  const allowed: Page[] = ["dashboard"];
  if (can(user, "calls.view_all")) allowed.push("analytics");
  if (can(user, "analysis.use")) allowed.push("replay");
  if (can(user, "users.manage")) allowed.push("users");
  if (can(user, "audit.view")) allowed.push("audit");
  const current: Page = allowed.includes(page) ? page : "dashboard";

  return (
    <AuthContext.Provider value={{ user, logout }}>
      <div className="app-layout">
        <Sidebar
          currentPage={current}
          allowedPages={allowed}
          onNavigate={(p) => { setPage(p); setSelectedCallId(null); }}
        />
        <main className="app-main">
          {current === "dashboard" && selectedCallId === null && <Dashboard onSelectCall={setSelectedCallId} />}
          {current === "dashboard" && selectedCallId !== null && (
            <CallDetail callId={selectedCallId} onBack={() => setSelectedCallId(null)} />
          )}
          {current === "analytics" && <Analytics />}
          {current === "replay" && <ReplayTest />}
          {current === "users" && <Users />}
          {current === "audit" && (
            <Audit onSelectCall={(id) => { setSelectedCallId(id); setPage("dashboard"); }} />
          )}
        </main>
      </div>
    </AuthContext.Provider>
  );
}
