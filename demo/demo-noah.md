# Demo Guide — Noah

Personalized step-by-step guide for the live demo.

| Item | Value |
|------|-------|
| **Trust domain** | `noah.inter-cloud-thi.de` |
| **VM IP** | `4.185.66.130` |
| **SPIFFE ID** | `spiffe://noah.inter-cloud-thi.de/game-server-noah` |
| **Peer (Raghad)** | `raghad.inter-cloud-thi.de` / `4.185.211.9` |

## Demo Checklist

| Nr. | Step | Points | What to Show |
|-----|------|--------|--------------|
| 1 | Single Trust Domain | 7 | SPIRE running, game starts with mTLS, SPIFFE ID in banner |
| 2 | Visible SPIFFE IDs | 5 | SPIFFE URI in startup + peer identity on challenge |
| 3 | Score Tracking | 3 | Play a round, run `scores` command |
| 4 | Federated Reconfiguration | 7 | Import peer bundle, re-register entry, play cross-domain |

**Bonus:** ACME scoreboard (3 pts), move signing (4 pts), supply chain verification.

---

# Phase 1: Single Trust Domain (15 pts)

> **Goal:** Raghad runs the SPIRE server. You connect to **Raghad's** server
> and get an identity under `raghad.inter-cloud-thi.de`. You play a game
> over mTLS on the same trust domain.
>
> **You need from Raghad:**
> 1. A **join token** (one-time use string)
> 2. Her **bootstrap bundle** (certificate text)

## Step 1 — Install SPIRE

```bash
cd ~
wget https://github.com/spiffe/spire/releases/download/v1.13.3/spire-1.13.3-linux-amd64-musl.tar.gz
tar -xzf spire-1.13.3-linux-amd64-musl.tar.gz
cd spire-1.13.3
sudo mkdir -p /opt/spire/agent
sudo mkdir -p /tmp/spire-agent/data /tmp/spire-agent/public
```

> You do **not** need to set up a SPIRE server for Phase 1. Raghad's server
> handles everything.

## Step 2 — Save Raghad's Bootstrap Bundle

Paste the bootstrap bundle text that Raghad sent you:

```bash
cat > /tmp/raghad-bootstrap.crt <<'CERTEOF'
<PASTE RAGHAD'S BOOTSTRAP BUNDLE HERE>
CERTEOF
```

## Step 3 — Configure Agent (Points to Raghad's Server)

```bash
sudo mkdir -p /opt/spire/agent

sudo tee /opt/spire/agent/agent.conf > /dev/null <<'EOF'
agent {
  data_dir = "/tmp/spire-agent/data"
  log_level = "INFO"
  server_address = "4.185.211.9"
  server_port = "9000"
  socket_path = "/tmp/spire-agent/public/api.sock"
  trust_domain = "raghad.inter-cloud-thi.de"
  trust_bundle_path = "/tmp/raghad-bootstrap.crt"
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

> Note: `server_address` is **Raghad's IP** (`4.185.211.9`), not yours.
> `trust_domain` is **Raghad's** trust domain.

## Step 4 — Start Agent with Raghad's Token

**Before starting:** verify you can reach Raghad's SPIRE server:

```bash
nc -zv -w 5 4.185.211.9 9000
# Should say "Connection ... succeeded" or "open"
```

> **If timeout:** Admin has opened ports 9000-9005 in NSG. Raghad must also run:
>
> ```bash
> sudo ufw allow 9000/tcp  # SPIRE server
> sudo ufw allow 9002/tcp  # Game
> ```
>
> Wait 30-60 seconds, then retry `nc -zv -w 5 4.185.211.9 9000`.

Replace `<TOKEN_FROM_RAGHAD>` with the actual token Raghad sent you:

```bash
cd ~/spire-1.13.3

sudo pkill -f spire-agent || true
sleep 3
sudo rm -rf /tmp/spire-agent/data/ 2>/dev/null; sudo mkdir -p /tmp/spire-agent/data
sudo rm -f /tmp/spire-agent/public/api.sock

sudo nohup ./bin/spire-agent run \
  -config /opt/spire/agent/agent.conf \
  -joinToken <TOKEN_FROM_RAGHAD> > /tmp/spire-agent.log 2>&1 &
sleep 30

# Verify — look for "Creating X509-SVID"
sudo tail -20 /tmp/spire-agent.log
```

> **"i/o timeout" or "connection refused"?** Raghad must run:
> `sudo ufw allow 9000/tcp` (SPIRE server port).

## Step 5 — Fetch Certificates

```bash
cd ~/spire-1.13.3

mkdir -p ~/certs && rm -f ~/certs/*
SPIFFE_ENDPOINT_SOCKET=/tmp/spire-agent/public/api.sock \
  ./bin/spire-agent api fetch x509 -write ~/certs/

ls ~/certs/
# Expected: svid.0.pem  svid.0.key  bundle.0.pem

# Retry if empty
if [ ! -f ~/certs/bundle.0.pem ]; then
  echo "Certs not ready, waiting 30s..."
  sleep 30
  SPIFFE_ENDPOINT_SOCKET=/tmp/spire-agent/public/api.sock \
    ./bin/spire-agent api fetch x509 -write ~/certs/
  ls ~/certs/
fi

# Prepare cert files for the game
cp ~/certs/bundle.0.pem ~/certs/svid_bundle.pem
mv ~/certs/svid.0.pem ~/certs/svid.pem
mv ~/certs/svid.0.key ~/certs/svid_key.pem

# Should show 1 CA (Raghad's)
grep -c "BEGIN CERTIFICATE" ~/certs/svid_bundle.pem
```

> **"no identity issued"?** Ask Raghad to check that your workload entry exists
> on her server: `sudo ./bin/spire-server entry show`. Your UID must match
> the selector in the entry. Run `id -u` and tell Raghad.

## Step 6 — Start the Game

Your identity is `spiffe://raghad.inter-cloud-thi.de/game-server-noah` — same
trust domain as Raghad.

```bash
./rps-game \
  --bind 0.0.0.0:9002 \
  --spiffe-id spiffe://raghad.inter-cloud-thi.de/game-server-noah \
  --public-url https://4.185.66.130:9002 \
  --mtls --cert-dir ~/certs \
  --sign-moves
```

You should see:

```text
============================================================
  Rock-Paper-Scissors — Interactive Mode
  SPIFFE ID : spiffe://raghad.inter-cloud-thi.de/game-server-noah
  Listening : https://0.0.0.0:9002
  Scoreboard: https://0.0.0.0:9002/v1/rps/scores
  Signing   : ssh
============================================================

rps>
```

## Step 7 — Challenge Raghad (Same Trust Domain)

Both on `raghad.inter-cloud-thi.de` — no federation needed:

```text
rps> challenge https://4.185.211.9:9002 spiffe://raghad.inter-cloud-thi.de/game-server-raghad
Round 1 — choose (r)ock, (p)aper, (s)cissors: r
```

```text
rps> scores
```

**Show the grader:**
- ✅ **Single trust domain** — SPIRE running, mTLS game (7 pts)
- ✅ **Visible SPIFFE IDs** — banner + peer identity on challenge (5 pts)
- ✅ **Score tracking** — `scores` command (3 pts)

---

# Phase 2: Federated Reconfiguration (7 pts)

> **Goal:** You now set up your **own** SPIRE server with trust domain
> `noah.inter-cloud-thi.de`. You and Raghad exchange bundles, re-register
> workloads with `-federatesWith`, and play cross-domain.
>
> **Raghad waits** while you set up your server. Tell her when you're ready.

**Stop the game** (`quit` in the rps prompt) and stop the Phase 1 agent:

```bash
sudo pkill -f spire-agent
```

## Step 1 — Set Up Your Own SPIRE Server

### Configure server:

```bash
sudo mkdir -p /opt/spire/server
sudo mkdir -p /tmp/spire-server/data

sudo tee /opt/spire/server/server.conf > /dev/null <<'EOF'
server {
  bind_address = "0.0.0.0"
  bind_port = "9000"
  trust_domain = "noah.inter-cloud-thi.de"
  data_dir = "/tmp/spire-server/data"
  log_level = "INFO"

  federation {
    bundle_endpoint {
      address = "0.0.0.0"
      port = 9001
    }
  }
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

### Start server:

```bash
cd ~/spire-1.13.3

sudo pkill -f spire-server || true
sleep 2
sudo rm -f /tmp/spire-server/private/api.sock
sudo mkdir -p /tmp/spire-server/data

sudo nohup ./bin/spire-server run -config /opt/spire/server/server.conf > /tmp/spire-server.log 2>&1 &
sleep 5

sudo ./bin/spire-server healthcheck
sudo ./bin/spire-server bundle show > /tmp/bootstrap-bundle.crt
```

### Configure agent (now points to YOUR server):

```bash
sudo tee /opt/spire/agent/agent.conf > /dev/null <<'EOF'
agent {
  data_dir = "/tmp/spire-agent/data"
  log_level = "INFO"
  server_address = "127.0.0.1"
  server_port = "9000"
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

### Start agent:

```bash
cd ~/spire-1.13.3

sudo rm -rf /tmp/spire-agent/data/*
sudo rm -f /tmp/spire-agent/public/api.sock

TOKEN=$(sudo ./bin/spire-server token generate \
  -spiffeID spiffe://noah.inter-cloud-thi.de/agent/myagent \
  | grep Token | awk '{print $2}')

sudo nohup ./bin/spire-agent run \
  -config /opt/spire/agent/agent.conf \
  -joinToken $TOKEN > /tmp/spire-agent.log 2>&1 &
sleep 5
```

### Register your workload (no federation yet):

```bash
cd ~/spire-1.13.3

sudo ./bin/spire-server entry create \
  -spiffeID spiffe://noah.inter-cloud-thi.de/game-server-noah \
  -parentID spiffe://noah.inter-cloud-thi.de/agent/myagent \
  -selector unix:uid:$(id -u)

sudo ./bin/spire-server entry show
```

> **NSG:** Admin has opened ports 9000-9005. Also run:
>
> ```bash
> sudo ufw allow 9000/tcp  # SPIRE server
> sudo ufw allow 9001/tcp  # Bundle endpoint
> sudo ufw allow 9002/tcp  # Game
> ```
>
> Tell Raghad: "My server is up, port 9001 is open — proceed with Phase 2."

## Step 2 — Exchange Bundles with Raghad

### Option A: Bundle Endpoint (recommended)

```bash
cd ~/spire-1.13.3

# Fetch Raghad's bundle from her server
curl -sk https://4.185.211.9:9001 > /tmp/peer.bundle

# Import it
sudo ./bin/spire-server bundle set \
  -format spiffe \
  -id spiffe://raghad.inter-cloud-thi.de \
  -path /tmp/peer.bundle

# Set up automatic refresh
sudo ./bin/spire-server federation create \
  -trustDomain raghad.inter-cloud-thi.de \
  -bundleEndpointURL https://4.185.211.9:9001 \
  -bundleEndpointProfile https_spiffe \
  -endpointSpiffeID spiffe://raghad.inter-cloud-thi.de/spire/server \
  -trustDomainBundlePath /tmp/peer.bundle \
  -trustDomainBundleFormat spiffe
```

> **NSG:** Both VMs need inbound TCP **9001** open (bundle endpoint).

### Option B: Manual Bundle Exchange

```bash
cd ~/spire-1.13.3

# Export your bundle — send this to Raghad
sudo ./bin/spire-server bundle show -format spiffe > /tmp/my.bundle
cat /tmp/my.bundle

# Import Raghad's bundle (she sends you hers)
cat <<'BUNDLE_EOF' | sudo ./bin/spire-server bundle set \
  -format spiffe -id spiffe://raghad.inter-cloud-thi.de
<PASTE RAGHAD'S BUNDLE HERE>
BUNDLE_EOF

sudo ./bin/spire-server bundle list
# Should show BOTH trust domains
```

## Step 3 — Re-register Workload WITH Federation

```bash
cd ~/spire-1.13.3

# Delete old entry
sudo ./bin/spire-server entry show
sudo ./bin/spire-server entry delete -entryID <OLD_ENTRY_ID>

# Re-create WITH federation
sudo ./bin/spire-server entry create \
  -spiffeID spiffe://noah.inter-cloud-thi.de/game-server-noah \
  -parentID spiffe://noah.inter-cloud-thi.de/agent/myagent \
  -selector unix:uid:$(id -u) \
  -federatesWith spiffe://raghad.inter-cloud-thi.de
```

## Step 4 — Re-fetch Certificates

```bash
cd ~/spire-1.13.3

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

sudo tail -20 /tmp/spire-agent.log

mkdir -p ~/certs && rm -f ~/certs/*
SPIFFE_ENDPOINT_SOCKET=/tmp/spire-agent/public/api.sock \
  ~/spire-1.13.3/bin/spire-agent api fetch x509 -write ~/certs/

ls ~/certs/
# Expected: svid.0.pem  svid.0.key  bundle.0.pem  federated_bundle.0.0.pem

# Combine ALL CAs into one bundle
cat ~/certs/bundle.0.pem ~/certs/federated_bundle.*.pem > ~/certs/svid_bundle.pem
mv ~/certs/svid.0.pem ~/certs/svid.pem
mv ~/certs/svid.0.key ~/certs/svid_key.pem

# Must show 2+ CAs
grep -c "BEGIN CERTIFICATE" ~/certs/svid_bundle.pem
```

## Step 5 — Restart Game & Play Cross-Domain

```bash
./rps-game \
  --bind 0.0.0.0:9002 \
  --spiffe-id spiffe://noah.inter-cloud-thi.de/game-server-noah \
  --public-url https://4.185.66.130:9002 \
  --mtls --cert-dir ~/certs \
  --sign-moves
```

Challenge Raghad (now on **her own** trust domain):

```text
rps> challenge https://4.185.211.9:9002 spiffe://raghad.inter-cloud-thi.de/game-server-raghad
Round 1 — choose (r)ock, (p)aper, (s)cissors: r
```

```text
rps> scores
```

**Show the grader:**
- ✅ **Federated reconfiguration** — bundle imported, entry updated, certs re-fetched (7 pts)
- ✅ **Cross-domain authentication** — peer SPIFFE ID from different trust domain (5 pts)
- ✅ **Move signing** — signed move in game output (4 pts bonus)

---

# Bonus: Move Signing (4 pts)

Already enabled via `--sign-moves`. The game auto-detects:

| Priority | Method | Tool | How |
|----------|--------|------|-----|
| 1 | **Sigstore keyless** | `cosign` | OIDC → Fulcio cert → Rekor log |
| 2 | **SSH key** | `ssh-keygen` | Signs with `~/.ssh/id_ed25519` |
| 3 | Unsigned | — | Fallback |

> On headless VMs, Sigstore OIDC may fail. The game automatically falls back
> to SSH signing if `~/.ssh/id_ed25519` exists. Generate one if needed:
> `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""`

---

# Bonus: ACME Scoreboard (3 pts)

A second HTTPS endpoint using Let's Encrypt serves the scoreboard publicly.

- **Port 9002**: SPIFFE mTLS (client certs required)
- **Port 443**: WebPKI / ACME (public, no client auth)

## Get the Certificate

```bash
sudo apt install -y certbot

sudo certbot certonly --standalone \
  -d noah.inter-cloud-thi.de \
  --agree-tos --no-eff-email \
  -m noah.paul@thi.de

mkdir -p ~/acme-certs
sudo cp /etc/letsencrypt/live/noah.inter-cloud-thi.de/fullchain.pem ~/acme-certs/
sudo cp /etc/letsencrypt/live/noah.inter-cloud-thi.de/privkey.pem ~/acme-certs/
sudo chown $USER:$USER ~/acme-certs/*.pem
```

> **NSG:** Open inbound TCP **80** (certbot) and **443** (scoreboard).

## Run with ACME

```bash
sudo ./rps-game \
  --spiffe-id spiffe://noah.inter-cloud-thi.de/game-server-noah \
  --mtls --cert-dir ~/certs \
  --public-url https://4.185.66.130:9002 \
  --acme-cert ~/acme-certs/fullchain.pem \
  --acme-key ~/acme-certs/privkey.pem \
  --acme-bind 0.0.0.0:443 \
  --sign-moves
```

Public scoreboard: `https://noah.inter-cloud-thi.de/v1/rps/scores`

---

# Troubleshooting

## "No identity issued" when fetching certs

The agent hasn't synced the workload entry. Restart with a new token:

```bash
cd ~/spire-1.13.3
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
sudo tail -20 /tmp/spire-agent.log
```

Also verify: `sudo ./bin/spire-server entry show` — the selector must
be `unix:uid:$(id -u)` matching your user.

## "AlreadyExists" when creating entries

```bash
sudo ./bin/spire-server entry show   # Note the Entry ID
sudo ./bin/spire-server entry delete -entryID <THE_ID>
# Then re-create
```

## Timeout connecting to peer

1. `sudo ss -tlnp | grep 9002`
2. `nc -zv -w 5 4.185.211.9 9002`
3. Open port **9002** TCP in Azure NSG
4. `sudo ufw allow 9002/tcp`

## SSL/TLS — "TLSV1_ALERT_UNKNOWN_CA"

Peer's cert CA is not in your `svid_bundle.pem`. Usually means the SPIRE
server restarted (new CA key) and bundles are stale.

**Fix:** Re-exchange bundles (Phase 2 Step 2), re-fetch certs (Step 4),
restart game (Step 5).

## Expired SVID

SVIDs expire after ~1 hour. Re-fetch certs — no bundle exchange needed
unless the CA rotated.

---

# Cleanup

```bash
sudo pkill -f spire-server
sudo pkill -f spire-agent
docker stop $(docker ps -q --filter ancestor=ghcr.io/npaulat99/rock-paper-scissors:latest) 2>/dev/null || true
sudo rm -rf /tmp/spire-server /tmp/spire-agent /tmp/bootstrap-bundle.crt
sudo rm -f /tmp/spire-server.log /tmp/spire-agent.log
rm -f ~/.rps/scores.json
```

