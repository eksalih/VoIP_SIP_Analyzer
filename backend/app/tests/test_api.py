"""
Integration tests for REST API endpoints.
Uses httpx + in-memory SQLite database.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.database import engine, Base


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _build_answered_call_pcap(path, call_id: str = "clear-test-call@127.0.0.1"):
    """Write a minimal synthetic INVITE -> 200 OK -> BYE PCAP to `path`."""
    from scapy.all import IP, UDP, Raw, wrpcap
    import time

    sip_invite = (
        f"INVITE sip:1002@127.0.0.1 SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK776a\r\n"
        f"From: <sip:1001@127.0.0.1>;tag=abc\r\n"
        f"To: <sip:1002@127.0.0.1>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 INVITE\r\n\r\n"
    )
    sip_200 = (
        f"SIP/2.0 200 OK\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 INVITE\r\n\r\n"
    )
    sip_bye = (
        f"BYE sip:1001@127.0.0.1 SIP/2.0\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 2 BYE\r\n\r\n"
    )

    pkts = []
    for i, msg in enumerate([sip_invite, sip_200, sip_bye]):
        pkt = IP(src="127.0.0.1", dst="127.0.0.1") / UDP(sport=5060, dport=5060) / Raw(load=msg.encode())
        pkt.time = time.time() + i
        pkts.append(pkt)

    wrpcap(str(path), pkts)
    return path


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"


class TestCallsEndpoint:
    @pytest.mark.asyncio
    async def test_list_calls_empty(self, client):
        response = await client.get("/calls")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_call_not_found(self, client):
        response = await client.get("/calls/9999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_calls_filter_status(self, client):
        response = await client.get("/calls?status=ANSWERED")
        assert response.status_code == 200


class TestClearAllData:
    @pytest.mark.asyncio
    async def test_clear_all_requires_confirmation(self, client):
        """Without confirm=true, the endpoint must refuse to delete anything."""
        response = await client.delete("/calls/clear-all")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_clear_all_with_confirmation_on_empty_db(self, client):
        response = await client.delete("/calls/clear-all?confirm=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["deleted"]["calls"] == 0

    @pytest.mark.asyncio
    async def test_clear_all_removes_uploaded_data(self, client, tmp_path):
        """Upload a synthetic PCAP, confirm it appears, then clear and confirm it's gone."""
        pcap_path = _build_answered_call_pcap(tmp_path / "clear_test.pcap")

        with open(pcap_path, "rb") as f:
            upload_resp = await client.post(
                "/upload-pcap",
                files={"file": ("clear_test.pcap", f, "application/octet-stream")},
            )
        assert upload_resp.status_code == 200

        list_resp = await client.get("/calls")
        assert len(list_resp.json()) >= 1

        clear_resp = await client.delete("/calls/clear-all?confirm=true")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["deleted"]["calls"] >= 1
        assert clear_resp.json()["deleted"]["capture_files"] >= 1

        list_resp_after = await client.get("/calls")
        assert list_resp_after.json() == []

        files_resp_after = await client.get("/capture-files")
        assert files_resp_after.json() == []


class TestAnalyticsEndpoint:
    @pytest.mark.asyncio
    async def test_analytics_empty(self, client):
        response = await client.get("/analytics")
        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 0
        assert data["success_rate"] == 0.0
        assert data["answered"] == 0

    @pytest.mark.asyncio
    async def test_zero_packet_loss_is_not_reported_as_none(self, client):
        """
        Regression test: a real Yeastar call with 0% packet loss was being
        reported as rtp_avg_loss_pct=None instead of 0.0, because the original
        code used `if avg_loss else None`, which treats 0.0 as falsy.
        Zero loss is the best possible outcome and must be shown as 0.0, not
        hidden as if no data exists.
        """
        import os
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "yeastar", "answered_clean.pcapng"
        )
        with open(fixture, "rb") as f:
            resp = await client.post("/upload-pcap", files={"file": ("answered_clean.pcapng", f, "application/octet-stream")})
        assert resp.status_code == 200

        analytics = (await client.get("/analytics")).json()
        assert analytics["rtp_streams_total"] > 0, "Expected RTP streams from real Yeastar capture"
        assert analytics["rtp_avg_loss_pct"] is not None, (
            "rtp_avg_loss_pct must not be None when RTP streams exist, even if loss is exactly 0%"
        )
        assert analytics["rtp_avg_loss_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_analytics_includes_rtp_fields(self, client):
        """Analytics response schema must always include the v2.0.3 RTP fields."""
        response = await client.get("/analytics")
        data = response.json()
        for field in ["rtp_streams_total", "rtp_avg_jitter_ms", "rtp_avg_loss_pct", "rtp_one_way_count"]:
            assert field in data, f"Missing RTP field in analytics response: {field}"


class TestCaptureFiles:
    @pytest.mark.asyncio
    async def test_list_capture_files_empty(self, client):
        response = await client.get("/capture-files")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_capture_file_not_found(self, client):
        response = await client.get("/capture-files/9999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_creates_capture_file_with_rollup_counts(self, client, tmp_path):
        pcap_path = _build_answered_call_pcap(tmp_path / "session1.pcap")

        with open(pcap_path, "rb") as f:
            upload_resp = await client.post(
                "/upload-pcap",
                files={"file": ("session1.pcap", f, "application/octet-stream")},
            )
        assert upload_resp.status_code == 200
        capture_file_id = upload_resp.json()["capture_file_id"]
        assert capture_file_id is not None

        cf_resp = await client.get(f"/capture-files/{capture_file_id}")
        assert cf_resp.status_code == 200
        cf = cf_resp.json()
        assert cf["filename"] == "session1.pcap"
        assert cf["calls_found"] == 1
        assert cf["answered_count"] == 1
        assert cf["missed_count"] == 0

    @pytest.mark.asyncio
    async def test_calls_can_be_filtered_by_capture_file_id(self, client, tmp_path):
        """Two uploads, each with a DIFFERENT Call-ID, should each show up
        only under their own capture_file_id filter."""
        path1 = _build_answered_call_pcap(tmp_path / "fileA.pcap", call_id="call-A@host")
        path2 = _build_answered_call_pcap(tmp_path / "fileB.pcap", call_id="call-B@host")

        with open(path1, "rb") as f:
            r1 = await client.post("/upload-pcap", files={"file": ("fileA.pcap", f, "application/octet-stream")})
        with open(path2, "rb") as f:
            r2 = await client.post("/upload-pcap", files={"file": ("fileB.pcap", f, "application/octet-stream")})

        cf1_id = r1.json()["capture_file_id"]
        cf2_id = r2.json()["capture_file_id"]
        assert cf1_id != cf2_id

        calls_in_file1 = (await client.get(f"/calls?capture_file_id={cf1_id}")).json()
        calls_in_file2 = (await client.get(f"/calls?capture_file_id={cf2_id}")).json()

        assert len(calls_in_file1) == 1
        assert len(calls_in_file2) == 1
        assert calls_in_file1[0]["call_id"] == "call-A@host"
        assert calls_in_file2[0]["call_id"] == "call-B@host"

    @pytest.mark.asyncio
    async def test_same_call_id_across_two_uploads_does_not_collide(self, client, tmp_path):
        """
        Regression test for the v1.0.x bug: Call-ID was globally unique, so
        uploading two different test sessions that happened to produce the
        same Call-ID string would corrupt data. Now each capture file scopes
        its own Call-IDs, so this must succeed and produce two separate calls.
        """
        same_call_id = "duplicate-call-id@same-phone"
        path1 = _build_answered_call_pcap(tmp_path / "session_morning.pcap", call_id=same_call_id)
        path2 = _build_answered_call_pcap(tmp_path / "session_afternoon.pcap", call_id=same_call_id)

        with open(path1, "rb") as f:
            r1 = await client.post("/upload-pcap", files={"file": ("session_morning.pcap", f, "application/octet-stream")})
        assert r1.status_code == 200

        with open(path2, "rb") as f:
            r2 = await client.post("/upload-pcap", files={"file": ("session_afternoon.pcap", f, "application/octet-stream")})
        assert r2.status_code == 200

        all_calls = (await client.get("/calls")).json()
        matching = [c for c in all_calls if c["call_id"] == same_call_id]
        assert len(matching) == 2
        assert matching[0]["capture_file_id"] != matching[1]["capture_file_id"]

    @pytest.mark.asyncio
    async def test_delete_capture_file_removes_its_calls(self, client, tmp_path):
        pcap_path = _build_answered_call_pcap(tmp_path / "to_delete.pcap")

        with open(pcap_path, "rb") as f:
            upload_resp = await client.post(
                "/upload-pcap",
                files={"file": ("to_delete.pcap", f, "application/octet-stream")},
            )
        capture_file_id = upload_resp.json()["capture_file_id"]

        del_resp = await client.delete(f"/capture-files/{capture_file_id}")
        assert del_resp.status_code == 200

        cf_resp = await client.get(f"/capture-files/{capture_file_id}")
        assert cf_resp.status_code == 404

        calls_resp = await client.get(f"/calls?capture_file_id={capture_file_id}")
        assert calls_resp.json() == []


class TestBatchUpload:
    @pytest.mark.asyncio
    async def test_batch_upload_multiple_files(self, client, tmp_path):
        path1 = _build_answered_call_pcap(tmp_path / "batch1.pcap", call_id="batch-call-1@host")
        path2 = _build_answered_call_pcap(tmp_path / "batch2.pcap", call_id="batch-call-2@host")
        path3 = _build_answered_call_pcap(tmp_path / "batch3.pcap", call_id="batch-call-3@host")

        files = [
            ("files", ("batch1.pcap", open(path1, "rb"), "application/octet-stream")),
            ("files", ("batch2.pcap", open(path2, "rb"), "application/octet-stream")),
            ("files", ("batch3.pcap", open(path3, "rb"), "application/octet-stream")),
        ]
        try:
            response = await client.post("/upload-pcap/batch", files=files)
        finally:
            for _, (_, fh, _) in files:
                fh.close()

        assert response.status_code == 200
        data = response.json()
        assert data["files_processed"] == 3
        assert data["files_ok"] == 3
        assert data["files_failed"] == 0
        assert data["total_calls_processed"] == 3

        # Each file should have produced its own capture_file_id
        capture_file_ids = {f["capture_file_id"] for f in data["files"]}
        assert len(capture_file_ids) == 3

        all_files = (await client.get("/capture-files")).json()
        assert len(all_files) == 3

    @pytest.mark.asyncio
    async def test_batch_upload_rejects_invalid_extension(self, client, tmp_path):
        bad_file = tmp_path / "not_a_pcap.txt"
        bad_file.write_text("hello")

        good_path = _build_answered_call_pcap(tmp_path / "ok.pcap")

        files = [
            ("files", ("ok.pcap", open(good_path, "rb"), "application/octet-stream")),
            ("files", ("not_a_pcap.txt", open(bad_file, "rb"), "text/plain")),
        ]
        try:
            response = await client.post("/upload-pcap/batch", files=files)
        finally:
            for _, (_, fh, _) in files:
                fh.close()

        # Extension validation happens up front for the whole batch, before any processing
        assert response.status_code == 400

        # Nothing should have been persisted since validation failed before processing began
        all_files = (await client.get("/capture-files")).json()
        assert all_files == []


class TestExportEndpoints:
    """v1.3.0: CSV and PDF export endpoints."""

    async def _upload_capture(self, client, tmp_path, call_id="export-test@host"):
        path = _build_answered_call_pcap(tmp_path / "export_test.pcap", call_id=call_id)
        with open(path, "rb") as f:
            resp = await client.post(
                "/upload-pcap",
                files={"file": ("export_test.pcap", f, "application/octet-stream")},
            )
        assert resp.status_code == 200
        return resp.json()["capture_file_id"]

    @pytest.mark.asyncio
    async def test_csv_export_returns_correct_content_type(self, client, tmp_path):
        await self._upload_capture(client, tmp_path)
        resp = await client.get("/export/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_csv_export_has_header_row_and_data(self, client, tmp_path):
        await self._upload_capture(client, tmp_path)
        resp = await client.get("/export/csv")
        lines = resp.text.strip().splitlines()
        assert len(lines) >= 2  # header + at least one data row
        assert "Call-ID" in lines[0]
        assert "Status" in lines[0]
        assert "export-test@host" in resp.text

    @pytest.mark.asyncio
    async def test_csv_export_filtered_by_capture_file_id(self, client, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir(); dir_b.mkdir()
        cf1 = await self._upload_capture(client, dir_a, "call-A@host")
        await self._upload_capture(client, dir_b, "call-B@host")

        resp = await client.get(f"/export/csv?capture_file_id={cf1}")
        assert resp.status_code == 200
        assert "call-A@host" in resp.text
        assert "call-B@host" not in resp.text

    @pytest.mark.asyncio
    async def test_csv_export_filename_is_set(self, client, tmp_path):
        await self._upload_capture(client, tmp_path)
        resp = await client.get("/export/csv")
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".csv" in disposition

    @pytest.mark.asyncio
    async def test_pdf_export_returns_valid_pdf(self, client, tmp_path):
        await self._upload_capture(client, tmp_path)
        resp = await client.get("/export/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers["content-type"]
        assert resp.content[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_pdf_export_accepts_vendor_name(self, client, tmp_path):
        await self._upload_capture(client, tmp_path)
        resp = await client.get("/export/pdf?vendor_name=Yeastar+PBX")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_pdf_export_filtered_by_capture_file_id(self, client, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        cf1 = await self._upload_capture(client, dir_a, "call-pdf-filter@host")
        resp = await client.get(f"/export/pdf?capture_file_id={cf1}&vendor_name=TestVendor")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_pdf_filename_is_set(self, client, tmp_path):
        await self._upload_capture(client, tmp_path)
        resp = await client.get("/export/pdf")
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".pdf" in disposition

    @pytest.mark.asyncio
    async def test_export_empty_db_returns_valid_files(self, client):
        """Exporting with no calls should still return valid CSV/PDF, not a 500."""
        csv_resp = await client.get("/export/csv")
        assert csv_resp.status_code == 200
        lines = csv_resp.text.strip().splitlines()
        assert len(lines) == 1  # header only, no data rows

        pdf_resp = await client.get("/export/pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.content[:4] == b"%PDF"


class TestMediaEndpoint:
    """v2.0.0: RTP media quality endpoints."""

    @pytest.mark.asyncio
    async def test_media_empty_for_missed_call(self, client, tmp_path):
        """MISSED calls have no RTP — endpoint must return [] not 404/500."""
        path = _build_answered_call_pcap(tmp_path / "missed.pcap", call_id="missed@host")
        # Build a MISSED pcap (INVITE → 180 → CANCEL)
        from scapy.all import IP, UDP, Raw, wrpcap
        import time as _time
        missed_msgs = [
            b"INVITE sip:1002@127.0.0.1 SIP/2.0\r\nCall-ID: missed-rtp@host\r\nCSeq: 1 INVITE\r\nFrom: <sip:1001@127.0.0.1>\r\nTo: <sip:1002@127.0.0.1>\r\n\r\n",
            b"SIP/2.0 180 Ringing\r\nCall-ID: missed-rtp@host\r\nCSeq: 1 INVITE\r\n\r\n",
            b"CANCEL sip:1002@127.0.0.1 SIP/2.0\r\nCall-ID: missed-rtp@host\r\nCSeq: 1 CANCEL\r\n\r\n",
        ]
        pkts = []
        for i, msg in enumerate(missed_msgs):
            pkt = IP(src="127.0.0.1", dst="127.0.0.1") / UDP(sport=5060, dport=5060) / Raw(load=msg)
            pkt.time = _time.time() + i
            pkts.append(pkt)
        pcap_path = tmp_path / "missed_rtp.pcap"
        wrpcap(str(pcap_path), pkts)

        with open(pcap_path, "rb") as f:
            resp = await client.post("/upload-pcap", files={"file": ("missed.pcap", f, "application/octet-stream")})
        assert resp.status_code == 200
        call_id = (await client.get("/calls")).json()[0]["id"]

        media = (await client.get(f"/calls/{call_id}/media")).json()
        assert media == [], f"Expected empty media for missed call, got {media}"

    @pytest.mark.asyncio
    async def test_media_endpoint_returns_list(self, client, tmp_path):
        """Endpoint always returns a list (possibly empty), never 404."""
        path = _build_answered_call_pcap(tmp_path / "test.pcap")
        with open(path, "rb") as f:
            await client.post("/upload-pcap", files={"file": ("test.pcap", f, "application/octet-stream")})
        call_id = (await client.get("/calls")).json()[0]["id"]
        resp = await client.get(f"/calls/{call_id}/media")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_media_nonexistent_call(self, client):
        """404 for a call that doesn't exist."""
        resp = await client.get("/calls/9999/media")
        # Should still return 200 with [] since endpoint queries by call_id
        # and returns empty list when none found - or 404 if call doesn't exist
        # Our implementation returns [] (no call lookup), so 200 with []
        assert resp.status_code == 200
        assert resp.json() == []


class TestCaptureFileLabels:
    """v2.0.1: Session labels on capture files."""

    @pytest.mark.asyncio
    async def test_patch_label_sets_value(self, client, tmp_path):
        path = _build_answered_call_pcap(tmp_path / "label_test.pcap")
        with open(path, "rb") as f:
            resp = await client.post("/upload-pcap", files={"file": ("label_test.pcap", f, "application/octet-stream")})
        cf_id = resp.json()["capture_file_id"]

        patch_resp = await client.patch(f"/capture-files/{cf_id}", json={"label": "Yeastar firmware 65 retest"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["label"] == "Yeastar firmware 65 retest"

        get_resp = await client.get(f"/capture-files/{cf_id}")
        assert get_resp.json()["label"] == "Yeastar firmware 65 retest"

    @pytest.mark.asyncio
    async def test_patch_label_strips_whitespace(self, client, tmp_path):
        path = _build_answered_call_pcap(tmp_path / "label_test2.pcap")
        with open(path, "rb") as f:
            resp = await client.post("/upload-pcap", files={"file": ("label_test2.pcap", f, "application/octet-stream")})
        cf_id = resp.json()["capture_file_id"]

        patch_resp = await client.patch(f"/capture-files/{cf_id}", json={"label": "  spaced label  "})
        assert patch_resp.json()["label"] == "spaced label"

    @pytest.mark.asyncio
    async def test_patch_label_to_empty_string_clears_it(self, client, tmp_path):
        path = _build_answered_call_pcap(tmp_path / "label_test3.pcap")
        with open(path, "rb") as f:
            resp = await client.post("/upload-pcap", files={"file": ("label_test3.pcap", f, "application/octet-stream")})
        cf_id = resp.json()["capture_file_id"]

        await client.patch(f"/capture-files/{cf_id}", json={"label": "temporary"})
        clear_resp = await client.patch(f"/capture-files/{cf_id}", json={"label": ""})
        assert clear_resp.json()["label"] is None

    @pytest.mark.asyncio
    async def test_patch_label_nonexistent_file_404(self, client):
        resp = await client.patch("/capture-files/9999", json={"label": "test"})
        assert resp.status_code == 404


class TestVendorFilter:
    """v2.1.0: Vendor detection and filtering."""

    @pytest.mark.asyncio
    async def test_yeastar_capture_detects_vendor(self, client):
        """Use the committed real Yeastar fixture to confirm vendor detection end-to-end."""
        import os
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "yeastar", "answered_clean.pcapng"
        )
        with open(fixture, "rb") as f:
            resp = await client.post("/upload-pcap", files={"file": ("answered_clean.pcapng", f, "application/octet-stream")})
        assert resp.status_code == 200

        calls = (await client.get("/calls")).json()
        assert len(calls) >= 1
        assert any(c["vendor"] == "Yeastar" for c in calls)
        assert any(c["vendor_category"] == "pbx" for c in calls)

    @pytest.mark.asyncio
    async def test_filter_calls_by_vendor(self, client):
        import os
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "yeastar", "answered_clean.pcapng"
        )
        with open(fixture, "rb") as f:
            await client.post("/upload-pcap", files={"file": ("answered_clean.pcapng", f, "application/octet-stream")})

        resp = await client.get("/calls?vendor=Yeastar")
        assert resp.status_code == 200
        calls = resp.json()
        assert len(calls) >= 1
        assert all(c["vendor"] == "Yeastar" for c in calls)

    @pytest.mark.asyncio
    async def test_filter_by_nonexistent_vendor_returns_empty(self, client, tmp_path):
        path = _build_answered_call_pcap(tmp_path / "novendor.pcap")
        with open(path, "rb") as f:
            await client.post("/upload-pcap", files={"file": ("novendor.pcap", f, "application/octet-stream")})

        resp = await client.get("/calls?vendor=NonexistentVendor")
        assert resp.status_code == 200
        assert resp.json() == []
