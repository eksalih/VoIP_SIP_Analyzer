import { useRef, useState } from "react";
import { api } from "../../utils/api";

interface Props {
  callId: number;
  status: string;
  hasAudio: boolean;
  codec: string | null;
  duration: number | null;
}

const SPEEDS = [0.5, 1, 1.5, 2];

/**
 * Playback for audio reconstructed from a call's RTP (v2.2.0).
 * The audio URL is built from the API base URL (VITE_API_URL), never a bare
 * relative path — a relative path would resolve against the frontend's own
 * origin and silently fail to load.
 */
export default function AudioPlayer({ callId, status, hasAudio, codec, duration }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [speed, setSpeed] = useState(1);
  const [loadError, setLoadError] = useState(false);

  if (!hasAudio) {
    // Only answered calls can have audio; stay quiet for the rest.
    if (status !== "ANSWERED") return null;
    return (
      <div className="audio-player audio-empty">
        <strong>No audio saved for this call.</strong>
        <div style={{ opacity: 0.8, marginTop: 4, fontSize: 13 }}>
          Audio is only reconstructed when <code>SAVE_CALL_AUDIO=true</code> is set on the server
          (then re-upload the capture), the capture contains RTP for this call, and the codec is
          G.711 (PCMU/PCMA).
        </div>
      </div>
    );
  }

  const url = api.callAudioUrl(callId);

  const changeSpeed = (s: number) => {
    if (audioRef.current) audioRef.current.playbackRate = s;
    setSpeed(s);
  };

  return (
    <div className="audio-player" style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 13, marginBottom: 6, opacity: 0.8 }}>
        Reconstructed audio · {codec}
        {duration != null && ` · ${duration}s`}
        {" · caller left channel, callee right channel"}
      </div>

      <audio
        ref={audioRef}
        controls
        preload="metadata"
        src={url}
        style={{ width: "100%" }}
        onError={() => setLoadError(true)}
        onLoadedData={() => setLoadError(false)}
      />

      {loadError && (
        <div style={{ color: "#f44336", fontSize: 13, marginTop: 6 }}>
          Could not load the audio from the server ({url}). Check that the backend is reachable
          from this browser.
        </div>
      )}

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
        <a href={url} download={`call_${callId}.wav`} style={{ marginLeft: "auto" }}>
          Download WAV
        </a>
      </div>
    </div>
  );
}
