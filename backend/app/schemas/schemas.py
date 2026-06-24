from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from app.models.call import CallStatus


class SIPEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: Optional[datetime] = None
    sip_method: Optional[str] = None
    sip_response_code: Optional[int] = None
    sip_response_text: Optional[str] = None
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    raw_message: Optional[str] = None
    sequence_number: Optional[int] = None


class CallSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    capture_file_id: Optional[int] = None
    call_id: str
    caller: Optional[str] = None
    called: Optional[str] = None
    display_name: Optional[str] = None
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    user_agent: Optional[str] = None
    sip_domain: Optional[str] = None
    branch_id: Optional[str] = None
    start_time: Optional[datetime] = None
    ring_time: Optional[datetime] = None
    answer_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    ring_duration: Optional[float] = None
    talk_duration: Optional[float] = None
    total_duration: Optional[float] = None
    status: CallStatus
    sip_result_code: Optional[int] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None


class CallDetailSchema(CallSchema):
    events: list[SIPEventSchema] = []


class CaptureFileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_size_bytes: Optional[int] = None
    packets_parsed: Optional[int] = None
    calls_found: Optional[int] = None
    answered_count: Optional[int] = None
    missed_count: Optional[int] = None
    rejected_count: Optional[int] = None
    failed_count: Optional[int] = None
    cancelled_count: Optional[int] = None
    processing_time_seconds: Optional[float] = None
    uploaded_at: Optional[datetime] = None
    label: Optional[str] = None


class AnalyticsSchema(BaseModel):
    total_calls: int
    answered: int
    missed: int
    rejected: int
    failed: int
    cancelled: int
    success_rate: float
    avg_ring_duration: Optional[float] = None
    avg_talk_duration: Optional[float] = None
    calls_by_day: list[dict] = []
    status_distribution: list[dict] = []


class TestResultSchema(BaseModel):
    call_id: str
    expected: str
    detected: str
    result: str


class UploadResponseSchema(BaseModel):
    status: str
    file: Optional[str] = None
    capture_file_id: Optional[int] = None
    message: Optional[str] = None
    packets_parsed: Optional[int] = None
    calls_processed: Optional[int] = None
    execution_time: Optional[float] = None
    test_results: Optional[list[TestResultSchema]] = None
    summary: Optional[dict] = None


class BatchUploadResponseSchema(BaseModel):
    status: str
    files_processed: int
    files_ok: int
    files_failed: int
    total_packets_parsed: int
    total_calls_processed: int
    execution_time: float
    combined_summary: dict
    files: list[UploadResponseSchema]
