# Live Capture Guide

Live capture listens to a **mirror (SPAN) port** on your network, follows SIP calls as
they happen, records the audio, and stores everything in the same database as uploaded
PCAPs. Your PBX and phones are not touched and do not know it is there.

```
 PBX / trunk ── switch ──────── phones
                  │ mirror (SPAN) port
                  ▼
        second network card (no IP address)
                  ▼
        capture container → database ← backend ← web UI
```

## 1. What you need

* A **Linux** machine running Docker (Docker Desktop on Windows or macOS only sees its own virtual network, not your network cards) with a **second network card** dedicated to the mirror port
  (the first stays for the web UI). A Raspberry Pi 5 (arm64) or an x86 mini-PC with 8 GB RAM
  is enough for roughly 10 simultaneous calls.
* A switch that supports port mirroring (SPAN).
* An SSD for recordings. A G.711 call is about **115 MB per hour** of audio.
* Unencrypted SIP and RTP. TLS and SRTP calls are detected only as far as the signalling
  is readable; they cannot be recorded (see Limitations).

## 2. Configure the mirror port

On your switch, mirror the port(s) where SIP and media pass, **both directions**
(receive and transmit), to the port cabled to the capture machine's second card.

Where to mirror: pick the port that carries **both** the SIP signalling and the RTP audio.
Usually that is the **PBX port**; if the PBX talks to the provider through a separate
gateway, mirror that port too. Phones on the same LAN as the PBX are seen through the
PBX port. If calls show up but have no audio, RTP is taking a path you are not mirroring.

Generic example (Cisco-style syntax; yours will differ, check your switch manual):

```text
monitor session 1 source interface Gi1/0/1 both
monitor session 1 destination interface Gi1/0/24
```

VLAN tags on the mirrored traffic are fine; they are ignored automatically.
Do not give the capture card an IP address; it only listens.

## 3. Choose the interface

Interface names differ per machine (`eth1`, `enp2s0`, `ens19`, ...). List them:

```bash
docker compose --profile capture run --rm capture python -m app.capture --list-interfaces
```

Put the one cabled to the mirror port in the **root** `.env`:

```text
CAPTURE_INTERFACE=enp2s0
```

## 4. Start it

```bash
docker compose up -d                          # web UI and API (as before)
docker compose --profile capture up -d --build   # live capture
```

Open the web UI and sign in. The **Live Calls** page shows a green banner when capture is
running. If a call is made, it appears under *In progress* within seconds and moves to
*Just finished* when it ends.

### First login

The first admin is created on the first start. Set the credentials in `.env` before that:

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose-a-long-password
```

If you leave `ADMIN_PASSWORD` empty, a random password is generated and printed once:

```bash
docker compose logs backend | grep "generated password"
```

Create other accounts on the **Users** page. Change your own password from the sidebar.
Serve the web UI over HTTPS (for example behind a reverse proxy) if anyone logs in over an
untrusted network.

## 5. Roles

| Role       | Can do |
|------------|--------|
| Admin      | Everything: users, deleting data, recordings, audit log |
| Supervisor | See all calls and live calls, play and download recordings, upload captures, analytics |
| User       | See live calls and call history **only for their assigned extensions**, play those recordings (no download) |

Every recording play and download, deletion and login is written to the **Audit Log**
(admin only).

## 6. Recordings and retention

* Recording is **on by default** for live calls. Turn it off with `LIVE_RECORDING_ENABLED=false`;
  call records and quality metrics are still kept.
* Recording telephone calls can legally require notice to or consent from the parties.
  You are responsible for complying with the laws that apply to you; the capture service
  logs a reminder at start-up.
* Recordings are deleted automatically (checked hourly):

  | Setting | Default | Meaning |
  |---------|---------|---------|
  | `RECORDINGS_RETENTION_DAYS` | 180 | Delete recordings older than this (0 = keep forever) |
  | `RECORDINGS_MAX_GB` | 0 | If recordings exceed this size, delete the oldest first (0 = no limit) |

  Only the audio is removed; the call record and quality metrics stay.

## 7. Settings reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAPTURE_INTERFACE` | `eth1` | Network card receiving the mirrored traffic |
| `CAPTURE_FILTER` | `udp or tcp port 5060` | BPF filter (RTP uses dynamic UDP ports, so UDP is not limited) |
| `LIVE_RECORDING_ENABLED` | `true` | Record live call audio |
| `CAPTURE_SETTLE_SECONDS` | `30` | Wait after BYE/CANCEL/failure before closing a call |
| `CAPTURE_IDLE_TIMEOUT` | `60` | Close an unanswered call after this much silence |
| `CAPTURE_MEDIA_IDLE_TIMEOUT` | `120` | Close an answered call whose audio stopped (missed BYE) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / generated | First admin account |
| `AUTH_SECRET` | generated | Signing key for login tokens |

## 8. Troubleshooting

**Banner says "Capture cannot start: Network interface '...' does not exist".**
The name in `CAPTURE_INTERFACE` is not a network card inside the container; the message lists the names that exist. On Windows or macOS (Docker Desktop) no physical card is visible, so run live capture on a Linux machine.

**Banner says "not set up" or "stopped reporting".**
Check the service: `docker compose --profile capture ps` and `docker compose logs capture`.
"Permission denied" means the container lacks raw-socket access (the compose file grants it;
do not remove `cap_add` or `network_mode: host`). "Cannot capture on '...'" means the
interface name is wrong; list the names as in step 3.

**Banner is green but no calls appear.**
The mirror is not delivering SIP. Check on the host: `sudo tcpdump -ni <interface> port 5060`.
If nothing shows, recheck the switch's mirror session and that it mirrors both directions.
Calls that began before capture started are not shown (tracking starts at the INVITE).

**Calls appear but have no recording.**
RTP is not reaching the capture card (mirror the PBX port, or the path the audio really takes),
or the codec is not G.711 (PCMU/PCMA), or recording is off or removed by retention.

**"Dropped" count keeps rising.**
The machine cannot keep up. Narrow the mirror to fewer ports, use an SSD, or a faster machine.

**Everything is doubled.**
Some switches send each frame twice on a mirror port. Duplicates are filtered automatically.

## 9. Limitations

* TLS-encrypted SIP and SRTP media cannot be read or recorded.
* Audio reconstruction supports G.711 (PCMU/PCMA) only.
* SIP over TCP is read one message per packet (no stream reassembly).
* Two simultaneous calls that announce the same media address and port cannot be told apart.
* A call whose audio stops for longer than `CAPTURE_MEDIA_IDLE_TIMEOUT` (for example a very long
  silent hold) is closed early.
* The SIP message list of a call is saved when the call ends, so an in-progress call shows
  its state but not yet its messages.
* Backend and capture share one SQLite file, fine for this call volume.
