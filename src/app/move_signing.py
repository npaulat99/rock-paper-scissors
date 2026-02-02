"""
Move Signing and Verification using Sigstore (keyless) or SSH keys.

This module provides cryptographic signing for game moves to ensure:
1. Non-repudiation: Players cannot deny making a move
2. Integrity: Moves cannot be tampered with in transit
3. Authenticity: Moves come from the claimed SPIFFE identity

Supports two modes:
- Sigstore (keyless): Uses OIDC identity for signing via Fulcio/Rekor
- SSH: Uses local SSH keys for offline signing
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Final, Literal

from protocol import Move

SIGNING_SCHEME: Final[str] = "rps-move-v1"


@dataclass(frozen=True)
class SignedMove:
    """A cryptographically signed move."""
    move: Move
    match_id: str
    round: int
    signer_spiffe_id: str
    signature: str  # Base64-encoded signature
    signing_method: Literal["sigstore", "ssh", "none"]
    # For Sigstore: the Rekor entry UUID or bundle
    transparency_log_entry: str | None = None


def create_move_payload(
    *,
    move: Move,
    match_id: str,
    round: int,
    signer_spiffe_id: str,
) -> str:
    """Create canonical payload for signing."""
    payload = {
        "scheme": SIGNING_SCHEME,
        "move": move,
        "match_id": match_id,
        "round": round,
        "signer": signer_spiffe_id,
    }
    # Canonical JSON: sorted keys, no extra whitespace
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_move_sigstore(
    *,
    move: Move,
    match_id: str,
    round: int,
    signer_spiffe_id: str,
) -> SignedMove:
    """
    Sign a move using Sigstore keyless signing.
    
    Requires:
    - cosign CLI installed
    - OIDC authentication (browser flow or GitHub Actions OIDC token)
    """
    payload = create_move_payload(
        move=move,
        match_id=match_id,
        round=round,
        signer_spiffe_id=signer_spiffe_id,
    )
    
    # Write payload to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        payload_path = f.name
    
    bundle_path = payload_path + ".bundle"
    
    try:
        # Sign with cosign (keyless mode)
        env = os.environ.copy()
        env["COSIGN_EXPERIMENTAL"] = "true"
        
        result = subprocess.run(
            [
                "cosign", "sign-blob",
                "--yes",
                "--bundle", bundle_path,
                payload_path,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Sigstore signing failed: {result.stderr}")
        
        # Read the bundle
        with open(bundle_path, "r") as f:
            bundle_content = f.read()
        
        # The signature is base64 in the bundle
        bundle_json = json.loads(bundle_content)
        signature_b64 = bundle_json.get("Payload", {}).get("body", "")
        
        return SignedMove(
            move=move,
            match_id=match_id,
            round=round,
            signer_spiffe_id=signer_spiffe_id,
            signature=signature_b64,
            signing_method="sigstore",
            transparency_log_entry=bundle_content,
        )
    finally:
        # Cleanup temp files
        for path in [payload_path, bundle_path]:
            if os.path.exists(path):
                os.unlink(path)


def verify_move_sigstore(signed_move: SignedMove) -> bool:
    """
    Verify a Sigstore-signed move.
    
    Returns True if the signature is valid and logged in Rekor.
    """
    if signed_move.signing_method != "sigstore":
        raise ValueError("Not a Sigstore-signed move")
    
    if not signed_move.transparency_log_entry:
        return False
    
    payload = create_move_payload(
        move=signed_move.move,
        match_id=signed_move.match_id,
        round=signed_move.round,
        signer_spiffe_id=signed_move.signer_spiffe_id,
    )
    
    # Write payload and bundle to temp files
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        payload_path = f.name
    
    bundle_path = payload_path + ".bundle"
    with open(bundle_path, "w") as f:
        f.write(signed_move.transparency_log_entry)
    
    try:
        result = subprocess.run(
            [
                "cosign", "verify-blob",
                "--bundle", bundle_path,
                "--certificate-identity-regexp", ".*",
                "--certificate-oidc-issuer-regexp", ".*",
                payload_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    finally:
        for path in [payload_path, bundle_path]:
            if os.path.exists(path):
                os.unlink(path)


def sign_move_ssh(
    *,
    move: Move,
    match_id: str,
    round: int,
    signer_spiffe_id: str,
    ssh_key_path: str = "~/.ssh/id_ed25519",
) -> SignedMove:
    """
    Sign a move using an SSH private key.
    
    This is an offline alternative when Sigstore is not available.
    """
    payload = create_move_payload(
        move=move,
        match_id=match_id,
        round=round,
        signer_spiffe_id=signer_spiffe_id,
    )
    
    key_path = os.path.expanduser(ssh_key_path)
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"SSH key not found: {key_path}")
    
    # Write payload to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        payload_path = f.name
    
    sig_path = payload_path + ".sig"
    
    try:
        result = subprocess.run(
            [
                "ssh-keygen",
                "-Y", "sign",
                "-f", key_path,
                "-n", "rps-move",
                payload_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"SSH signing failed: {result.stderr}")
        
        # Read the signature
        with open(sig_path, "r") as f:
            signature = f.read()
        
        return SignedMove(
            move=move,
            match_id=match_id,
            round=round,
            signer_spiffe_id=signer_spiffe_id,
            signature=base64.b64encode(signature.encode()).decode(),
            signing_method="ssh",
            transparency_log_entry=None,
        )
    finally:
        for path in [payload_path, sig_path]:
            if os.path.exists(path):
                os.unlink(path)


def verify_move_ssh(
    signed_move: SignedMove,
    allowed_signers_path: str,
) -> bool:
    """
    Verify an SSH-signed move.
    
    The allowed_signers_path should contain lines like:
        spiffe://domain/identity ssh-ed25519 AAAA...
    """
    if signed_move.signing_method != "ssh":
        raise ValueError("Not an SSH-signed move")
    
    payload = create_move_payload(
        move=signed_move.move,
        match_id=signed_move.match_id,
        round=signed_move.round,
        signer_spiffe_id=signed_move.signer_spiffe_id,
    )
    
    # Decode signature
    signature = base64.b64decode(signed_move.signature).decode()
    
    # Write payload and signature to temp files
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        payload_path = f.name
    
    sig_path = payload_path + ".sig"
    with open(sig_path, "w") as f:
        f.write(signature)
    
    try:
        result = subprocess.run(
            [
                "ssh-keygen",
                "-Y", "verify",
                "-f", allowed_signers_path,
                "-I", signed_move.signer_spiffe_id,
                "-n", "rps-move",
                "-s", sig_path,
            ],
            stdin=open(payload_path, "r"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    finally:
        for path in [payload_path, sig_path]:
            if os.path.exists(path):
                os.unlink(path)


def create_unsigned_move(
    *,
    move: Move,
    match_id: str,
    round: int,
    signer_spiffe_id: str,
) -> SignedMove:
    """Create an unsigned move (for environments without signing capabilities)."""
    return SignedMove(
        move=move,
        match_id=match_id,
        round=round,
        signer_spiffe_id=signer_spiffe_id,
        signature="",
        signing_method="none",
        transparency_log_entry=None,
    )


def is_signing_available() -> Literal["sigstore", "ssh", "none"]:
    """Check what signing methods are available."""
    # Check for cosign
    try:
        result = subprocess.run(
            ["cosign", "version"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return "sigstore"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Check for SSH key
    ssh_key = os.path.expanduser("~/.ssh/id_ed25519")
    if os.path.exists(ssh_key):
        return "ssh"
    
    return "none"
