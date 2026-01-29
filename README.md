# rock-paper-scissors

Federated Rock-Paper-Scissors game with SPIFFE mTLS authentication and supply chain security.

## 🎮 Quick Start

### Option 1: Download Pre-Built Signed Binary (Recommended)

```bash
# Clone the repository (requires authentication for private repos)
git clone https://github.com/npaulat99/rock-paper-scissors.git
cd rock-paper-scissors

# Download and verify the signed binary from GitHub Actions
bash scripts/download-and-verify-binary.sh
```

**Prerequisites:**
- GitHub CLI (`gh`) installed and authenticated: `gh auth login`
- Cosign installed: `curl -fsSL https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64 -o cosign && chmod +x cosign && sudo mv cosign /usr/local/bin/`

This script will:
1. Download the latest binary from GitHub Actions artifacts
2. Verify the Cosign signature (keyless signing)
3. Extract the binary to a temporary directory
4. Run a quick test

**Optional:** Copy binary to your PATH:
```bash
sudo cp /tmp/tmp.*/rps-game /usr/local/bin/
```

### Option 2: Docker Image

```bash
docker pull ghcr.io/npaulat99/rock-paper-scissors:latest
```

### Option 3: Build from Source

```bash
git clone https://github.com/npaulat99/rock-paper-scissors.git
cd rock-paper-scissors
pip install -r requirements.txt
python src/app/cli.py --help
```

---

## 📦 Supply Chain Security

This project demonstrates complete supply chain security:

✅ **Phase 1 - Scanning:** Trivy scans (source, Docker, IaC, image)  
✅ **Phase 2 - Attestations:** SLSA provenance, SBOM, vulnerability attestations  
✅ **Phase 3 - Signing:** Cosign keyless signing (GitHub OIDC)  
✅ **Phase 4 - CI/CD:** Automated GitHub Actions pipeline  

**Bonus Features:**
- ✅ Game binary built in CI/CD (PyInstaller)
- ✅ Binary downloadable from pipeline (GitHub Actions artifacts)
- ✅ Signature verification before execution (Cosign blob signing)

### Manual Download & Verify

If you prefer manual steps:

```bash
# 1. Download artifact from GitHub Actions
gh run download <RUN_ID> --repo npaulat99/rock-paper-scissors --name rps-game-binary

# 2. Verify signature
cosign verify-blob \
  --bundle rps-game.cosign.bundle \
  --certificate-identity-regexp="https://github.com/.+" \
  --certificate-oidc-issuer-regexp="https://token.actions.githubusercontent.com" \
  rps-game

# 3. Run
chmod +x rps-game
./rps-game --help
```

---

## Prerequisites

- Ubuntu VM with sudo access
- Docker installed
- Internet connectivity
- Another team's VM for federation (or simulate locally)

---

## Part 1: SPIRE Infrastructure Setup

### 1.1 Install SPIRE Server and Agent

```bash
# Download SPIRE 1.13.3
cd ~
wget https://github.com/spiffe/spire/releases/download/v1.13.3/spire-1.13.3-linux-amd64-musl.tar.gz
tar -xzf spire-1.13.3-linux-amd64-musl.tar.gz
cd spire-1.13.3

# Create config directories
sudo mkdir -p /opt/spire/server /opt/spire/agent
sudo mkdir -p /tmp/spire-server /tmp/spire-agent
```

### 1.2 Configure SPIRE Server

```bash
# Create server config
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

# Replace YOUR-TRUST-DOMAIN with your actual domain (e.g., alice.inter-cloud-thi.de)
```

### 1.3 Configure SPIRE Agent

```bash
# Get server trust bundle first
cd ~/spire-1.13.3
sudo ./bin/spire-server bundle show > /tmp/bootstrap-bundle.crt

# Create agent config
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

### 1.4 Start SPIRE Server

```bash
# Start server
cd ~/spire-1.13.3
sudo ./bin/spire-server run -config /opt/spire/server/server.conf &

# Wait for server to start
sleep 3

# Verify server is running
sudo ./bin/spire-server healthcheck
```

### 1.5 Generate Join Token and Start Agent

```bash
# Generate join token for agent
TOKEN=$(sudo ./bin/spire-server token generate -spiffeID spiffe://noah.inter-cloud-thi.de/agent/myagent | grep Token | awk '{print $2}')

# Start agent with join token
sudo ./bin/spire-agent run -config /opt/spire/agent/agent.conf -joinToken $TOKEN &

# Wait for agent to start
sleep 3

# Verify socket exists
ls -la /tmp/spire-agent/public/api.sock
```

---

## Part 2: Game Workload Registration

### 2.1 Register Game Workload

Choose your workload SPIFFE ID (e.g., `/game-server-alice`):

```bash
cd ~/spire-1.13.3

# Register game workload (Unix UID selector)
sudo ./bin/spire-server entry create \
  -spiffeID spiffe://noah.inter-cloud-thi.de/game-server-alice \
  -parentID spiffe://noah.inter-cloud-thi.de/agent/myagent \
  -selector unix:uid:$(id -u)

# Verify registration
sudo ./bin/spire-server entry show
```

**Important:** The selector `unix:uid:$(id -u)` means any process running as your user can obtain this SVID.

### 2.2 Generate Certificates with SPIRE Agent API

The game application will fetch certificates directly from the SPIRE agent using the go-spiffe library. No additional tools needed!

**For testing that the workload can get certificates:**

```bash
# Create cert directory (the game will use this)
mkdir -p ~/certs

# Test fetching SVID using SPIRE agent (run as your user, NOT sudo)
SPIFFE_ENDPOINT_SOCKET=/tmp/spire-agent/public/api.sock \
  ~/spire-1.13.3/bin/spire-agent api fetch x509 \
  -write ~/certs/

# Verify certs exist
ls -lh ~/certs/
```

You should see `svid.0.pem`, `svid.0.key`, and `bundle.0.pem`.

**Note:** The rock-paper-scissors Docker container will fetch certificates automatically when it runs - these manual steps are just for verification.

---

## Part 3: Federation Setup (Cross-Domain Play)

**This section is for federating with another team's trust domain.**

### 3.1 Export Your Trust Bundle

```bash
cd ~/spire-1.13.3

# Export your trust bundle
sudo ./bin/spire-server bundle show -format spiffe > ~/my-trust-bundle.json

# Share this file with your peer (e.g., via email, USB, or secure file transfer)
cat ~/my-trust-bundle.json
```

### 3.2 Import Peer's Trust Bundle

**After receiving peer's trust bundle (e.g., `peer-trust-bundle.json`):**

```bash
cd ~/spire-1.13.3

# Set the peer trust bundle
sudo ./bin/spire-server bundle set \
  -format spiffe \
  -id spiffe://PEER-TRUST-DOMAIN.example.com \
  < ~/peer-trust-bundle.json

# Verify federation
sudo ./bin/spire-server bundle list
```

You should see both your trust domain and the peer's trust domain listed.

---

## Part 4: Pull and Run the Game

### 4.1 Pull Docker Image

```bash
# Pull the image from GHCR
docker pull ghcr.io/npaulat99/rock-paper-scissors:latest

# Or build locally if you have the repo
cd ~/rock-paper-scissors
docker build -f src/docker/Dockerfile -t rock-paper-scissors:latest .
```

### 4.2 Run in Serve Mode (Wait for Challenges)

```bash
# Run server in interactive mode
docker run -it --rm \
  --network host \
  -v ~/certs:/app/certs:ro \
  ghcr.io/npaulat99/rock-paper-scissors:latest \
  serve \
  --bind 0.0.0.0:9002 \
  --spiffe-id spiffe://noah.inter-cloud-thi.de/game-server-alice \
  --mtls \
  --cert-dir /app/certs
```

**What happens:**
- Server listens on port 9002
- When a peer sends a challenge, you'll see a prompt to choose your move
- Enter `r` (rock), `p` (paper), or `s` (scissors)

### 4.3 Challenge a Peer (Initiate Game)

**In another terminal or VM:**

```bash
# Challenge another player
docker run -it --rm \
  --network host \
  -v ~/certs:/app/certs:ro \
  ghcr.io/npaulat99/rock-paper-scissors:latest \
  play \
  --bind 0.0.0.0:9003 \
  --spiffe-id spiffe://noah.inter-cloud-thi.de/game-server-alice \
  --peer https://PEER-IP:9002 \
  --peer-id spiffe://PEER-TRUST-DOMAIN.example.com/game-server-bob \
  --public-url https://YOUR-PUBLIC-IP:9003 \
  --mtls \
  --cert-dir /app/certs
```

**What happens:**
- You'll be prompted to choose your move for round 1
- After you choose, the challenger sends the commitment to the peer
- Peer chooses their move and sends it back
- You reveal your move, and the outcome is shown
- If it's a tie, you're prompted again for the next round
- When someone wins, scores are updated

### 4.4 View Scores

```bash
# View your local scoreboard
docker run -it --rm \
  -v ~/.rps:/root/.rps \
  ghcr.io/npaulat99/rock-paper-scissors:latest \
  scores
```

---

## Part 5: Testing Locally (Single VM, Two Identities)

If you want to test without a second VM:

### 5.1 Register Second Workload

```bash
cd ~/spire-1.13.3

# Register second identity
sudo ./bin/spire-server entry create \
  -spiffeID spiffe://noah.inter-cloud-thi.de/game-server-bob \
  -parentID spiffe://noah.inter-cloud-thi.de/agent/myagent \
  -selector unix:uid:$(id -u)
```

### 5.2 Generate Certs for Second Identity

```bash
# Create second cert directory
mkdir -p ~/certs-bob

# Create second spiffe-helper config
cat > ~/spiffe-helper-bob.conf <<EOF
agent_address = "/tmp/spire-agent/public/api.sock"
cmd = ""
cmd_args = ""
cert_dir = "$HOME/certs-bob"
renew_signal = ""
svid_file_name = "svid.pem"
svid_key_file_name = "svid_key.pem"
svid_bundle_file_name = "svid_bundle.pem"
EOF

# Fetch certs (requires bob's SPIFFE ID to be registered)
# This won't work automatically - you'd need workload attestation to distinguish
# For testing, manually create a process that requests bob's identity
```

**Note:** For true local testing with two identities, you need separate processes with different selectors (e.g., different UIDs or container IDs). Simpler approach: use two VMs.
