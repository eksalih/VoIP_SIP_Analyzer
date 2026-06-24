"""
PCAP Processing Service
Coordinates parsing, classification, and database persistence.

Every upload creates a CaptureFile row. All calls extracted from that
upload are scoped to it, so multiple files (or repeated test sessions)
never blur their calls together in the call list.
"""
import logging
import time
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.sip_parser import parse_pcap_file
from app.core.call_state_machine import process_pcap_sessions, CallSession
from app.models.call import Call, CallStatus
from app.models.sip_event import SIPEvent
from app.models.test_run import TestRun
from app.models.capture_file import CaptureFile

logger = logging.getLogger(__name__)


async def process_pcap(
    file_path: str,
    filename: str,
    db: AsyncSession,
    expected_status: str | None = None,
    file_size_bytes: int | None = None,
    label: str | None = None,
) -> dict:
    """
    Full single-file processing pipeline:
    1. Create a CaptureFile record
    2. Parse PCAP
    3. Classify sessions
    4. Persist calls + events, scoped to this capture file
    5. Return summary
    """
    start = time.monotonic()

    capture_file = CaptureFile(
        filename=filename,
        file_size_bytes=file_size_bytes,
        label=label,
    )
    db.add(capture_file)
    await db.flush()  # assigns capture_file.id

    try:
        packets = parse_pcap_file(file_path)
    except ValueError as e:
        # Raised by parse_pcap_file for detectable problems (e.g. SIP-over-TLS).
        # Return a clean error response rather than letting a 500 propagate.
        capture_file.packets_parsed = 0
        capture_file.calls_found = 0
        capture_file.processing_time_seconds = round(time.monotonic() - start, 3)
        await db.flush()
        return {
            "status": "error",
            "message": str(e),
            "file": filename,
            "capture_file_id": capture_file.id,
            "calls_processed": 0,
        }

    if not packets:
        capture_file.packets_parsed = 0
        capture_file.calls_found = 0
        capture_file.processing_time_seconds = round(time.monotonic() - start, 3)
        await db.flush()
        return {
            "status": "error",
            "message": "No SIP packets found in capture file",
            "file": filename,
            "capture_file_id": capture_file.id,
            "calls_processed": 0,
        }

    sessions = process_pcap_sessions(packets)
    calls_saved = 0
    test_results = []

    for session in sessions:
        call = await _upsert_call(session, capture_file.id, db)
        await _save_events(session, call, db)

        if expected_status:
            tr = await _save_test_run(
                session, call, filename, expected_status, time.monotonic() - start, db
            )
            test_results.append({
                "call_id": session.call_id,
                "expected": expected_status,
                "detected": session.status,
                "result": tr.result,
            })

        calls_saved += 1

    elapsed = round(time.monotonic() - start, 3)
    summary = _build_summary(sessions)

    # Persist rollup counts onto the capture file for fast list-view rendering
    capture_file.packets_parsed = len(packets)
    capture_file.calls_found = calls_saved
    capture_file.answered_count = summary.get("ANSWERED", 0)
    capture_file.missed_count = summary.get("MISSED", 0)
    capture_file.rejected_count = summary.get("REJECTED", 0)
    capture_file.failed_count = summary.get("FAILED", 0)
    capture_file.cancelled_count = summary.get("CANCELLED", 0)
    capture_file.processing_time_seconds = elapsed

    await db.flush()

    return {
        "status": "ok",
        "file": filename,
        "capture_file_id": capture_file.id,
        "packets_parsed": len(packets),
        "calls_processed": calls_saved,
        "execution_time": elapsed,
        "test_results": test_results,
        "summary": summary,
    }


async def process_pcap_batch(
    files: list[tuple[str, str, int]],  # (file_path, filename, file_size_bytes)
    db: AsyncSession,
    expected_status: str | None = None,
) -> dict:
    """
    Process multiple PCAP files in one upload action.
    Each file gets its own CaptureFile row; failures in one file
    do not block processing of the rest.
    """
    batch_start = time.monotonic()
    results = []
    combined_summary = {s: 0 for s in ["ANSWERED", "MISSED", "REJECTED", "FAILED", "CANCELLED", "UNKNOWN"]}

    for file_path, filename, file_size_bytes in files:
        try:
            result = await process_pcap(
                file_path=file_path,
                filename=filename,
                db=db,
                expected_status=expected_status,
                file_size_bytes=file_size_bytes,
            )
        except Exception as e:
            logger.error(f"Failed to process {filename}: {e}")
            result = {
                "status": "error",
                "file": filename,
                "message": str(e),
                "calls_processed": 0,
            }

        results.append(result)

        if result.get("summary"):
            for key, val in result["summary"].items():
                if key in combined_summary:
                    combined_summary[key] += val

    total_calls = sum(r.get("calls_processed", 0) for r in results)
    total_packets = sum(r.get("packets_parsed", 0) for r in results)
    files_ok = sum(1 for r in results if r.get("status") == "ok")
    files_failed = len(results) - files_ok

    return {
        "status": "ok" if files_failed == 0 else "partial",
        "files_processed": len(results),
        "files_ok": files_ok,
        "files_failed": files_failed,
        "total_packets_parsed": total_packets,
        "total_calls_processed": total_calls,
        "execution_time": round(time.monotonic() - batch_start, 3),
        "combined_summary": {
            **combined_summary,
            "total": total_calls,
            "success_rate": round((combined_summary["ANSWERED"] / total_calls * 100), 1) if total_calls else 0,
        },
        "files": results,
    }


async def _upsert_call(session: CallSession, capture_file_id: int, db: AsyncSession) -> Call:
    """
    Insert or update a Call record from a session.
    Lookup is scoped to (capture_file_id, call_id) — the same Call-ID string
    appearing in two different uploads must NOT be treated as the same call.
    """
    result = await db.execute(
        select(Call).where(
            Call.capture_file_id == capture_file_id,
            Call.call_id == session.call_id,
        )
    )
    call = result.scalar_one_or_none()

    status_enum = _map_status(session.status)

    if call:
        call.status = status_enum
        call.end_time = session.end_time
        call.ring_duration = session.ring_duration
        call.talk_duration = session.talk_duration
        call.total_duration = session.total_duration
        call.sip_result_code = session.sip_result_code
        call.rejection_reason = session.rejection_reason
    else:
        call = Call(
            capture_file_id=capture_file_id,
            call_id=session.call_id,
            caller=session.caller,
            called=session.called,
            display_name=session.display_name,
            source_ip=session.source_ip,
            destination_ip=session.destination_ip,
            user_agent=session.user_agent,
            sip_domain=session.sip_domain,
            branch_id=session.branch_id,
            start_time=session.invite_time,
            ring_time=session.ringing_time,
            answer_time=session.answer_time,
            end_time=session.end_time,
            ring_duration=session.ring_duration,
            talk_duration=session.talk_duration,
            total_duration=session.total_duration,
            status=status_enum,
            sip_result_code=session.sip_result_code,
            rejection_reason=session.rejection_reason,
        )
        db.add(call)

    await db.flush()
    return call


async def _save_events(session: CallSession, call: Call, db: AsyncSession):
    """Save SIP events for a call."""
    for i, pkt in enumerate(sorted(
        [p for p in session.packets if p.timestamp],
        key=lambda x: x.timestamp,
    )):
        event = SIPEvent(
            call_id=call.id,
            timestamp=pkt.timestamp,
            sip_method=pkt.method,
            sip_response_code=pkt.response_code,
            sip_response_text=pkt.response_text,
            source_ip=pkt.source_ip,
            destination_ip=pkt.destination_ip,
            raw_message=pkt.raw_message,
            sequence_number=i,
        )
        db.add(event)


async def _save_test_run(
    session: CallSession,
    call: Call,
    filename: str,
    expected_status: str,
    exec_time: float,
    db: AsyncSession,
) -> TestRun:
    detected = session.status or "UNKNOWN"
    passed = detected.upper() == expected_status.upper()
    tr = TestRun(
        call_id=call.id,
        capture_file_name=filename,
        expected_status=expected_status.upper(),
        detected_status=detected,
        result="PASS" if passed else "FAIL",
        execution_time=round(exec_time, 3),
        passed=passed,
    )
    db.add(tr)
    await db.flush()
    return tr


def _map_status(status: str | None) -> CallStatus:
    mapping = {
        "ANSWERED": CallStatus.ANSWERED,
        "MISSED": CallStatus.MISSED,
        "REJECTED": CallStatus.REJECTED,
        "FAILED": CallStatus.FAILED,
        "CANCELLED": CallStatus.CANCELLED,
    }
    return mapping.get(str(status).upper(), CallStatus.UNKNOWN)


def _build_summary(sessions: list[CallSession]) -> dict:
    counts = {s: 0 for s in ["ANSWERED", "MISSED", "REJECTED", "FAILED", "CANCELLED", "UNKNOWN"]}
    for s in sessions:
        counts[s.status or "UNKNOWN"] = counts.get(s.status or "UNKNOWN", 0) + 1
    total = len(sessions)
    answered = counts.get("ANSWERED", 0)
    return {
        **counts,
        "total": total,
        "success_rate": round((answered / total * 100), 1) if total else 0,
    }
