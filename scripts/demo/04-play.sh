#!/usr/bin/env bash
set -euo pipefail

# Launches the interactive RPS game and issues a challenge.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_spire_env

REPO_DIR="${REPO_DIR:-$HOME/rock-paper-scissors}"
BIND="${BIND:-0.0.0.0:9002}"
CERT_DIR="${CERT_DIR:-$HOME/rps/certs}"
SPIFFE_ID="${SPIFFE_ID:-spiffe://$TRUST_DOMAIN/game-server-noah}"

PEER_URL="${1:-}"
PEER_SPIFFE_ID="${2:-}"

if [[ -z "$PEER_URL" || -z "$PEER_SPIFFE_ID" ]]; then
  echo "Usage: $0 <peer_url> <peer_spiffe_id>" >&2
  echo "Example: $0 https://1.2.3.4:9002 spiffe://raghad.inter-cloud-thi.de/game-server-raghad" >&2
  exit 1
fi

PUBLIC_URL="${PUBLIC_URL:-}"
if [[ -z "${PUBLIC_URL}" ]]; then
  echo "ERROR: PUBLIC_URL must be set (peer needs callback for /response)." >&2
  echo "Example: export PUBLIC_URL=https://<your-public-ip>:9002" >&2
  exit 1
fi

require_dir "$REPO_DIR"
require_dir "$CERT_DIR"

cd "$REPO_DIR"

echo "Starting interactive mode. Use 'challenge $PEER_URL $PEER_SPIFFE_ID' at the rps> prompt."

PY="$(python_bin)"
exec "$PY" src/app/cli.py \
  --bind "$BIND" \
  --public-url "$PUBLIC_URL" \
  --spiffe-id "$SPIFFE_ID" \
  --mtls --cert-dir "$CERT_DIR"
