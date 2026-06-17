import { useState, useRef } from "react";
import { api } from "../../utils/api";
import type { UploadResult } from "../../types";

interface Props {
  onSuccess: (result: UploadResult) => void;
}

export default function UploadPanel({ onSuccess }: Props) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setError(null);
    setLoading(true);
    try {
      const result = await api.uploadPcap(file);
      onSuccess(result);
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div
      className={`upload-zone ${dragging ? "dragging" : ""} ${loading ? "loading" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => !loading && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pcap,.pcapng,.cap"
        style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }}
      />
      {loading ? (
        <div className="upload-inner">
          <div className="spinner" />
          <p>Parsing packets…</p>
        </div>
      ) : (
        <div className="upload-inner">
          <span className="upload-icon">📂</span>
          <p className="upload-primary">Drop a PCAP file here or click to browse</p>
          <p className="upload-secondary">.pcap · .pcapng · .cap</p>
          {error && <p className="upload-error">{error}</p>}
        </div>
      )}
    </div>
  );
}
