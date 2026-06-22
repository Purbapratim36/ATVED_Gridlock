"""
SHA-256 evidence hashing with deterministic serialisation.

Thin wrapper around the core evidence sealer, exposed for
direct use in evidence verification endpoints.
"""

from __future__ import annotations

import hashlib

import orjson
import structlog

logger = structlog.get_logger(__name__)


class EvidenceHasher:
    """Computes and verifies SHA-256 hashes for evidence integrity."""

    @staticmethod
    def compute_hash(data: dict, frame_bytes_list: list[bytes]) -> str:
        """
        Compute a SHA-256 hash over metadata and frame contents.

        Uses orjson with sorted keys for deterministic serialisation.
        """
        frame_hashes = [hashlib.sha256(fb).hexdigest() for fb in frame_bytes_list]

        payload = {
            "data": data,
            "frame_hashes": frame_hashes,
        }
        canonical = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def verify_hash(expected_hash: str, data: dict, frame_bytes_list: list[bytes]) -> bool:
        """Verify that stored hash matches recomputed hash."""
        computed = EvidenceHasher.compute_hash(data, frame_bytes_list)
        return computed == expected_hash

    @staticmethod
    def verify_chain(hashes: list[tuple[str, str | None]]) -> tuple[bool, int]:
        """
        Verify append-only chain integrity.

        Parameters
        ----------
        hashes:
            List of (sha256_hash, previous_hash) tuples in order.

        Returns
        -------
        (is_valid, break_index) — break_index is -1 if valid.
        """
        for i in range(1, len(hashes)):
            current_prev = hashes[i][1]
            expected_prev = hashes[i - 1][0]
            if current_prev != expected_prev:
                return False, i
        return True, -1
