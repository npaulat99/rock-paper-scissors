#!/usr/bin/env bash
set -euo pipefail

# Starts the interactive RPS CLI in SPIFFE mTLS mode.
# Use the 'challenge <peer_url> <peer_spiffe_id>' command at the rps> prompt.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

load_spire_env

REPO_DIR="${REPO_DIR:-$HOME/rock-paper-scissors}"
BIND="${BIND:-0.0.0.0:9002}"
CERT_DIR="${CERT_DIR:-$HOME/rps/certs}"
SPIFFE_ID="${SPIFFE_ID:-spiffe://$TRUST_DOMAIN/game-server-noah}"
PUBLIC_URL="${PUBLIC_URL:-}"
SCORES="${SCORES:-}"
ACME_CERT="${ACME_CERT:-}"
ACME_KEY="${ACME_KEY:-}"
ACME_BIND="${ACME_BIND:-}"

require_dir "$REPO_DIR"
require_dir "$CERT_DIR"

cd "$REPO_DIR"
PY="$(python_bin)"

CMD=("$PY" src/app/cli.py
  --bind "$BIND"
  --spiffe-id "$SPIFFE_ID"
  --mtls --cert-dir "$CERT_DIR"
)
[[ -n "$PUBLIC_URL" ]]  && CMD+=(--public-url "$PUBLIC_URL")
[[ -n "$SCORES" ]]      && CMD+=(--scores "$SCORES")
[[ -n "$ACME_CERT" ]]   && CMD+=(--acme-cert "$ACME_CERT")
[[ -n "$ACME_KEY" ]]    && CMD+=(--acme-key "$ACME_KEY")
[[ -n "$ACME_BIND" ]]   && CMD+=(--acme-bind "$ACME_BIND")

exec "${CMD[@]}"
