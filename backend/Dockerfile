FROM python:3.12-slim

# tshark is OPTIONAL and not installed by default -- the app uses Scapy as its
# primary PCAP parser, which has no external binary dependency. Build with
# `docker build --build-arg INSTALL_TSHARK=true .` if you want to enable the
# optional PyShark backend (SIP_PARSER_BACKEND=pyshark) for its deeper
# protocol decoding on top of Scapy's regex-based parser.
ARG INSTALL_TSHARK=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpcap-dev \
    curl \
    && if [ "$INSTALL_TSHARK" = "true" ]; then \
         echo "wireshark-common wireshark-common/install-setuid boolean true" | debconf-set-selections \
         && apt-get install -y --no-install-recommends tshark \
         && dpkg-reconfigure -f noninteractive wireshark-common; \
       fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
