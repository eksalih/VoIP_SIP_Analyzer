import type { Page } from "../../App";
import "../../App.css";

interface Props {
  currentPage: Page;
  onNavigate: (p: Page) => void;
}

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: "dashboard", label: "Call Log",    icon: "📋" },
  { id: "analytics", label: "Analytics",  icon: "📊" },
  { id: "replay",    label: "Replay Test", icon: "🔁" },
];

export default function Sidebar({ currentPage, onNavigate }: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-icon">📡</span>
        <span className="brand-text">SIP Analyzer</span>
      </div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
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
      <div className="sidebar-footer">
        <span className="version-badge">v1.0.0</span>
      </div>
    </aside>
  );
}
