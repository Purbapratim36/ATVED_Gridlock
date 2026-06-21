"""
Evidence hash-sealing logic.

Each evidence record is sealed with a SHA-256 hash computed over
the canonical representation of its metadata and frame contents.
Records are chained via ``previous_hash`` to form an append-only
log, making post-hoc tampering detectable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import orjson
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SealedEvidence:
    """An immutable, hash-sealed evidence record."""

    sha256_hash: str
    previous_hash: str | None
    evidence_frames_json: list[dict[str, Any]]
    annotations_json: dict[str, Any]
    metadata_json: dict[str, Any]
    sealed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EvidenceSealer:
    """
    Computes cryptographic seals for evidence records and verifies
    chain integrity.

    The hash covers:
        1. Canonical JSON of metadata (sorted keys, deterministic).
        2. SHA-256 of each individual evidence frame.
        3. The previous record's hash (chain link).

    This makes each record's hash dependent on all prior records,
    so inserting, modifying, or deleting any record breaks the chain.
    """

    def __init__(self, hash_algorithm: str = "sha256") -> None:
        self._algo = hash_algorithm

    def seal(
        self,
        metadata: dict[str, Any],
        annotations: dict[str, Any],
        frames: list[bytes],
        frame_metadata: list[dict[str, Any]],
        previous_hash: str | None = None,
    ) -> SealedEvidence:
        """
        Create a sealed evidence record.

        Parameters
        ----------
        metadata:
            Violation metadata (camera_id, timestamp, model versions, etc.).
        annotations:
            Visual annotations (bounding boxes, labels, trajectories).
        frames:
            Raw bytes of each evidence frame (JPEG-encoded).
        frame_metadata:
            Per-frame metadata (index, timestamp, storage key).
        previous_hash:
            Hash of the preceding evidence record for chain linking.
        """
        # Compute per-frame hashes
        frame_hashes = [hashlib.sha256(f).hexdigest() for f in frames]

        frames_json = []
        for i, (fmeta, fhash) in enumerate(zip(frame_metadata, frame_hashes)):
            entry = {**fmeta, "frame_index": i, "sha256": fhash}
            frames_json.append(entry)

        # Build the canonical payload for hashing
        seal_payload = {
            "metadata": metadata,
            "annotations": annotations,
            "frame_hashes": frame_hashes,
            "previous_hash": previous_hash,
        }

        # Deterministic serialisation (sorted keys)
        canonical = orjson.dumps(
            seal_payload, option=orjson.OPT_SORT_KEYS | orjson.OPT_SERIALIZE_NUMPY
        )
        record_hash = hashlib.sha256(canonical).hexdigest()

        sealed = SealedEvidence(
            sha256_hash=record_hash,
            previous_hash=previous_hash,
            evidence_frames_json=frames_json,
            annotations_json=annotations,
            metadata_json=metadata,
        )

        logger.info(
            "evidence.sealed",
            hash=record_hash[:16] + "...",
            chain_link=previous_hash[:16] + "..." if previous_hash else "genesis",
            frame_count=len(frames),
        )

        return sealed

    def verify_hash(self, evidence: SealedEvidence, frames: list[bytes]) -> bool:
        """
        Verify that an evidence record's hash matches its content.

        Re-computes the hash from the stored metadata + frame bytes
        and compares against the stored hash.
        """
        frame_hashes = [hashlib.sha256(f).hexdigest() for f in frames]

        seal_payload = {
            "metadata": evidence.metadata_json,
            "annotations": evidence.annotations_json,
            "frame_hashes": frame_hashes,
            "previous_hash": evidence.previous_hash,
        }

        canonical = orjson.dumps(
            seal_payload, option=orjson.OPT_SORT_KEYS | orjson.OPT_SERIALIZE_NUMPY
        )
        computed = hashlib.sha256(canonical).hexdigest()
        return computed == evidence.sha256_hash

    def verify_chain(
        self, records: list[SealedEvidence]
    ) -> tuple[bool, int]:
        """
        Verify the chain integrity of a sequence of evidence records.

        Parameters
        ----------
        records:
            Evidence records in chronological order.

        Returns
        -------
        (is_valid, break_index):
            ``is_valid`` is True if the entire chain is intact.
            ``break_index`` is -1 if valid, otherwise the index of the
            first record where the chain breaks.
        """
        for i in range(1, len(records)):
            if records[i].previous_hash != records[i - 1].sha256_hash:
                logger.warning(
                    "evidence.chain_break",
                    index=i,
                    expected=records[i - 1].sha256_hash[:16],
                    found=records[i].previous_hash[:16] if records[i].previous_hash else "None",
                )
                return False, i

        return True, -1
