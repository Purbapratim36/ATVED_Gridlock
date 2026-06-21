"""
Evidence storage — async S3/MinIO operations for evidence frames.
"""

from __future__ import annotations

import io
from typing import Any

import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger(__name__)

UPLOAD_COUNT = Counter("atved_evidence_uploads_total", "Evidence uploads to S3")
UPLOAD_LATENCY = Histogram(
    "atved_evidence_upload_seconds", "Evidence upload latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


class EvidenceStorage:
    """
    Handles evidence frame storage in S3/MinIO with server-side encryption.

    Each violation's evidence is stored under:
        ``s3://{bucket}/evidence/{violation_id}/frame_{index}.jpg``
        ``s3://{bucket}/evidence/{violation_id}/metadata.json``
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        encryption_enabled: bool = True,
    ) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region
        self._encrypt = encryption_enabled

    def _get_extra_args(self) -> dict[str, str]:
        """S3 upload extra args for server-side encryption."""
        if self._encrypt:
            return {"ServerSideEncryption": "aws:kms"}
        return {}

    async def upload_evidence(
        self,
        evidence_id: str,
        frames: list[bytes],
        metadata_bytes: bytes,
    ) -> list[str]:
        """
        Upload evidence frames and metadata to S3.

        Returns list of S3 keys for the uploaded objects.
        """
        import aiobotocore.session

        session = aiobotocore.session.get_session()
        keys: list[str] = []
        extra = self._get_extra_args()

        async with session.create_client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        ) as client:
            # Upload frames
            for i, frame_bytes in enumerate(frames):
                key = f"evidence/{evidence_id}/frame_{i:04d}.jpg"
                await client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=frame_bytes,
                    ContentType="image/jpeg",
                    **extra,
                )
                keys.append(key)

            # Upload metadata
            meta_key = f"evidence/{evidence_id}/metadata.json"
            await client.put_object(
                Bucket=self._bucket,
                Key=meta_key,
                Body=metadata_bytes,
                ContentType="application/json",
                **extra,
            )
            keys.append(meta_key)

        UPLOAD_COUNT.inc(len(keys))
        logger.info(
            "storage.evidence_uploaded",
            evidence_id=evidence_id,
            frame_count=len(frames),
            keys=len(keys),
        )
        return keys

    async def download_evidence(
        self,
        evidence_id: str,
        frame_count: int,
    ) -> tuple[list[bytes], bytes]:
        """Download evidence frames and metadata from S3."""
        import aiobotocore.session

        session = aiobotocore.session.get_session()
        frames: list[bytes] = []

        async with session.create_client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        ) as client:
            for i in range(frame_count):
                key = f"evidence/{evidence_id}/frame_{i:04d}.jpg"
                resp = await client.get_object(Bucket=self._bucket, Key=key)
                data = await resp["Body"].read()
                frames.append(data)

            meta_key = f"evidence/{evidence_id}/metadata.json"
            resp = await client.get_object(Bucket=self._bucket, Key=meta_key)
            metadata = await resp["Body"].read()

        return frames, metadata

    async def delete_evidence(self, evidence_id: str) -> None:
        """Delete all objects for an evidence record (retention enforcement)."""
        import aiobotocore.session

        session = aiobotocore.session.get_session()

        async with session.create_client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        ) as client:
            # List all objects with the evidence prefix
            prefix = f"evidence/{evidence_id}/"
            paginator = client.get_paginator("list_objects_v2")
            keys_to_delete: list[dict[str, str]] = []

            async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys_to_delete.append({"Key": obj["Key"]})

            if keys_to_delete:
                await client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": keys_to_delete},
                )

        logger.info(
            "storage.evidence_deleted",
            evidence_id=evidence_id,
            objects_deleted=len(keys_to_delete),
        )
