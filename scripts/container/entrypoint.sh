#!/usr/bin/env bash
set -euo pipefail

# Container entrypoint for the RPS game.
# Uses pre-generated SPIFFE certs mounted into the container.

RPS_MODE="${RPS_MODE:-serve}"
RPS_BIND="${RPS_BIND:-0.0.0.0:9002}"
RPS_SPIFFE_ID="${RPS_SPIFFE_ID:-}"
RPS_PEER_URL="${RPS_PEER_URL:-}"
RPS_PEER_ID="${RPS_PEER_ID:-}"
RPS_MOVE="${RPS_MOVE:-rock}"
RPS_PUBLIC_URL="${RPS_PUBLIC_URL:-}"
RPS_MTLS="${RPS_MTLS:-1}"
RPS_CERT_DIR="${RPS_CERT_DIR:-/app/certs}"

if [[ "$RPS_MTLS" == "1" || "$RPS_MTLS" == "true" ]]; then
  if [[ -z "$RPS_SPIFFE_ID" ]]; then
    echo "ERROR: RPS_SPIFFE_ID is required when RPS_MTLS=1" >&2
    exit 1
  fi
  if [[ ! -f "$RPS_CERT_DIR/svid.pem" || ! -f "$RPS_CERT_DIR/svid_key.pem" || ! -f "$RPS_CERT_DIR/svid_bundle.pem" ]]; then
    echo "ERROR: SPIFFE certs not found in $RPS_CERT_DIR" >&2
    echo "Generate them on the VM first (scripts/demo/02-fetch-certs.sh) and mount the certs directory." >&2
    exit 1
  fi
  RPS_MTLS_ARGS=("--mtls" "--cert-dir" "$RPS_CERT_DIR")
else
  RPS_MTLS_ARGS=()
fi

case "$RPS_MODE" in
  serve)
    exec python /app/cli.py serve \
      --bind "$RPS_BIND" \
      --spiffe-id "$RPS_SPIFFE_ID" \
      "${RPS_MTLS_ARGS[@]}"
    ;;
  play)
    if [[ -z "$RPS_PEER_URL" || -z "$RPS_PEER_ID" || -z "$RPS_PUBLIC_URL" ]]; then
      echo "ERROR: RPS_PEER_URL, RPS_PEER_ID, and RPS_PUBLIC_URL are required for play" >&2
      exit 1
    fi
    exec python /app/cli.py play \
      --bind "$RPS_BIND" \
      --public-url "$RPS_PUBLIC_URL" \
      --spiffe-id "$RPS_SPIFFE_ID" \
      --peer "$RPS_PEER_URL" \
      --peer-id "$RPS_PEER_ID" \
      --move "$RPS_MOVE" \
      "${RPS_MTLS_ARGS[@]}"
    ;;
  *)
    echo "ERROR: Unknown RPS_MODE: $RPS_MODE (expected serve|play)" >&2
    exit 1
    ;;
esac
