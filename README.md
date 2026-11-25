# VoIP SIP Analyzer

A self-hosted web app for understanding what happens on your phone system. It tells you which calls were answered, missed, rejected, cancelled or failed, how good the audio was, and lets you listen back to recorded calls.

You can use it two ways:

* **Analyze captures:** upload a PCAP file from Wireshark or tcpdump and get a clear call history.
* **Monitor live:** connect it to a mirror (SPAN) port on your network and watch calls as they happen, with automatic recording.

Made for VoIP engineers, telecom administrators and support teams who troubleshoot SIP-based phone systems.

---

## What You Can Do

* See every call and its outcome without reading hundreds of SIP messages in Wireshark
* Inspect a call's SIP message flow, timeline and details
* Check audio quality: packet loss, jitter and one-way audio
* Play back call recordings (caller on the left channel, callee on the right)
* Watch live calls and see whether capture is healthy
* Give each person their own login, limited to the extensions they should see
* Keep an audit trail of who played, downloaded or deleted what
* View statistics and export call lists as CSV or PDF

---

## Call Outcomes

| Status    | Meaning                                       |
| --------- | --------------------------------------------- |
| ANSWERED  | The call was connected                        |
| MISSED    | It rang but nobody answered                   |
| REJECTED  | It was declined or the line was busy          |
| CANCELLED | The caller hung up before it rang             |
| FAILED    | It failed because of an error                 |

Examples of how outcomes are decided:

| SIP flow                      | Result    |
| ----------------------------- | --------- |
| INVITE → 200 OK → BYE         | ANSWERED  |
| INVITE → 180 Ringing → CANCEL | MISSED    |
| INVITE → 486 Busy Here        | REJECTED  |
| INVITE → CANCEL               | CANCELLED |
| INVITE → 404 or 5xx error     | FAILED    |

---

## Works With

Tested with captures from Asterisk, FreePBX, 3CX, Yeastar, Grandstream, Cisco and Avaya. It should work with any SIP-compliant system.

---

## Quick Start

You need Docker and Docker Compose.

```bash
git clone https://github.com/eksalih/VoIP_SIP_Analyzer.git
cd VoIP_SIP_Analyzer
cp .env.example .env
docker compose up -d --build
```

Or use the helper script: `./setup.sh` (or `make setup`).

Then open:

| What              | Address                    |
| ----------------- | -------------------------- |
| Web app           | http://localhost:3000      |
| API               | http://localhost:8000      |
| API documentation | http://localhost:8000/docs |

### First login

The first admin account is created automatically on the first start. Set the username and password in the `.env` file before starting:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose-a-long-password
```

If you leave the password empty, a random one is generated and printed once in the log:

```bash
docker compose logs backend | grep "generated password"
```

Sign in, then add other people on the **Users** page.

### Analyze a capture

Go to **Call Log**, drop in one or more PCAP/PCAPNG files (up to 25 at once), and click a call to see its details.

---

## Live Monitoring and Recording (optional)

Live monitoring runs as a separate container that listens on a mirror port of your switch.

1. On the switch, mirror the PBX port (both directions) to a free port cabled to the monitoring machine's second network card.
2. Find the card's name and set it in `.env`:

   ```bash
   docker compose --profile capture run --rm capture python -m app.capture --list-interfaces
   ```

   ```env
   CAPTURE_INTERFACE=enp2s0
   ```

3. Start it:

   ```bash
   docker compose --profile capture up -d --build
   ```

Open **Live Calls** to see calls as they happen. Calls are recorded automatically.

Full guide with switch setup, troubleshooting and all settings: [docs/LIVE_CAPTURE.md](docs/LIVE_CAPTURE.md).

> Recording phone calls can legally require notice to or consent from the people on the call. You are responsible for following the laws that apply to you. Set `LIVE_RECORDING_ENABLED=false` to keep call records without audio.

---

## Who Can See What

| Role       | Access |
| ---------- | ------ |
| Admin      | Everything: users, deleting data, recordings, audit log |
| Supervisor | All calls and live calls, play and download recordings, upload captures, analytics |
| User       | Only calls for their own extensions; can play those recordings |

---

## Configuration

Everything works with the defaults. Set options in the `.env` file in the project folder.

| Setting | Default | What it does |
| ------- | ------- | ------------ |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `admin`, generated | First admin account |
| `CAPTURE_INTERFACE` | `eth1` | Network card that receives the mirrored traffic |
| `LIVE_RECORDING_ENABLED` | `true` | Record live calls |
| `RECORDINGS_RETENTION_DAYS` | `180` | Delete recordings older than this (0 keeps them forever) |
| `RECORDINGS_MAX_GB` | `0` | Keep recordings under this size, oldest deleted first (0 means no limit) |
| `SAVE_CALL_AUDIO` | `false` | Also rebuild audio from uploaded PCAP files |
| `DATABASE_URL` | SQLite | Use PostgreSQL instead, for example `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME` |

Recordings are saved in `data/recordings`. Only audio is removed by retention; call records and quality data are kept.

---

## Requirements

* Docker and Docker Compose

or, to run without Docker:

* Python 3.11+
* Node.js 18+

For live monitoring: a **Linux** machine (Docker Desktop on Windows or macOS cannot reach the physical network cards), a second network card for the mirror port and an SSD for recordings. A Raspberry Pi 5 or a small x86 PC with 8 GB RAM is enough for about 10 simultaneous calls. Recording uses roughly 115 MB per hour of call audio.

---

## Limitations

* SIP and RTP must be unencrypted. TLS and SRTP calls cannot be analyzed or recorded
* Audio recording supports the G.711 codec (PCMU/PCMA) only
* Live monitoring needs a Linux host and a switch with port mirroring. Uploading and analyzing PCAP files works on any system

---

## Local Development

Backend:

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Run the tests:

```bash
cd backend
pytest -v
```

---

## API

Interactive documentation is at `http://localhost:8000/docs`. All endpoints except `/health` and `/auth/login` need an `Authorization: Bearer <token>` header; get the token from `POST /auth/login`.

---

## Contributing

Contributions are welcome. The most valuable contribution is anonymized SIP capture files from real systems, which help improve compatibility across VoIP vendors. See `CONTRIBUTING.md`.

---

## License

MIT License

## Screenshots

<img width="1896" height="862" alt="image" src="https://github.com/user-attachments/assets/696cee94-4a86-4c69-aaf7-66455971b1ca" />

<img width="1852" height="858" alt="image" src="https://github.com/user-attachments/assets/7ae06195-d8b0-4561-bb42-03a5ad61f5a0" />

<img width="1892" height="857" alt="image" src="https://github.com/user-attachments/assets/be882f1f-3e7b-4b07-b7b6-663f9851d7bd" />

