export type CallStatus = "ANSWERED" | "MISSED" | "REJECTED" | "FAILED" | "CANCELLED" | "UNKNOWN";

export interface SIPEvent {
  id: number;
  timestamp: string | null;
  sip_method: string | null;
  sip_response_code: number | null;
  sip_response_text: string | null;
  source_ip: string | null;
  destination_ip: string | null;
  raw_message: string | null;
  sequence_number: number | null;
}

export interface RTPStream {
  id: number;
  source_ip: string | null;
  source_port: number | null;
  destination_ip: string | null;
  destination_port: number | null;
  ssrc: string | null;
  payload_type: number | null;
  codec: string | null;
  packet_count: number | null;
  expected_packets: number | null;
  packet_loss_count: number | null;
  packet_loss_pct: number | null;
  jitter_ms: number | null;
  jitter_max_ms: number | null;
  duration_seconds: number | null;
  is_one_way: boolean;
}

export interface Call {
  id: number;
  capture_file_id: number | null;
  call_id: string;
  caller: string | null;
  called: string | null;
  display_name: string | null;
  source_ip: string | null;
  destination_ip: string | null;
  user_agent: string | null;
  vendor: string | null;
  vendor_category: string | null;
  sip_domain: string | null;
  branch_id: string | null;
  start_time: string | null;
  ring_time: string | null;
  answer_time: string | null;
  end_time: string | null;
  ring_duration: number | null;
  talk_duration: number | null;
  total_duration: number | null;
  status: CallStatus;
  sip_result_code: number | null;
  rejection_reason: string | null;
  created_at: string | null;
  events?: SIPEvent[];
}

export interface CaptureFile {
  id: number;
  filename: string;
  file_size_bytes: number | null;
  packets_parsed: number | null;
  calls_found: number | null;
  answered_count: number | null;
  missed_count: number | null;
  rejected_count: number | null;
  failed_count: number | null;
  cancelled_count: number | null;
  processing_time_seconds: number | null;
  uploaded_at: string | null;
  label: string | null;
}

export interface Analytics {
  total_calls: number;
  answered: number;
  missed: number;
  rejected: number;
  failed: number;
  cancelled: number;
  success_rate: number;
  avg_ring_duration: number | null;
  avg_talk_duration: number | null;
  calls_by_day: { date: string; count: number }[];
  status_distribution: { status: string; count: number; color: string }[];
  rtp_streams_total: number;
  rtp_avg_jitter_ms: number | null;
  rtp_avg_loss_pct: number | null;
  rtp_one_way_count: number;
}

export interface UploadResult {
  status: string;
  file?: string;
  capture_file_id?: number;
  message?: string;
  packets_parsed?: number;
  calls_processed?: number;
  execution_time?: number;
  test_results?: { call_id: string; expected: string; detected: string; result: string }[];
  summary?: Record<string, number>;
}

export interface BatchUploadResult {
  status: string;
  files_processed: number;
  files_ok: number;
  files_failed: number;
  total_packets_parsed: number;
  total_calls_processed: number;
  execution_time: number;
  combined_summary: Record<string, number>;
  files: UploadResult[];
}
