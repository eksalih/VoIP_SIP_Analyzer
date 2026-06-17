# VoIP SIP Analyzer

A modern VoIP packet analysis platform that helps engineers, telecom teams, and support staff quickly understand what happened during a SIP call.

Upload a packet capture file (`.pcap` or `.pcapng`) and the system automatically:

* Detects SIP calls
* Reconstructs call flows
* Classifies call outcomes
* Displays SIP ladder diagrams
* Generates analytics and statistics
* Validates call scenarios with automated PASS/FAIL testing

---

## Why This Project?

Troubleshooting VoIP issues often requires manually inspecting thousands of packets in Wireshark.

VoIP SIP Analyzer automates that process by converting SIP signaling into easy-to-understand call records and visualizations.

Instead of searching through packets manually, you can immediately see:

* Who called whom
* Whether the call was answered
* Why the call failed
* Which calls were rejected or cancelled
* Overall call statistics

---

## Features

### SIP Packet Analysis

Supports packet captures from:

* Wireshark
* tcpdump
* tshark
* Network monitoring systems

### Automatic Call Classification

The analyzer automatically identifies:

| Call Outcome | Description                                   |
| ------------ | --------------------------------------------- |
| ANSWERED     | Call connected successfully                   |
| MISSED       | Phone rang but was not answered               |
| REJECTED     | User explicitly declined or was busy          |
| CANCELLED    | Caller cancelled before completion            |
| FAILED       | Network or routing error prevented completion |

### SIP Ladder Diagrams

Visual call-flow diagrams help users understand SIP signaling without reading raw packets.

Example:

Caller                    PBX                    Callee
| INVITE ---------------->|                      |
|                          | INVITE ------------>|
|                          |<----- 180 Ringing --|
|<----- 180 Ringing -------|                      |
|                          |<------ 200 OK ------|
|<------ 200 OK -----------|                      |
| ACK -------------------->|                      |

### Analytics Dashboard

View:

* Total calls
* Answer rate
* Failure rate
* Rejected calls
* Call outcome distribution
* Historical trends

### Replay Testing

Validate SIP captures against expected outcomes and automatically generate PASS/FAIL results.

---

## Screenshots

<img width="1896" height="862" alt="image" src="https://github.com/user-attachments/assets/696cee94-4a86-4c69-aaf7-66455971b1ca" />

<img width="1852" height="858" alt="image" src="https://github.com/user-attachments/assets/7ae06195-d8b0-4561-bb42-03a5ad61f5a0" />

<img width="1892" height="857" alt="image" src="https://github.com/user-attachments/assets/be882f1f-3e7b-4b07-b7b6-663f9851d7bd" />




## Quick Start

### Run with Docker

```bash
git clone https://github.com/eksalih/VoIP_SIP_Analyzer.git
cd VoIP_SIP_Analyzer

docker compose up --build
```

Application URLs:

Frontend:
http://localhost:3000

Backend API:
http://localhost:8000

Swagger Documentation:
http://localhost:8000/docs

---

## Supported SIP Platforms

Tested with captures from:

* Asterisk
* FreePBX
* 3CX
* Yeastar
* Grandstream
* Cisco
* Avaya

Any standards-compliant SIP platform should work.

---

## Call Detection Logic

Examples of how calls are classified:

| SIP Flow                      | Result    |
| ----------------------------- | --------- |
| INVITE → 200 OK → BYE         | ANSWERED  |
| INVITE → 180 Ringing → CANCEL | MISSED    |
| INVITE → 486 Busy Here        | REJECTED  |
| INVITE → 603 Decline          | REJECTED  |
| INVITE → CANCEL               | CANCELLED |
| INVITE → 404 Not Found        | FAILED    |
| INVITE → 5xx Server Error     | FAILED    |

Rejected calls are intentionally separated from missed calls to provide accurate reporting.

---

## Technology Stack

### Backend

* FastAPI
* SQLAlchemy
* PyShark
* Scapy
* Pydantic
* Pytest

### Frontend

* React
* TypeScript
* Vite
* Tailwind CSS

### Infrastructure

* Docker
* Docker Compose
* SQLite
* PostgreSQL (optional)

---

## API Endpoints

| Method | Endpoint             | Description           |
| ------ | -------------------- | --------------------- |
| GET    | /health              | Service health check  |
| POST   | /upload-pcap         | Upload packet capture |
| GET    | /calls               | Retrieve call records |
| GET    | /calls/{id}          | Retrieve call details |
| GET    | /calls/{id}/events   | Retrieve SIP events   |
| GET    | /analytics           | Analytics data        |
| POST   | /replay-test         | Run validation test   |
| GET    | /replay-test/history | Test history          |

---

## Requirements

Recommended:

* Python 3.11+
* Node.js 18+
* Docker
* tshark

The analyzer uses tshark for the best parsing performance and automatically falls back to Scapy if tshark is unavailable.

---

## Limitations

Current version supports:

* SIP over UDP/TCP
* Unencrypted SIP traffic

Not currently supported:

* SIP-TLS
* SRTP
* Encrypted signaling

---

## Use Cases

* VoIP troubleshooting
* Telecom QA testing
* SIP interoperability validation
* PBX migration projects
* Call-center diagnostics
* Network operations monitoring
* VoIP training and education

---

## Contributing

Contributions are welcome.

Feel free to:

* Open issues
* Submit pull requests
* Suggest new SIP classifications
* Add support for additional protocols

---

## License

MIT License

Feel free to use, modify, and distribute this project.
