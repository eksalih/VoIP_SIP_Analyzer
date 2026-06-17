FROM python:3.12-slim

# Install tshark for pyshark support
RUN apt-get update && apt-get install -y \
    tshark \
    libpcap-dev \
    && rm -rf /var/lib/apt/lists/*

# Allow tshark without root
RUN echo "wireshark-common wireshark-common/install-setuid boolean true" | debconf-set-selections \
    && dpkg-reconfigure -f noninteractive wireshark-common || true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
