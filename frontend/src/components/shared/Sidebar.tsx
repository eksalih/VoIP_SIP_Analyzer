import { useEffect, useState } from "react";
import type { Page } from "../../App";
import { api } from "../../utils/api";
import { useAuth } from "../../utils/AuthContext";
import "../../App.css";

interface Props {
  currentPage: Page;
  onNavigate: (p: Page) => void;
  allowedPages: Page[];
}

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: "dashboard", label: "Call Log",    icon: "📋" },
  { id: "analytics", label: "Analytics",  icon: "📊" },
  { id: "replay",    label: "Replay Test", icon: "🔁" },
];

export default function Sidebar({ currentPage, onNavigate, allowedPages }: Props) {
  const { user, logout } = useAuth();
  // Show the version the backend actually reports, so the badge can never drift
  // from the running build. Fallback is shown until /health answers (or if it fails).
  const [version, setVersion] = useState("v2.2.0");
  useEffect(() => {
    api.health().then((h) => h.version && setVersion(`v${h.version}`)).catch(() => {});
  }, []);

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-icon">📡</span>
        <span className="brand-text">SIP Analyzer</span>
      </div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.filter((i) => allowedPages.includes(i.id)).map((item) => (
          <button
            key={item.id}
            className={`nav-item ${currentPage === item.id ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-user">
        <div>{user.display_name || user.username}</div>
        <div className="role">{user.role}</div>
        <div style={{ marginTop: 6 }}>
          <button onClick={logout}>Sign out</button>
        </div>
      </div>
      <div className="sidebar-footer">
        <span className="version-badge">{version}</span>
      </div>
    </aside>
  );
}
