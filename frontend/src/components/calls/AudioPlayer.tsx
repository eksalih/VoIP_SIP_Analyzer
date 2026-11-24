import { useEffect, useRef, useState } from "react";
import { api } from "../../utils/api";
import { useAuth } from "../../utils/AuthContext";

interface Props {
  callId: number;
  status: string;
  hasAudio: boolean;
  codec: string | null;
  duration: number | null;
}

const SPEEDS = [0.5, 1, 1.5, 2];

/**
 * Playback for a recorded call. The browser's <audio> element cannot send the login
 * token, so the recording is fetched with it and played from a local blob URL.
 * It loads when the user presses Play, not when the page opens, so browsing calls
 * never downloads audio and every playback is a deliberate (and audit-logged) action.
 */
export default function AudioPlayer({ callId, status, hasAudio, codec, duration }: Props) {
  const { can } = useAuth();
  const audioRef = useRef<HTMLAudioElement>(null);
  const [speed, setSpeed] = useState(1);
  const [src, setSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Free the blob and reset when switching calls or leaving the page
  useEffect(() => {
    return () => { if (src) URL.revokeObjectURL(src); };
  }, [src]);
  useEffect(() => { setSrc(null); setError(null); }, [callId]);

  if (!hasAudio) {
    if (status !== "ANSWERED") return null;
    return (
      <div className="audio-player audio-empty">
        <strong>No recording for this call.</strong>
        <div style={{ opacity: 0.8, marginTop: 4, fontSize: 13 }}>
          Recordings exist when recording was enabled, the media was captured, the codec is
          G.711 (PCMU/PCMA), and the recording has not been removed by retention cleanup.
        </div>
      </div>
    );
  }

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const blob = await api.fetchCallAudio(callId);
      setSrc(URL.createObjectURL(blob));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the recording");
    } finally {
      setLoading(false);
    }
  };

  const download = async () => {
    try {
      const blob = await api.fetchCallAudio(callId, true);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `call_${callId}.wav`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    }
  };

  const changeSpeed = (s: number) => {
    if (audioRef.current) audioRef.current.playbackRate = s;
    setSpeed(s);
  };

  return (
    <div className="audio-player" style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 13, marginBottom: 6, opacity: 0.8 }}>
        Recording · {codec}
        {duration != null && ` · ${duration}s`}
        {" · caller left channel, callee right channel"}
      </div>

      {src ? (
        <audio
          ref={audioRef}
          controls
          autoPlay
          src={src}
          style={{ width: "100%" }}
          onLoadedMetadata={() => { if (audioRef.current) audioRef.current.playbackRate = speed; }}
        />
      ) : (
        <button className="export-btn" onClick={load} disabled={loading}>
          {loading ? "Loading recording…" : "▶ Play recording"}
        </button>
      )}

      {error && <div style={{ color: "#f44336", fontSize: 13, marginTop: 6 }}>{error}</div>}

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8, fontSize: 13 }}>
        <span style={{ opacity: 0.8 }}>Speed:</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            className={`tab-btn${speed === s ? " active" : ""}`}
            style={{ padding: "2px 10px" }}
            onClick={() => changeSpeed(s)}
          >
            {s}x
          </button>
        ))}
        {can("recordings.download") && (
          <button className="export-btn" style={{ marginLeft: "auto" }} onClick={download}>
            Download WAV
          </button>
        )}
      </div>
    </div>
  );
}
