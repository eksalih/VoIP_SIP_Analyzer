"""
SIP Packet Parser
Parses PCAP/PCAPNG files and extracts SIP call information.
Supports PyShark (tshark-based) with Scapy fallback.
"""
import re
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# SIP method & response patterns
SIP_REQUEST_LINE = re.compile(r'^(INVITE|ACK|BYE|CANCEL|OPTIONS|REGISTER|NOTIFY|SUBSCRIBE|MESSAGE|REFER|INFO|PRACK|UPDATE)\s+sip:', re.IGNORECASE)
SIP_RESPONSE_LINE = re.compile(r'^SIP/2\.0\s+(\d{3})\s+(.*)', re.IGNORECASE)
CALL_ID_RE = re.compile(r'^Call-ID:\s*(.+)', re.IGNORECASE | re.MULTILINE)
FROM_RE = re.compile(r'^From:\s*(.+)', re.IGNORECASE | re.MULTILINE)
TO_RE = re.compile(r'^To:\s*(.+)', re.IGNORECASE | re.MULTILINE)
VIA_RE = re.compile(r'^Via:\s*(.+)', re.IGNORECASE | re.MULTILINE)
USER_AGENT_RE = re.compile(r'^User-Agent:\s*(.+)', re.IGNORECASE | re.MULTILINE)
CONTACT_RE = re.compile(r'^Contact:\s*(.+)', re.IGNORECASE | re.MULTILINE)
CSEQ_RE = re.compile(r'^CSeq:\s*(\d+)\s+(\w+)', re.IGNORECASE | re.MULTILINE)

SIP_URI_NUMBER_RE = re.compile(r'(?:sip:|tel:)([+\d\w\.\-]+)@?', re.IGNORECASE)
DISPLAY_NAME_RE = re.compile(r'^"?([^"<]+?)"?\s*<sip:', re.IGNORECASE)
BRANCH_RE = re.compile(r'branch=(z9hG4bK[^\s;,>]+)', re.IGNORECASE)
DOMAIN_RE = re.compile(r'sip:[^@]+@([^\s;>]+)', re.IGNORECASE)


@dataclass
class SIPPacket:
    timestamp: Optional[datetime] = None
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    source_port: Optional[int] = None
    destination_port: Optional[int] = None
    call_id: Optional[str] = None
    method: Optional[str] = None
    response_code: Optional[int] = None
    response_text: Optional[str] = None
    caller: Optional[str] = None
    called: Optional[str] = None
    display_name: Optional[str] = None
    user_agent: Optional[str] = None
    sip_domain: Optional[str] = None
    branch_id: Optional[str] = None
    cseq_number: Optional[int] = None
    cseq_method: Optional[str] = None
    raw_message: Optional[str] = None
    is_request: bool = False
    is_response: bool = False


def _extract_number(uri_header: str) -> Optional[str]:
    m = SIP_URI_NUMBER_RE.search(uri_header)
    return m.group(1) if m else None


def _extract_display_name(from_header: str) -> Optional[str]:
    m = DISPLAY_NAME_RE.search(from_header)
    return m.group(1).strip() if m else None


def _extract_branch(via_header: str) -> Optional[str]:
    m = BRANCH_RE.search(via_header)
    return m.group(1) if m else None


def _extract_domain(uri: str) -> Optional[str]:
    m = DOMAIN_RE.search(uri)
    return m.group(1).split(":")[0] if m else None


def parse_sip_message(raw: str) -> dict:
    """Extract SIP fields from raw SIP message text."""
    result = {}

    lines = raw.strip().split("\n")
    first_line = lines[0].strip() if lines else ""

    req_match = re.match(r'^(\w+)\s+sip:', first_line, re.IGNORECASE)
    resp_match = SIP_RESPONSE_LINE.match(first_line)

    if req_match:
        result["method"] = req_match.group(1).upper()
        result["is_request"] = True
    elif resp_match:
        result["response_code"] = int(resp_match.group(1))
        result["response_text"] = resp_match.group(2).strip()
        result["is_response"] = True

    cid = CALL_ID_RE.search(raw)
    if cid:
        result["call_id"] = cid.group(1).strip()

    from_h = FROM_RE.search(raw)
    if from_h:
        fval = from_h.group(1)
        result["caller"] = _extract_number(fval)
        result["display_name"] = _extract_display_name(fval)

    to_h = TO_RE.search(raw)
    if to_h:
        result["called"] = _extract_number(to_h.group(1))
        if not result.get("sip_domain"):
            result["sip_domain"] = _extract_domain(to_h.group(1))

    via_h = VIA_RE.search(raw)
    if via_h:
        result["branch_id"] = _extract_branch(via_h.group(1))

    ua_h = USER_AGENT_RE.search(raw)
    if ua_h:
        result["user_agent"] = ua_h.group(1).strip()

    cseq_h = CSEQ_RE.search(raw)
    if cseq_h:
        result["cseq_number"] = int(cseq_h.group(1))
        result["cseq_method"] = cseq_h.group(2).upper()

    return result


def parse_pcap_pyshark(file_path: str) -> list[SIPPacket]:
    """Parse PCAP using PyShark (requires tshark installed)."""
    try:
        import pyshark
    except ImportError:
        logger.warning("PyShark not available, falling back to Scapy")
        return []

    packets = []
    try:
        cap = pyshark.FileCapture(
            file_path,
            display_filter="sip",
            use_json=True,
            include_raw=True,
            keep_packets=False,
        )

        for pkt in cap:
            try:
                p = SIPPacket()

                # Timestamp
                if hasattr(pkt, "sniff_time"):
                    p.timestamp = pkt.sniff_time

                # Network layer
                if hasattr(pkt, "ip"):
                    p.source_ip = str(pkt.ip.src)
                    p.destination_ip = str(pkt.ip.dst)
                elif hasattr(pkt, "ipv6"):
                    p.source_ip = str(pkt.ipv6.src)
                    p.destination_ip = str(pkt.ipv6.dst)

                # Transport layer
                if hasattr(pkt, "udp"):
                    p.source_port = int(pkt.udp.srcport)
                    p.destination_port = int(pkt.udp.dstport)
                elif hasattr(pkt, "tcp"):
                    p.source_port = int(pkt.tcp.srcport)
                    p.destination_port = int(pkt.tcp.dstport)

                # SIP layer
                if hasattr(pkt, "sip"):
                    sip = pkt.sip
                    raw_text = ""
                    try:
                        raw_text = bytes.fromhex(
                            pkt.sip.get_raw_value("raw")
                        ).decode("utf-8", errors="replace") if hasattr(pkt.sip, "raw") else ""
                    except Exception:
                        pass

                    # Try direct field access first
                    if hasattr(sip, "call_id"):
                        p.call_id = str(sip.call_id)
                    if hasattr(sip, "from_user"):
                        p.caller = str(sip.from_user)
                    if hasattr(sip, "to_user"):
                        p.called = str(sip.to_user)
                    if hasattr(sip, "from_display_info"):
                        p.display_name = str(sip.from_display_info).strip('"')
                    if hasattr(sip, "user_agent"):
                        p.user_agent = str(sip.user_agent)

                    # Method or response
                    if hasattr(sip, "request_method"):
                        p.method = str(sip.request_method).upper()
                        p.is_request = True
                    if hasattr(sip, "status_code"):
                        p.response_code = int(str(sip.status_code))
                        p.is_response = True
                    if hasattr(sip, "status_text"):
                        p.response_text = str(sip.status_text)

                    if hasattr(sip, "via_branch"):
                        p.branch_id = str(sip.via_branch)
                    if hasattr(sip, "cseq_seq_no"):
                        p.cseq_number = int(str(sip.cseq_seq_no))
                    if hasattr(sip, "cseq_method"):
                        p.cseq_method = str(sip.cseq_method).upper()

                    p.raw_message = raw_text or str(sip)

                    if p.call_id:
                        packets.append(p)

            except Exception as e:
                logger.debug(f"Skipping packet: {e}")
                continue

        cap.close()

    except Exception as e:
        logger.error(f"PyShark parsing error: {e}")

    return packets


def parse_pcap_scapy(file_path: str) -> list[SIPPacket]:
    """Parse PCAP using Scapy (fallback, no tshark required)."""
    try:
        from scapy.all import rdpcap, UDP, TCP, IP, Raw
    except ImportError:
        logger.error("Scapy not available")
        return []

    packets = []
    try:
        raw_packets = rdpcap(file_path)
        for raw_pkt in raw_packets:
            try:
                if not raw_pkt.haslayer(Raw):
                    continue
                payload = raw_pkt[Raw].load.decode("utf-8", errors="replace")

                # Quick SIP check
                if not any(kw in payload[:20] for kw in ["SIP/2.0", "INVITE", "BYE", "CANCEL", "ACK", "REGISTER"]):
                    continue

                parsed = parse_sip_message(payload)
                if not parsed.get("call_id"):
                    continue

                p = SIPPacket()
                p.raw_message = payload

                # Timestamp from Scapy
                if hasattr(raw_pkt, "time"):
                    p.timestamp = datetime.fromtimestamp(float(raw_pkt.time))

                if raw_pkt.haslayer(IP):
                    p.source_ip = raw_pkt[IP].src
                    p.destination_ip = raw_pkt[IP].dst

                if raw_pkt.haslayer(UDP):
                    p.source_port = raw_pkt[UDP].sport
                    p.destination_port = raw_pkt[UDP].dport
                elif raw_pkt.haslayer(TCP):
                    p.source_port = raw_pkt[TCP].sport
                    p.destination_port = raw_pkt[TCP].dport

                p.call_id = parsed.get("call_id")
                p.method = parsed.get("method")
                p.response_code = parsed.get("response_code")
                p.response_text = parsed.get("response_text")
                p.caller = parsed.get("caller")
                p.called = parsed.get("called")
                p.display_name = parsed.get("display_name")
                p.user_agent = parsed.get("user_agent")
                p.sip_domain = parsed.get("sip_domain")
                p.branch_id = parsed.get("branch_id")
                p.cseq_number = parsed.get("cseq_number")
                p.cseq_method = parsed.get("cseq_method")
                p.is_request = parsed.get("is_request", False)
                p.is_response = parsed.get("is_response", False)

                packets.append(p)

            except Exception as e:
                logger.debug(f"Scapy packet skip: {e}")
                continue

    except Exception as e:
        logger.error(f"Scapy reading error: {e}")

    return packets


def parse_pcap_file(file_path: str) -> list[SIPPacket]:
    """
    Main entry point: parse a PCAP/PCAPNG file.
    Tries PyShark first, falls back to Scapy.
    """
    logger.info(f"Parsing PCAP: {file_path}")

    packets = parse_pcap_pyshark(file_path)
    if not packets:
        logger.info("PyShark returned no packets, trying Scapy...")
        packets = parse_pcap_scapy(file_path)

    logger.info(f"Parsed {len(packets)} SIP packets")
    return packets
