import { useState, useRef } from "react";
import { api } from "../utils/api";

type StatusOption = "ANSWERED" | "MISSED" | "REJECTED" | "CANCELLED" | "FAILED";
const STATUS_OPTIONS: StatusOption[] = ["ANSWERED", "MISSED", "REJECTED", "CANCELLED", "FAILED"];

interface TestResult {
  file: string;
  expected_status: string;
  calls_tested: number;
  passed: number;
  failed: number;
  pass_rate: number;
  execution_time: number;
  results: { call_id: string; expected: string; detected: string; result: string }[];
}

export default function ReplayTest() {
  const [file, setFile] = useState<File | null>(null);
  const [expected, setExpected] = useState<StatusOption>("ANSWERED");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleRun = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.replayTest(file, expected);
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Test failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Replay Test</h1>
        <p className="page-subtitle">Upload a PCAP, declare the expected outcome, and validate your classification engine.</p>
      </div>

      <div className="replay-panel">
        <div className="form-row">
          <label className="form-label">PCAP File</label>
          <div className="file-picker" onClick={() => inputRef.current?.click()}>
            <input
              ref={inputRef}
              type="file"
              accept=".pcap,.pcapng,.cap"
              style={{ display: "none" }}
              onChange={(e) => { setFile(e.target.files?.[0] || null); e.target.value = ""; }}
            />
            <span className="file-icon">📂</span>
            <span>{file ? file.name : "Choose .pcap / .pcapng"}</span>
          </div>
        </div>

        <div className="form-row">
          <label className="form-label">Expected Call Status</label>
          <div className="status-selector">
            {STATUS_OPTIONS.map((s) => (
              <button
                key={s}
                className={`status-option ${expected === s ? "selected" : ""}`}
                onClick={() => setExpected(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <button
          className="run-btn"
          disabled={!file || loading}
          onClick={handleRun}
        >
          {loading ? "Running…" : "▶ Run Test"}
        </button>

        {error && <div className="replay-error">{error}</div>}
      </div>

      {result && (
        <div className="result-panel">
          <div className={`result-header ${result.failed === 0 ? "pass" : "fail"}`}>
            <span className="result-verdict">{result.failed === 0 ? "✓ PASS" : "✗ FAIL"}</span>
            <span>{result.passed}/{result.calls_tested} calls passed · {result.pass_rate}% · {result.execution_time}s</span>
          </div>

          <table className="calls-table" style={{ marginTop: "16px" }}>
            <thead>
              <tr>
                <th>Call-ID</th>
                <th>Expected</th>
                <th>Detected</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {result.results.map((r, i) => (
                <tr key={i}>
                  <td style={{ fontSize: "12px", fontFamily: "monospace" }}>
                    {r.call_id.length > 28 ? r.call_id.slice(0, 14) + "…" + r.call_id.slice(-10) : r.call_id}
                  </td>
                  <td>{r.expected}</td>
                  <td>{r.detected}</td>
                  <td>
                    <span className={`result-badge ${r.result === "PASS" ? "pass" : "fail"}`}>
                      {r.result}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
