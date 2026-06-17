"""
PCAP Processing Service
Coordinates parsing, classification, and database persistence.
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

logger = logging.getLogger(__name__)


async def process_pcap(
    file_path: str,
    filename: str,
    db: AsyncSession,
    expected_status: str | None = None,
) -> dict:
    """
    Full processing pipeline:
    1. Parse PCAP
    2. Classify sessions
    3. Persist to DB
    4. Return summary
    """
    start = time.monotonic()
    packets = parse_pcap_file(file_path)

    if not packets:
        return {
            "status": "error",
            "message": "No SIP packets found in capture file",
            "calls_processed": 0,
        }

    sessions = process_pcap_sessions(packets)
    calls_saved = 0
    test_results = []

    for session in sessions:
        call = await _upsert_call(session, db)
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

    await db.flush()

    elapsed = round(time.monotonic() - start, 3)
    return {
        "status": "ok",
        "file": filename,
        "packets_parsed": len(packets),
        "calls_processed": calls_saved,
        "execution_time": elapsed,
        "test_results": test_results,
        "summary": _build_summary(sessions),
    }


async def _upsert_call(session: CallSession, db: AsyncSession) -> Call:
    """Insert or update a Call record from a session."""
    result = await db.execute(select(Call).where(Call.call_id == session.call_id))
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
