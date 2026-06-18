import { useState, useRef } from "react";
import { api } from "../../utils/api";
import type { UploadResult, BatchUploadResult } from "../../types";

interface Props {
  onSuccess: (result: UploadResult | BatchUploadResult) => void;
}

const MAX_BATCH_FILES = 25;

export default function UploadPanel({ onSuccess }: Props) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("Parsing packets…");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = async (fileList: File[]) => {
    if (fileList.length === 0) return;
    setError(null);

    if (fileList.length > MAX_BATCH_FILES) {
      setError(`Too many files selected (${fileList.length}). Max ${MAX_BATCH_FILES} per upload.`);
      return;
    }

    setLoading(true);
    try {
      if (fileList.length === 1) {
        setLoadingLabel("Parsing packets…");
        const result = await api.uploadPcap(fileList[0]);
        onSuccess(result);
      } else {
        setLoadingLabel(`Parsing ${fileList.length} files…`);
        const result = await api.uploadPcapBatch(fileList);
        onSuccess(result);
      }
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(Array.from(e.dataTransfer.files));
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
        multiple
        style={{ display: "none" }}
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length) handleFiles(files);
          e.target.value = "";
        }}
      />
      {loading ? (
        <div className="upload-inner">
          <div className="spinner" />
          <p>{loadingLabel}</p>
        </div>
      ) : (
        <div className="upload-inner">
          <span className="upload-icon">📂</span>
          <p className="upload-primary">Drop one or more PCAP files here, or click to browse</p>
          <p className="upload-secondary">.pcap · .pcapng · .cap · up to {MAX_BATCH_FILES} files at once</p>
          {error && <p className="upload-error">{error}</p>}
        </div>
      )}
    </div>
  );
}
