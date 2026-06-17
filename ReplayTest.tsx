/* ── Design tokens ─────────────────────────────────────── */
:root {
  --bg: #0d1117;
  --surface: #161b22;
  --surface2: #21262d;
  --border: #30363d;
  --text: #e6edf3;
  --text-muted: #8b949e;
  --accent: #58a6ff;
  --accent-dim: #1f6feb22;
  --green: #3fb950;
  --orange: #d29922;
  --red: #f85149;
  --blue: #58a6ff;
  --gray: #6e7681;
  --radius: 8px;
  --sidebar-w: 220px;
  --font: "Inter", system-ui, -apple-system, sans-serif;
  --mono: "JetBrains Mono", "Fira Mono", monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #root { height: 100%; }

body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
}

/* ── Layout ─────────────────────────────────────────────── */
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.app-main {
  flex: 1;
  overflow-y: auto;
  padding: 32px 36px;
}

/* ── Sidebar ─────────────────────────────────────────────── */
.sidebar {
  width: var(--sidebar-w);
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  padding: 20px 0;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px 24px;
  border-bottom: 1px solid var(--border);
}

.brand-icon { font-size: 22px; }
.brand-text {
  font-weight: 700;
  font-size: 15px;
  color: var(--text);
  letter-spacing: -0.02em;
}

.sidebar-nav {
  flex: 1;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius);
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13.5px;
  font-weight: 500;
  text-align: left;
  transition: background 0.15s, color 0.15s;
}
.nav-item:hover { background: var(--surface2); color: var(--text); }
.nav-item.active { background: var(--accent-dim); color: var(--accent); }

.nav-icon { font-size: 16px; }
.sidebar-footer { padding: 16px 20px; border-top: 1px solid var(--border); }
.version-badge { font-size: 11px; color: var(--text-muted); font-family: var(--mono); }

/* ── Page ─────────────────────────────────────────────── */
.page { max-width: 1200px; }
.page-header { margin-bottom: 24px; }
.page-title { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
.page-subtitle { color: var(--text-muted); font-size: 13px; margin-top: 4px; }

/* ── Upload zone ────────────────────────────────────────── */
.upload-zone {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  margin-bottom: 20px;
  padding: 28px;
  text-align: center;
}
.upload-zone:hover, .upload-zone.dragging {
  border-color: var(--accent);
  background: var(--accent-dim);
}
.upload-zone.loading { cursor: default; }
.upload-inner { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.upload-icon { font-size: 32px; }
.upload-primary { font-weight: 500; color: var(--text); }
.upload-secondary { font-size: 12px; color: var(--text-muted); }
.upload-error { color: var(--red); font-size: 13px; margin-top: 6px; }

/* ── Upload result banner ───────────────────────────────── */
.upload-result-banner {
  background: #1a2a1a;
  border: 1px solid #3fb95044;
  border-radius: var(--radius);
  padding: 10px 16px;
  font-size: 13px;
  color: var(--green);
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.stat-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 600;
  margin: 0 2px;
}
.stat-pill.answered { background: #1a2e1a; color: #3fb950; }
.stat-pill.missed   { background: #2e2208; color: #d29922; }
.stat-pill.rejected { background: #2e1111; color: #f85149; }

/* ── Filter bar ─────────────────────────────────────────── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.filter-tabs { display: flex; gap: 4px; }
.filter-tab {
  padding: 5px 14px;
  border-radius: 99px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s;
}
.filter-tab:hover { border-color: var(--accent); color: var(--accent); }
.filter-tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }

.search-input {
  padding: 6px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  min-width: 260px;
  outline: none;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: var(--accent); }
.search-input::placeholder { color: var(--text-muted); }

/* ── Table ──────────────────────────────────────────────── */
.table-wrap { overflow-x: auto; border-radius: var(--radius); border: 1px solid var(--border); }
.calls-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.calls-table th {
  padding: 10px 14px;
  text-align: left;
  font-weight: 600;
  font-size: 11.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
}
.calls-table td {
  padding: 11px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  vertical-align: middle;
}
.calls-table tbody tr:last-child td { border-bottom: none; }
.call-row { cursor: pointer; transition: background 0.1s; }
.call-row:hover td { background: var(--surface2); }
.call-id-cell {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--text-muted);
}

/* ── States ─────────────────────────────────────────────── */
.loading-state, .empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px;
  color: var(--text-muted);
  flex-direction: column;
}
.spinner {
  width: 20px; height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Call detail ─────────────────────────────────────────── */
.back-btn {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 13px;
  margin-bottom: 20px;
  padding: 0;
}
.back-btn:hover { text-decoration: underline; }
.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
  gap: 16px;
}
.call-id-full {
  display: block;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
  word-break: break-all;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.summary-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.summary-card.rejection { border-color: #f8514944; background: #1e1010; }
.card-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
.card-value { font-size: 15px; font-weight: 600; color: var(--text); }
.card-value.small { font-size: 12px; font-weight: 400; }
.card-sub { font-size: 11px; color: var(--text-muted); }
.detail-tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 0; }
.tab-btn {
  padding: 8px 16px;
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-panel { margin-top: 8px; }

/* ── SIP Ladder ──────────────────────────────────────────── */
.ladder-container {
  font-size: 12px;
  font-family: var(--mono);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  overflow-x: auto;
}
.ladder-empty { color: var(--text-muted); padding: 32px; text-align: center; }
.ladder-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
  font-weight: 700;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
.ladder-endpoint { display: flex; align-items: center; gap: 6px; }
.endpoint-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg);
  box-shadow: 0 0 0 2px var(--accent);
}
.ladder-spacer { flex: 1; }
.ladder-body { position: relative; }
.ladder-line {
  position: absolute;
  top: 0; bottom: 0;
  width: 2px;
  background: var(--border);
}
.ladder-line.left { left: 64px; }
.ladder-line.right { right: 64px; }
.ladder-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  position: relative;
}
.ladder-time {
  width: 60px;
  font-size: 10px;
  color: var(--text-muted);
  flex-shrink: 0;
  text-align: right;
}
.ladder-arrow-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  position: relative;
}
.arrow-line {
  flex: 1;
  height: 0;
  border-top: 2px solid;
  position: relative;
}
.arrow-label {
  position: absolute;
  top: -18px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10.5px;
  font-weight: 600;
  white-space: nowrap;
  background: var(--surface);
  padding: 0 4px;
}
.arrow-head {
  width: 0; height: 0;
  border-top: 6px solid transparent;
  border-bottom: 6px solid transparent;
}
.arrow-head.right { border-left: 8px solid; border-right: none; }
.arrow-head.left  { border-right: 8px solid; border-left: none; }
.left-to-right .arrow-head { order: 10; }
.right-to-left .arrow-head { order: -1; }
.right-to-left .arrow-line { direction: rtl; }
.ladder-seq {
  width: 28px;
  font-size: 10px;
  color: var(--text-muted);
  text-align: left;
}

/* ── Raw messages ────────────────────────────────────────── */
.raw-message-block {
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.raw-message-header {
  background: var(--surface2);
  padding: 8px 14px;
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
}
.raw-ips { margin-left: auto; color: var(--text-muted); font-family: var(--mono); font-size: 11px; }
.raw-message-body {
  background: var(--bg);
  padding: 12px 16px;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--text);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

/* ── Modal ───────────────────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: #000a;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal-box {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: 90%;
  max-width: 800px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}
.modal-header button {
  background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px;
}
.modal-body {
  padding: 16px;
  font-family: var(--mono);
  font-size: 12px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  flex: 1;
}

/* ── Analytics ───────────────────────────────────────────── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.kpi-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kpi-card.answered { border-color: #3fb95033; }
.kpi-card.missed   { border-color: #d2992233; }
.kpi-card.rejected { border-color: #f8514933; }
.kpi-card.failed   { border-color: var(--border); }
.kpi-value { font-size: 26px; font-weight: 700; letter-spacing: -0.03em; color: var(--text); }
.kpi-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
@media (max-width: 768px) { .charts-grid { grid-template-columns: 1fr; } }

.chart-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.chart-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.bar-label { width: 80px; font-size: 11.5px; color: var(--text-muted); flex-shrink: 0; }
.bar-track { flex: 1; background: var(--surface2); border-radius: 4px; height: 14px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; min-width: 4px; }
.bar-count { width: 32px; text-align: right; font-size: 12px; color: var(--text-muted); }
.day-chart { display: flex; align-items: flex-end; gap: 4px; height: 130px; }
.day-bar-col { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; }
.day-bar { width: 100%; background: var(--accent); border-radius: 3px 3px 0 0; min-width: 4px; transition: height 0.5s; }
.day-label { font-size: 9px; color: var(--text-muted); writing-mode: vertical-rl; transform: rotate(180deg); }

/* ── Replay test ─────────────────────────────────────────── */
.replay-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-bottom: 24px;
}
.form-row { display: flex; flex-direction: column; gap: 8px; }
.form-label { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
.file-picker {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
  transition: border-color 0.15s;
}
.file-picker:hover { border-color: var(--accent); }
.file-icon { font-size: 18px; }
.status-selector { display: flex; gap: 8px; flex-wrap: wrap; }
.status-option {
  padding: 7px 16px;
  border-radius: 99px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.15s;
}
.status-option:hover { border-color: var(--accent); color: var(--accent); }
.status-option.selected { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
.run-btn {
  align-self: flex-start;
  padding: 10px 28px;
  background: var(--accent);
  color: #0d1117;
  border: none;
  border-radius: var(--radius);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.15s;
}
.run-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.run-btn:not(:disabled):hover { opacity: 0.88; }
.replay-error { color: var(--red); font-size: 13px; }
.result-panel { margin-top: 8px; }
.result-header {
  padding: 12px 16px;
  border-radius: var(--radius);
  display: flex;
  gap: 16px;
  align-items: center;
  font-size: 13px;
}
.result-header.pass { background: #1a2e1a; border: 1px solid #3fb95044; color: var(--green); }
.result-header.fail { background: #2e1111; border: 1px solid #f8514944; color: var(--red); }
.result-verdict { font-size: 18px; font-weight: 700; }
.result-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.result-badge.pass { background: #1a2e1a; color: var(--green); }
.result-badge.fail { background: #2e1111; color: var(--red); }
