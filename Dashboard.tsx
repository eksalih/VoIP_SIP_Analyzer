import { useState } from "react";
import Dashboard from "./pages/Dashboard";
import CallDetail from "./pages/CallDetail";
import Analytics from "./pages/Analytics";
import ReplayTest from "./pages/ReplayTest";
import Sidebar from "./components/shared/Sidebar";
import "./App.css";

export type Page = "dashboard" | "analytics" | "replay";

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [selectedCallId, setSelectedCallId] = useState<number | null>(null);

  const handleSelectCall = (id: number) => setSelectedCallId(id);
  const handleBack = () => setSelectedCallId(null);

  return (
    <div className="app-layout">
      <Sidebar currentPage={page} onNavigate={(p) => { setPage(p); setSelectedCallId(null); }} />
      <main className="app-main">
        {page === "dashboard" && !selectedCallId && (
          <Dashboard onSelectCall={handleSelectCall} />
        )}
        {page === "dashboard" && selectedCallId !== null && (
          <CallDetail callId={selectedCallId} onBack={handleBack} />
        )}
        {page === "analytics" && <Analytics />}
        {page === "replay" && <ReplayTest />}
      </main>
    </div>
  );
}
