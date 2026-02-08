# rock-paper-scissors

Federated Rock-Paper-Scissors game with SPIFFE mTLS authentication and supply chain security.

## Overview

A peer-to-peer game where each player runs an interactive server that can **simultaneously receive and issue challenges**. Authentication uses SPIFFE mTLS with cross-domain federation.

### Architecture

- Each player runs **one** interactive process (no separate serve/play modes)
- The process listens for incoming challenges AND lets you issue challenges from a command prompt
- All communication uses the **commit-reveal protocol** over SPIFFE mTLS
- Scores are tracked per SPIFFE ID and queryable via HTTPS

### Commit-Reveal Protocol (3 Messages)

1. **Challenge** (Challenger → Responder): `SHA256(move + salt)` commitment
2. **Response** (Responder → Challenger): Responder's plaintext move
3. **Reveal** (Challenger → Responder): Challenger's move + salt for verification

---

## Quick Start

### Option 1: Docker Image (Recommended)

```bash
docker pull ghcr.io/npaulat99/rock-paper-scissors:latest
```

### Option 2: Download Signed Binary

```bash
curl -L -o rps-game https://github.com/npaulat99/rock-paper-scissors/releases/latest/download/rps-game
curl -L -o rps-game.cosign.bundle https://github.com/npaulat99/rock-paper-scissors/releases/latest/download/rps-game.cosign.bundle

cosign verify-blob \
  --bundle rps-game.cosign.bundle \
  --certificate-identity-regexp="https://github.com/.+" \
  --certificate-oidc-issuer-regexp="https://token.actions.githubusercontent.com" \
  rps-game

chmod +x rps-game
./rps-game --help
```

### Option 3: Build from Source

```bash
git clone https://github.com/npaulat99/rock-paper-scissors.git
cd rock-paper-scissors
pip install -r requirements.txt
python src/app/cli.py --help
```

---

## Supply Chain Security

✅ **Phase 1** — Trivy scanning (source, Docker, IaC, image)  
✅ **Phase 2** — SLSA provenance, SBOM, vulnerability attestations  
✅ **Phase 3** — Cosign keyless signing (GitHub OIDC)  
✅ **Phase 4** — Automated GitHub Actions CI/CD pipeline  
✅ **Bonus** — Binary built in CI, downloadable from pipeline, signature verification  

---

# Setup Guide for Noah

**Trust Domain:** `noah.inter-cloud-thi.de`  
**Public IP:** `4.185.66.130`  
**SPIFFE ID:** `spiffe://noah.inter-cloud-thi.de/game-server-noah`  

## 1. Install SPIRE

```bash
cd ~
wget https://github.com/spiffe/spire/releases/download/v1.13.3/spire-1.13.3-linux-amd64-musl.tar.gz
tar -xzf spire-1.13.3-linux-amd64-musl.tar.gz
cd spire-1.13.3
sudo mkdir -p /opt/spire/server /opt/spire/agent
sudo mkdir -p /tmp/spire-server /tmp/spire-agent
```

## 2. Configure SPIRE Server

```bash
sudo tee /opt/spire/server/server.conf > /dev/null <<'EOF'
server {
  bind_address = "0.0.0.0"
  bind_port = "8081"
  trust_domain = "noah.inter-cloud-thi.de"
  data_dir = "/tmp/spire-server/data"
  log_level = "INFO"
}

plugins {
  DataStore "sql" {
    plugin_data {
      database_type = "sqlite3"
      connection_string = "/tmp/spire-server/data/datastore.sqlite3"
    }
  }
  NodeAttestor "join_token" {
    plugin_data {}
  }
  KeyManager "disk" {
    plugin_data {
      keys_path = "/tmp/spire-server/data/keys.json"
    }
  }
}
EOF
```

## 3. Configure SPIRE Agent

```bash
sudo tee /opt/spire/agent/agent.conf > /dev/null <<'EOF'
agent {
  data_dir = "/tmp/spire-agent/data"
  log_level = "INFO"
  server_address = "127.0.0.1"
  server_port = "8081"
  socket_path = "/tmp/spire-agent/public/api.sock"
  trust_domain = "noah.inter-cloud-thi.de"
  trust_bundle_path = "/tmp/bootstrap-bundle.crt"
}

plugins {
  NodeAttestor "join_token" {
    plugin_data {}
  }
  KeyManager "disk" {
    plugin_data {
      directory = "/tmp/spire-agent/data"
    }
  }
  WorkloadAttestor "unix" {
    plugin_data {}
  }
}
EOF
```

## 4. Start SPIRE Server

```bash
cd ~/spire-1.13.3

# Kill any existing processes
sudo pkill -f spire-server || true
sudo pkill -f spire-agent || true
sleep 2

# Clean up
sudo rm -f /tmp/spire-server/private/api.sock
sudo rm -f /tmp/spire-agent/public/api.sock
sudo mkdir -p /tmp/spire-server/data
sudo mkdir -p /tmp/spire-agent/data /tmp/spire-agent/public

# Start server
sudo nohup ./bin/spire-server run -config /opt/spire/server/server.conf > /tmp/spire-server.log 2>&1 &
sleep 5

# Verify
sudo ./bin/spire-server healthcheck

# Save bootstrap bundle for agent
sudo ./bin/spire-server bundle show > /tmp/bootstrap-bundle.crt
```

## 5. Start SPIRE Agent

```bash
cd ~/spire-1.13.3

TOKEN=$(sudo ./bin/spire-server token generate \
  -spiffeID spiffe://noah.inter-cloud-thi.de/agent/myagent \
  | grep Token | awk '{print $2}')
echo "Token: $TOKEN"

sudo nohup ./bin/spire-agent run \
  -config /opt/spire/agent/agent.conf \
  -joinToken $TOKEN > /tmp/spire-agent.log 2>&1 &
sleep 5

# Verify
ls -la /tmp/spire-agent/public/api.sock
```

## 6. Register Workload with Federation

```bash
cd ~/spire-1.13.3

sudo ./bin/spire-server entry create \
  -spiffeID spiffe://noah.inter-cloud-thi.de/game-server-noah \
  -parentID spiffe://noah.inter-cloud-thi.de/agent/myagent \
  -selector unix:uid:$(id -u) \
  -federatesWith spiffe://raghad.inter-cloud-thi.de

# Verify — should show FederatesWith: raghad.inter-cloud-thi.de
sudo ./bin/spire-server entry show
```

**If it says "AlreadyExists":** delete the old entry first:
```bash
# Find the entry ID
sudo ./bin/spire-server entry show
# Delete it (replace with actual ID)
sudo ./bin/spire-server entry delete -entryID <ENTRY_ID>
# Then re-run the create command above
```

## 7. Import Raghad's Trust Bundle

Import Raghad's trust bundle by pasting the JSON directly:

```bash
cd ~/spire-1.13.3

cat <<'BUNDLE_EOF' | sudo ./bin/spire-server bundle set -format spiffe -id spiffe://raghad.inter-cloud-thi.de
{
    "keys": [
        {
            "use": "x509-svid",
            "kty": "EC",
            "crv": "P-256",
            "x": "<raghad-x-value>",
            "y": "<raghad-y-value>",
            "x5c": ["<raghad-x5c-cert>"]
        }
    ],
    "spiffe_sequence": 1
}
BUNDLE_EOF

# Verify both bundles are listed
sudo ./bin/spire-server bundle list
```

> **Note:** Replace the placeholder values with Raghad's actual trust bundle.
> To get a fresh bundle from Raghad: she runs `sudo ./bin/spire-server bundle show -format spiffe`

## 8. Fetch Certificates (with Combined Bundle)

This is the critical step — after importing Raghad's bundle AND registering with `-federatesWith`, the agent will issue certs with **both** CAs in the federated bundle.

```bash
cd ~/spire-1.13.3

# If agent hasn't synced (gives "no identity issued"), restart it:
sudo pkill -f spire-agent
sleep 3
sudo rm -rf /tmp/spire-agent/data/*
sudo rm -f /tmp/spire-agent/public/api.sock
TOKEN=$(sudo ./bin/spire-server token generate \
  -spiffeID spiffe://noah.inter-cloud-thi.de/agent/myagent \
  | grep Token | awk '{print $2}')
sudo nohup ./bin/spire-agent run \
  -config /opt/spire/agent/agent.conf \
  -joinToken $TOKEN > /tmp/spire-agent.log 2>&1 &
sleep 30

# Verify agent picked up the entry
sudo tail -20 /tmp/spire-agent.log
# Should show: "Creating X509-SVID" for game-server-noah

# Fetch certs
mkdir -p ~/certs
rm -f ~/certs/*.pem
SPIFFE_ENDPOINT_SOCKET=/tmp/spire-agent/public/api.sock \
  ~/spire-1.13.3/bin/spire-agent api fetch x509 -write ~/certs/

# Verify federated bundle was fetched
ls ~/certs/
# Should show: svid.0.pem, svid.0.key, bundle.0.pem, federated_bundle.0.0.pem

# IMPORTANT: Combine both CAs into one bundle file
cat ~/certs/bundle.0.pem ~/certs/federated_bundle.0.0.pem > ~/certs/svid_bundle.pem
mv ~/certs/svid.0.pem ~/certs/svid.pem
mv ~/certs/svid.0.key ~/certs/svid_key.pem

# Verify 2 CAs in combined bundle
grep -c "BEGIN CERTIFICATE" ~/certs/svid_bundle.pem
# Must output: 2
```

## 9. Run the Game

```bash
docker run -it --rm \
  --network host \
  -v ~/certs:/app/certs:ro \
  -e RPS_BIND=0.0.0.0:9002 \
  -e RPS_SPIFFE_ID=spiffe://noah.inter-cloud-thi.de/game-server-noah \
  -e RPS_PUBLIC_URL=https://4.185.66.130:9002 \
  -e RPS_MTLS=1 \
  ghcr.io/npaulat99/rock-paper-scissors:latest
```

You'll see an interactive prompt:
```
============================================================
  Rock-Paper-Scissors — Interactive Mode
  SPIFFE ID : spiffe://noah.inter-cloud-thi.de/game-server-noah
  Listening : https://0.0.0.0:9002
  Scoreboard: https://0.0.0.0:9002/v1/rps/scores
============================================================

Commands:
  challenge <peer_url> <peer_spiffe_id>  — Start a match
  scores                                 — Show scoreboard
  quit / exit                            — Exit

rps>
```

### Challenge Raghad

```
rps> challenge https://4.185.211.9:9002 spiffe://raghad.inter-cloud-thi.de/game-server-raghad
```

### View Scores

```
rps> scores
```

---

# Setup Guide for Raghad

**Trust Domain:** `raghad.inter-cloud-thi.de`  
**Public IP:** `4.185.211.9`  
**SPIFFE ID:** `spiffe://raghad.inter-cloud-thi.de/game-server-raghad`  

## 1. Install SPIRE

```bash
cd ~
wget https://github.com/spiffe/spire/releases/download/v1.13.3/spire-1.13.3-linux-amd64-musl.tar.gz
tar -xzf spire-1.13.3-linux-amd64-musl.tar.gz
cd spire-1.13.3
sudo mkdir -p /opt/spire/server /opt/spire/agent
sudo mkdir -p /tmp/spire-server /tmp/spire-agent
```

## 2. Configure SPIRE Server

```bash
sudo tee /opt/spire/server/server.conf > /dev/null <<'EOF'
server {
  bind_address = "0.0.0.0"
  bind_port = "8081"
  trust_domain = "raghad.inter-cloud-thi.de"
  data_dir = "/tmp/spire-server/data"
  log_level = "INFO"
}

plugins {
  DataStore "sql" {
    plugin_data {
      database_type = "sqlite3"
      connection_string = "/tmp/spire-server/data/datastore.sqlite3"
    }
  }
  NodeAttestor "join_token" {
    plugin_data {}
  }
  KeyManager "disk" {
    plugin_data {
      keys_path = "/tmp/spire-server/data/keys.json"
    }
  }
}
EOF
```

## 3. Configure SPIRE Agent

```bash
sudo tee /opt/spire/agent/agent.conf > /dev/null <<'EOF'
agent {
  data_dir = "/tmp/spire-agent/data"
  log_level = "INFO"
  server_address = "127.0.0.1"
  server_port = "8081"
  socket_path = "/tmp/spire-agent/public/api.sock"
  trust_domain = "raghad.inter-cloud-thi.de"
  trust_bundle_path = "/tmp/bootstrap-bundle.crt"
}

plugins {
  NodeAttestor "join_token" {
    plugin_data {}
  }
  KeyManager "disk" {
    plugin_data {
      directory = "/tmp/spire-agent/data"
    }
  }
  WorkloadAttestor "unix" {
    plugin_data {}
  }
}
EOF
```

## 4. Start SPIRE Server

```bash
cd ~/spire-1.13.3

sudo pkill -f spire-server || true
sudo pkill -f spire-agent || true
sleep 2
sudo rm -f /tmp/spire-server/private/api.sock
sudo rm -f /tmp/spire-agent/public/api.sock
sudo mkdir -p /tmp/spire-server/data
sudo mkdir -p /tmp/spire-agent/data /tmp/spire-agent/public

sudo nohup ./bin/spire-server run -config /opt/spire/server/server.conf > /tmp/spire-server.log 2>&1 &
sleep 5

sudo ./bin/spire-server healthcheck
sudo ./bin/spire-server bundle show > /tmp/bootstrap-bundle.crt
```

## 5. Start SPIRE Agent

```bash
cd ~/spire-1.13.3

TOKEN=$(sudo ./bin/spire-server token generate \
  -spiffeID spiffe://raghad.inter-cloud-thi.de/agent/myagent \
  | grep Token | awk '{print $2}')
echo "Token: $TOKEN"

sudo nohup ./bin/spire-agent run \
  -config /opt/spire/agent/agent.conf \
  -joinToken $TOKEN > /tmp/spire-agent.log 2>&1 &
sleep 5

ls -la /tmp/spire-agent/public/api.sock
```

## 6. Register Workload with Federation

```bash
cd ~/spire-1.13.3

sudo ./bin/spire-server entry create \
  -spiffeID spiffe://raghad.inter-cloud-thi.de/game-server-raghad \
  -parentID spiffe://raghad.inter-cloud-thi.de/agent/myagent \
  -selector unix:uid:$(id -u) \
  -federatesWith spiffe://noah.inter-cloud-thi.de

sudo ./bin/spire-server entry show
```

## 7. Import Noah's Trust Bundle

```bash
cd ~/spire-1.13.3

# Get Noah's bundle: he runs: sudo ./bin/spire-server bundle show -format spiffe
# Then paste it here:
cat <<'BUNDLE_EOF' | sudo ./bin/spire-server bundle set -format spiffe -id spiffe://noah.inter-cloud-thi.de
{
    "keys": [
        {
            "use": "x509-svid",
            "kty": "EC",
            "crv": "P-256",
            "x": "<noah-x-value>",
            "y": "<noah-y-value>",
            "x5c": ["<noah-x5c-cert>"]
        }
    ],
    "spiffe_sequence": 1
}
BUNDLE_EOF

sudo ./bin/spire-server bundle list
```

## 8. Fetch Certificates (with Combined Bundle)

```bash
cd ~/spire-1.13.3

# Restart agent to pick up federation
sudo pkill -f spire-agent
sleep 3
sudo rm -rf /tmp/spire-agent/data/*
sudo rm -f /tmp/spire-agent/public/api.sock
TOKEN=$(sudo ./bin/spire-server token generate \
  -spiffeID spiffe://raghad.inter-cloud-thi.de/agent/myagent \
  | grep Token | awk '{print $2}')
sudo nohup ./bin/spire-agent run \
  -config /opt/spire/agent/agent.conf \
  -joinToken $TOKEN > /tmp/spire-agent.log 2>&1 &
sleep 30

sudo tail -20 /tmp/spire-agent.log
# Should show: "Creating X509-SVID" for game-server-raghad

mkdir -p ~/certs
rm -f ~/certs/*.pem
SPIFFE_ENDPOINT_SOCKET=/tmp/spire-agent/public/api.sock \
  ~/spire-1.13.3/bin/spire-agent api fetch x509 -write ~/certs/

# IMPORTANT: Combine both CAs into one bundle file
cat ~/certs/bundle.0.pem ~/certs/federated_bundle.0.0.pem > ~/certs/svid_bundle.pem
mv ~/certs/svid.0.pem ~/certs/svid.pem
mv ~/certs/svid.0.key ~/certs/svid_key.pem

# Verify 2 CAs in combined bundle
grep -c "BEGIN CERTIFICATE" ~/certs/svid_bundle.pem
# Must output: 2
```

## 9. Run the Game

```bash
docker pull ghcr.io/npaulat99/rock-paper-scissors:latest

docker run -it --rm \
  --network host \
  -v ~/certs:/app/certs:ro \
  -e RPS_BIND=0.0.0.0:9002 \
  -e RPS_SPIFFE_ID=spiffe://raghad.inter-cloud-thi.de/game-server-raghad \
  -e RPS_PUBLIC_URL=https://4.185.211.9:9002 \
  -e RPS_MTLS=1 \
  ghcr.io/npaulat99/rock-paper-scissors:latest
```

### Challenge Noah

```
rps> challenge https://4.185.66.130:9002 spiffe://noah.inter-cloud-thi.de/game-server-noah
```

---

# ACME / Let's Encrypt Public Scoreboard (Bonus)

The game supports a **second HTTPS endpoint** for the scoreboard using **Let's Encrypt (WebPKI)** certificates, separate from the SPIFFE mTLS game port.

This demonstrates two distinct trust models running simultaneously:
- **Port 9002**: SPIFFE mTLS — client certificates required, peer identity validated via SPIFFE URI SANs
- **Port 443**: WebPKI / ACME — standard server-only TLS, publicly accessible scoreboard

## Obtain Let's Encrypt Certificate

On the Azure VM (requires DNS zone access — see ACME lab):

```bash
# Install certbot
sudo apt install -y certbot

# Use standalone mode (stop any service on port 80 first)
sudo certbot certonly --standalone \
  -d noah.inter-cloud-thi.de \
  --agree-tos --no-eff-email \
  -m noah@student.th-ingolstadt.de

# Certs are in /etc/letsencrypt/live/noah.inter-cloud-thi.de/
sudo ls /etc/letsencrypt/live/noah.inter-cloud-thi.de/
# fullchain.pem  privkey.pem
```

**Alternative — DNS-01 challenge (if port 80 is blocked):**
```bash
# Using Azure DNS plugin
sudo apt install -y python3-certbot-dns-azure
sudo certbot certonly --dns-azure \
  --dns-azure-config /etc/letsencrypt/azure.ini \
  -d noah.inter-cloud-thi.de \
  --agree-tos --no-eff-email \
  -m noah@student.th-ingolstadt.de
```

## Run with ACME Scoreboard

```bash
# Copy certs to a readable location
sudo cp /etc/letsencrypt/live/noah.inter-cloud-thi.de/fullchain.pem ~/acme-certs/
sudo cp /etc/letsencrypt/live/noah.inter-cloud-thi.de/privkey.pem ~/acme-certs/
sudo chown $USER:$USER ~/acme-certs/*.pem

# Run with both mTLS game + ACME scoreboard
docker run -it --rm \
  --network host \
  -v ~/certs:/app/certs:ro \
  -v ~/acme-certs:/app/acme-certs:ro \
  -e RPS_BIND=0.0.0.0:9002 \
  -e RPS_SPIFFE_ID=spiffe://noah.inter-cloud-thi.de/game-server-noah \
  -e RPS_PUBLIC_URL=https://4.185.66.130:9002 \
  -e RPS_MTLS=1 \
  -e RPS_ACME_CERT=/app/acme-certs/fullchain.pem \
  -e RPS_ACME_KEY=/app/acme-certs/privkey.pem \
  -e RPS_ACME_BIND=0.0.0.0:443 \
  ghcr.io/npaulat99/rock-paper-scissors:latest
```

The scoreboard is then publicly accessible at:
```
https://noah.inter-cloud-thi.de/v1/rps/scores
```

---

# Troubleshooting

## "No identity issued" when fetching certs

The SPIRE agent hasn't synced the workload entry. Fix:
```bash
cd ~/spire-1.13.3
sudo pkill -f spire-agent
sleep 3
sudo rm -rf /tmp/spire-agent/data/*
sudo rm -f /tmp/spire-agent/public/api.sock
TOKEN=$(sudo ./bin/spire-server token generate \
  -spiffeID spiffe://YOUR_DOMAIN/agent/myagent \
  | grep Token | awk '{print $2}')
sudo nohup ./bin/spire-agent run \
  -config /opt/spire/agent/agent.conf \
  -joinToken $TOKEN > /tmp/spire-agent.log 2>&1 &
sleep 30
sudo tail -20 /tmp/spire-agent.log
```

## "AlreadyExists" when creating entries

Delete the old entry first:
```bash
sudo ./bin/spire-server entry show   # Note the Entry ID
sudo ./bin/spire-server entry delete -entryID <THE_ID>
# Then re-create
```

## Timeout connecting to peer

1. Check the peer's server is running: `sudo ss -tlnp | grep 9002`
2. Test TCP connectivity: `nc -zv -w 5 <PEER_IP> 9002`
3. If blocked: open port 9002 TCP inbound in **Azure NSG** (Portal → VM → Networking)
4. Check local firewall: `sudo ufw allow 9002/tcp`

## SSL/TLS errors

- Ensure `svid_bundle.pem` contains **2 certificates** (both CAs):
  ```bash
  grep -c "BEGIN CERTIFICATE" ~/certs/svid_bundle.pem  # Must be 2
  ```
- Re-fetch certs if expired (SPIRE SVIDs default to 1 hour):
  ```bash
  SPIFFE_ENDPOINT_SOCKET=/tmp/spire-agent/public/api.sock \
    ~/spire-1.13.3/bin/spire-agent api fetch x509 -write ~/certs/
  cat ~/certs/bundle.0.pem ~/certs/federated_bundle.0.0.pem > ~/certs/svid_bundle.pem
  mv ~/certs/svid.0.pem ~/certs/svid.pem
  mv ~/certs/svid.0.key ~/certs/svid_key.pem
  ```

## Checking registered entries

```bash
sudo ./bin/spire-server entry show
# Verify:
# - SPIFFE ID matches what you pass to --spiffe-id
# - FederatesWith lists the peer's trust domain
# - Selector matches: unix:uid:<your-uid>
```

---

# Project Structure

```
rock-paper-scissors/
├── .github/workflows/
│   └── supply-chain.yml     # CI/CD pipeline with signing & attestations
├── attestations/            # SLSA provenance, SBOM, vulnerability reports
├── scripts/
│   ├── download-and-verify-binary.sh
│   └── container/
│       └── entrypoint.sh    # Docker entrypoint
├── src/
│   ├── app/
│   │   ├── cli.py           # Interactive CLI (serve + challenge in one process)
│   │   ├── commit_reveal.py # SHA256 commitment scheme
│   │   ├── http_api.py      # HTTP server with mTLS
│   │   ├── move_signing.py  # Sigstore/SSH move signing
│   │   ├── protocol.py      # Game rules
│   │   ├── rps_client.py    # HTTP client for challenges
│   │   ├── scoreboard.py    # Score tracking per SPIFFE ID
│   │   └── spiffe_mtls.py   # SPIFFE mTLS SSL contexts
│   ├── docker/
│   │   └── Dockerfile
│   └── k8s/                 # Kubernetes manifests
└── tests/
    └── test_protocol.py
```

---

# Cleanup

```bash
sudo pkill -f spire-server
sudo pkill -f spire-agent
docker stop $(docker ps -q --filter ancestor=ghcr.io/npaulat99/rock-paper-scissors:latest) 2>/dev/null || true
sudo rm -rf /tmp/spire-server /tmp/spire-agent /tmp/bootstrap-bundle.crt
sudo rm -f /tmp/spire-server.log /tmp/spire-agent.log
```
