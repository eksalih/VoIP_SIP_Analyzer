"""
Vendor Detection
Parses SIP User-Agent header strings and maps them to known PBX/phone vendors.
Used to add a vendor badge to calls and enable vendor-based filtering.
"""
import re
from typing import Optional

# Pattern list: (regex, vendor_name, category)
# Order matters — more specific patterns first.
_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # PBX platforms
    (re.compile(r"Yeastar",           re.I), "Yeastar",      "pbx"),
    (re.compile(r"3CXPhoneSystem",    re.I), "3CX",          "pbx"),
    (re.compile(r"3CX",               re.I), "3CX",          "pbx"),
    (re.compile(r"FreePBX",           re.I), "FreePBX",      "pbx"),
    (re.compile(r"Asterisk",          re.I), "Asterisk",     "pbx"),
    (re.compile(r"FusionPBX",         re.I), "FusionPBX",    "pbx"),
    (re.compile(r"FreeSWITCH",        re.I), "FreeSWITCH",   "pbx"),
    (re.compile(r"CUCM|Cisco-CUCM",   re.I), "Cisco CUCM",   "pbx"),
    (re.compile(r"Avaya",             re.I), "Avaya",        "pbx"),
    (re.compile(r"Alcatel",           re.I), "Alcatel",      "pbx"),
    (re.compile(r"Mitel",             re.I), "Mitel",        "pbx"),
    (re.compile(r"Panasonic",         re.I), "Panasonic",    "pbx"),

    # IP Phones / endpoints
    (re.compile(r"Grandstream",       re.I), "Grandstream",  "phone"),
    (re.compile(r"Cisco-CP",          re.I), "Cisco",        "phone"),
    (re.compile(r"Cisco",             re.I), "Cisco",        "phone"),
    (re.compile(r"Polycom",           re.I), "Polycom",      "phone"),
    (re.compile(r"POLY",              re.I), "Poly",         "phone"),
    (re.compile(r"Snom",              re.I), "Snom",         "phone"),
    (re.compile(r"Yealink",           re.I), "Yealink",      "phone"),
    (re.compile(r"Fanvil",            re.I), "Fanvil",       "phone"),
    (re.compile(r"Htek",              re.I), "Htek",         "phone"),
    (re.compile(r"Gigaset",           re.I), "Gigaset",      "phone"),
    (re.compile(r"Aastra",            re.I), "Aastra",       "phone"),
    (re.compile(r"Linksys",           re.I), "Linksys",      "phone"),
    (re.compile(r"Etisalat",          re.I), "Etisalat",     "phone"),

    # Softphones / apps
    (re.compile(r"Zoiper",            re.I), "Zoiper",       "softphone"),
    (re.compile(r"MicroSIP",          re.I), "MicroSIP",     "softphone"),
    (re.compile(r"Bria",              re.I), "Bria",         "softphone"),
    (re.compile(r"Linphone",          re.I), "Linphone",     "softphone"),
    (re.compile(r"Twinkle",           re.I), "Twinkle",      "softphone"),
    (re.compile(r"X-Lite",            re.I), "X-Lite",       "softphone"),
    (re.compile(r"eyeBeam",           re.I), "eyeBeam",      "softphone"),
    (re.compile(r"CSipSimple",        re.I), "CSipSimple",   "softphone"),
    (re.compile(r"Baresip",           re.I), "Baresip",      "softphone"),
]


def detect_vendor(user_agent: Optional[str]) -> Optional[str]:
    """
    Return the detected vendor name from a SIP User-Agent string, or None if unknown.
    Example: "Yeastar S20-65.16.0.183" → "Yeastar"
    """
    if not user_agent:
        return None
    for pattern, vendor, _ in _PATTERNS:
        if pattern.search(user_agent):
            return vendor
    return None


def detect_vendor_category(user_agent: Optional[str]) -> Optional[str]:
    """
    Return the category ('pbx', 'phone', 'softphone') or None if unknown.
    """
    if not user_agent:
        return None
    for pattern, _, category in _PATTERNS:
        if pattern.search(user_agent):
            return category
    return None


def extract_version(user_agent: Optional[str]) -> Optional[str]:
    """
    Try to extract a version string from the User-Agent.
    Prefers the longest dot-separated numeric sequence, since firmware
    versions (e.g. "65.16.0.183") are more useful than model numbers
    (e.g. "7942") when both appear in the same string.
    e.g. "Yeastar S20-65.16.0.183"      -> "65.16.0.183"
         "Asterisk PBX 18.6.0"          -> "18.6.0"
         "Cisco-CP-7942G/8.5.3"         -> "8.5.3"
    """
    if not user_agent:
        return None
    candidates = re.findall(r"\d+(?:\.\d+)+", user_agent)
    if not candidates:
        return None
    # Prefer the candidate with the most dot-separated segments (most specific)
    return max(candidates, key=lambda c: c.count("."))
