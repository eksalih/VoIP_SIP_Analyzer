import type { CaptureFile } from "../../types";
import { formatDateTime } from "../../utils/format";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface Props {
  file: CaptureFile;
  selected: boolean;
  onClick: () => void;
  onDelete: () => void;
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function CaptureFileCard({ file, selected, onClick, onDelete }: Props) {
  const total = file.calls_found ?? 0;

  const handleExport = (format: "csv" | "pdf", e: React.MouseEvent) => {
    e.stopPropagation();
    const url = `${BASE}/export/${format}?capture_file_id=${file.id}`;
    const a = document.createElement("a");
    a.href = url;
    a.click();
  };

  return (
    <div className={`capture-card ${selected ? "selected" : ""}`} onClick={onClick}>
      <div className="capture-card-header">
        <span className="capture-card-name" title={file.filename}>{file.filename}</span>
        <div className="capture-card-actions">
          <button
            className="capture-card-action-btn"
            title="Download CSV"
            onClick={(e) => handleExport("csv", e)}
          >
            CSV
          </button>
          <button
            className="capture-card-action-btn pdf"
            title="Download PDF report"
            onClick={(e) => handleExport("pdf", e)}
          >
            PDF
          </button>
          <button
            className="capture-card-delete"
            title="Delete this capture file and its calls"
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
          >
            ✕
          </button>
        </div>
      </div>

      <div className="capture-card-meta">
        <span>{formatDateTime(file.uploaded_at)}</span>
        <span>·</span>
        <span>{formatBytes(file.file_size_bytes)}</span>
        <span>·</span>
        <span>{file.packets_parsed ?? 0} packets</span>
        {file.processing_time_seconds != null && (
          <>
            <span>·</span>
            <span>{file.processing_time_seconds}s</span>
          </>
        )}
      </div>

      <div className="capture-card-stats">
        <span className="capture-stat total">{total} call{total === 1 ? "" : "s"}</span>
        {!!file.answered_count && <span className="capture-stat answered">{file.answered_count} answered</span>}
        {!!file.missed_count && <span className="capture-stat missed">{file.missed_count} missed</span>}
        {!!file.rejected_count && <span className="capture-stat rejected">{file.rejected_count} rejected</span>}
        {!!file.failed_count && <span className="capture-stat failed">{file.failed_count} failed</span>}
        {!!file.cancelled_count && <span className="capture-stat cancelled">{file.cancelled_count} cancelled</span>}
        {total === 0 && <span className="capture-stat empty">No SIP calls found</span>}
      </div>
    </div>
  );
}
