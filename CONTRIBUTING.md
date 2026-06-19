# Contributing to VoIP SIP Analyzer

Thanks for considering a contribution. This project exists to make vendor
interoperability testing for SIP/VoIP equipment easier and more accessible —
contributions of all sizes are welcome, especially **real-world PCAP captures
from PBX/phone vendors not yet covered by the test suite**.

## Quick start for contributors

```bash
git clone https://github.com/eksalih/VoIP_SIP_Analyzer.git
cd VoIP_SIP_Analyzer

# Backend
cd backend
cp .env.example .env
pip install -r requirements.txt
pytest -v                              # should show 49+ passing tests
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                            # http://localhost:3000
```

Or just `docker compose up --build` from the repo root.

## The most valuable contribution: real vendor captures

The call classification engine (`backend/app/core/call_state_machine.py`) is
only as good as the real-world traffic it's been tested against. It has been
validated against captures from:

- Etisalat IP phones
- Yeastar PBX

If you have access to a SIP capture from a vendor not in that list — Asterisk,
FreePBX, 3CX, Grandstream, Cisco, Avaya, or anything else — that's the single
most useful thing you can contribute, even without writing any code yourself.

### How to add a new vendor fixture

1. Capture a PCAP/PCAPNG of a real call scenario (ANSWERED, MISSED, REJECTED,
   CANCELLED, or FAILED). **Anonymize it first** — strip or replace real phone
   numbers, IP addresses, and any PII in display names or User-Agent strings.
   `tcprewrite`/`bittwiste` or a short Scapy script both work for this.
2. Manually verify the expected outcome by reading the raw SIP flow (Wireshark
   or `tshark -r file.pcap -Y sip`) — confirm what status a human would assign
   before trusting the engine's output.
3. Add the file under `backend/app/tests/fixtures/<vendor>/` with a name that
   describes the scenario, e.g. `rejected_603_decline.pcapng`.
4. Add tests in `backend/app/tests/test_vendor_fixtures.py` (or a new
   `test_vendor_fixtures_<vendor>.py` file) following the existing pattern —
   see the docstring at the top of that file for the rationale.
5. Run the full suite and confirm everything passes:
   ```bash
   cd backend && pytest -v
   ```
6. Open a PR. Please describe the equipment/firmware version the capture came
   from, if known — that context helps future debugging.

If the engine misclassifies your capture, that's just as valuable a
contribution — please open an issue with the (anonymized) PCAP attached and a
description of what the correct classification should be and why.

## Code conventions

- **Backend**: Python 3.12, FastAPI, SQLAlchemy async ORM, SQLite-first.
  Type hints throughout; keep new code consistent with the existing style in
  `app/core/` and `app/services/`.
- **Frontend**: React + TypeScript, no UI framework — hand-rolled components
  styled via `App.css` following the existing dark, GitHub-inspired design
  system. Keep new components in `components/calls/` or `components/shared/`
  depending on scope.
- **Tests**: this repo treats automated tests as load-bearing, not optional.
  - `test_sip_engine.py` — synthetic unit tests for the parser and state
    machine. Add cases here for new SIP flows or edge cases you've reasoned
    through manually.
  - `test_api.py` — integration tests against the FastAPI app using
    synthetically generated PCAPs (see `_build_answered_call_pcap` for the
    pattern).
  - `test_vendor_fixtures.py` — regression tests against real, committed PCAP
    captures. This is the project's strongest defense against vendor-specific
    regressions; please don't remove or weaken these without strong reason.

  Run `pytest -v` before opening a PR. All tests must pass.

## Pull requests

- Keep PRs focused — one feature or fix per PR is easier to review and easier
  to revert if something goes wrong.
- Update `README.md`'s changelog section for any user-facing change.
- If you're changing the call classification logic in
  `call_state_machine.py`, please explain your reasoning in the PR
  description — small changes here have historically had non-obvious
  knock-on effects (see the README changelog for past examples: the
  CANCEL/200-OK bug, the 487-misclassified-as-rejection bug, and the
  ghost-session filtering issue).

## Reporting bugs

Please include:
- What PBX/phone vendor and (if known) firmware version produced the capture
- The expected call outcome vs. what the app reported
- An anonymized PCAP if you're able to share one — this is by far the fastest
  way to get a bug fixed, since the classification engine's bugs have
  historically all been vendor-specific signaling quirks that are very hard
  to reproduce without the original traffic.

## Questions / ideas

Open an issue. Feature ideas, especially around new SIP edge cases or
additional vendor support, are welcome even without a PR attached.
