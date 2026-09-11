import { useState, useEffect } from "react";
import { api } from "../../utils/api";
import type { Recording } from "../../types";
import "./AudioRecordings.css";

interface Props {
  callId: number;
}

export default function AudioRecordings({ callId }: Props) {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getRecordings(callId)
      .then((data) => {
        setRecordings(data.recordings || []);
        if (!data.recordings || data.recordings.length === 0) {
          setError("No audio recordings available for this call");
        }
      })
      .catch((err) => {
        setError(err.message || "Failed to load recordings");
        setRecordings([]);
      })
      .finally(() => setLoading(false));
  }, [callId]);

  if (loading) {
    return (
      <div className="recordings-container">
        <div className="loading-state">
          <div className="spinner" />
          <span>Loading recordings…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="recordings-container">
        <div className="empty-state">
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (recordings.length === 0) {
    return (
      <div className="recordings-container">
        <div className="empty-state">
          <p>No audio recordings reconstructed from this call's RTP streams.</p>
          <p className="hint">Only answered calls with G.711 audio (µ-law/A-law) are supported in v2.2.0.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="recordings-container">
      <div className="recordings-list">
        {recordings.map((rec) => (
          <div key={rec.id} className={`recording-item recording-${rec.status.toLowerCase()}`}>
            <div className="recording-header">
              <div className="recording-info">
                <span className="recording-direction">{rec.direction}</span>
                <span className={`recording-status status-${rec.status.toLowerCase()}`}>
                  {rec.status}
                </span>
                {rec.codec && <span className="recording-codec">{rec.codec}</span>}
              </div>
              {rec.status === "SUCCESS" || rec.status === "PARTIAL" ? (
                <a href={rec.download_url} className="download-btn" download>
                  ↓ Download
                </a>
              ) : (
                <span className="download-btn disabled">Unavailable</span>
              )}
            </div>

            <div className="recording-meta">
              {rec.duration_seconds !== null && (
                <div className="meta-item">
                  <span className="meta-label">Duration:</span>
                  <span className="meta-value">{rec.duration_seconds.toFixed(2)}s</span>
                </div>
              )}
              {rec.file_size_bytes !== null && (
                <div className="meta-item">
                  <span className="meta-label">Size:</span>
                  <span className="meta-value">{(rec.file_size_bytes / 1024).toFixed(1)} KB</span>
                </div>
              )}
              <div className="meta-item">
                <span className="meta-label">Packets:</span>
                <span className="meta-value">
                  {rec.packets_used}
                  {rec.packets_missing > 0 ? ` (${rec.packets_missing} missing)` : " ✓"}
                </span>
              </div>
            </div>

            {/* Inline player for successful recordings */}
            {(rec.status === "SUCCESS" || rec.status === "PARTIAL") && (
              <audio controls className="recording-player">
                <source src={rec.download_url} type="audio/wav" />
                Your browser does not support the audio element.
              </audio>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
