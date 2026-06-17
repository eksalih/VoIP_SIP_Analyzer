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

export interface Call {
  id: number;
  call_id: string;
  caller: string | null;
  called: string | null;
  display_name: string | null;
  source_ip: string | null;
  destination_ip: string | null;
  user_agent: string | null;
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
}

export interface UploadResult {
  status: string;
  file?: string;
  message?: string;
  packets_parsed?: number;
  calls_processed?: number;
  execution_time?: number;
  test_results?: { call_id: string; expected: string; detected: string; result: string }[];
  summary?: Record<string, number>;
}
