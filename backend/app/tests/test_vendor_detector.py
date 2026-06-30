"""
Unit tests for vendor detection from SIP User-Agent strings.
"""
import pytest
from app.core.vendor_detector import detect_vendor, detect_vendor_category, extract_version


class TestDetectVendor:
    @pytest.mark.parametrize("ua,expected", [
        ("Yeastar S20-65.16.0.183", "Yeastar"),
        ("Grandstream GXP2140 1.0.8.80", "Grandstream"),
        ("Cisco-CP-7942G/8.5.3", "Cisco"),
        ("Asterisk PBX 18.6.0", "Asterisk"),
        ("3CXPhoneSystem/18", "3CX"),
        ("FreePBX 15.0", "FreePBX"),
        ("Polycom/5.4.3", "Polycom"),
        ("Yealink SIP-T31P 124.86.0.40", "Yealink"),
        ("Yealink SIP-T46S 66.84.0.5", "Yealink"),
        ("Zoiper rv2.10.16", "Zoiper"),
        ("MicroSIP/3.20.5", "MicroSIP"),
        ("FreeSWITCH-mod_sofia/1.10.7", "FreeSWITCH"),
    ])
    def test_known_vendors_detected(self, ua, expected):
        assert detect_vendor(ua) == expected

    def test_unknown_vendor_returns_none(self):
        assert detect_vendor("SomeRandomDevice/9.9.9") is None

    def test_none_input_returns_none(self):
        assert detect_vendor(None) is None

    def test_empty_string_returns_none(self):
        assert detect_vendor("") is None

    def test_real_yeastar_capture_user_agent(self):
        """Exact User-Agent string observed in real Yeastar PBX captures."""
        assert detect_vendor("Yeastar S20-65.16.0.183") == "Yeastar"

    def test_real_yealink_phone_user_agent(self):
        """Exact User-Agent string observed paired with the Yeastar PBX captures."""
        assert detect_vendor("Yealink SIP-T31P 124.86.0.40") == "Yealink"


class TestDetectVendorCategory:
    def test_pbx_category(self):
        assert detect_vendor_category("Yeastar S20-65.16.0.183") == "pbx"
        assert detect_vendor_category("Asterisk PBX 18.6.0") == "pbx"
        assert detect_vendor_category("FreePBX 15.0") == "pbx"

    def test_phone_category(self):
        assert detect_vendor_category("Yealink SIP-T31P 124.86.0.40") == "phone"
        assert detect_vendor_category("Grandstream GXP2140 1.0.8.80") == "phone"
        assert detect_vendor_category("Cisco-CP-7942G/8.5.3") == "phone"

    def test_softphone_category(self):
        assert detect_vendor_category("Zoiper rv2.10.16") == "softphone"
        assert detect_vendor_category("MicroSIP/3.20.5") == "softphone"

    def test_unknown_returns_none(self):
        assert detect_vendor_category("UnknownThing/1.0") is None

    def test_none_returns_none(self):
        assert detect_vendor_category(None) is None


class TestExtractVersion:
    def test_prefers_firmware_version_over_model_number(self):
        """Cisco UA has both a model number (7942) and firmware (8.5.3) —
        firmware (more dotted segments) should win."""
        assert extract_version("Cisco-CP-7942G/8.5.3") == "8.5.3"

    def test_yeastar_version(self):
        assert extract_version("Yeastar S20-65.16.0.183") == "65.16.0.183"

    def test_yealink_version(self):
        assert extract_version("Yealink SIP-T31P 124.86.0.40") == "124.86.0.40"

    def test_asterisk_version(self):
        assert extract_version("Asterisk PBX 18.6.0") == "18.6.0"

    def test_no_version_returns_none(self):
        assert extract_version("JustAName") is None

    def test_none_returns_none(self):
        assert extract_version(None) is None
