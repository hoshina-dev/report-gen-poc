"""
Cloudflare R2 storage — upload PDFs and generate presigned download URLs.

Key convention: pdfs/{exp_id}.pdf  (deterministic; put_object overwrites on retry)
Store only the key in the DB; generate a fresh presigned URL on demand.
"""

import boto3
from botocore.config import Config as BotocoreConfig

from .config import R2Config


def _client(cfg: R2Config):
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        region_name=cfg.region,
        config=BotocoreConfig(
            signature_version="s3v4",
            s3={
                "addressing_style": "path"
            },  # required for R2 — no virtual-hosted-style
        ),
    )


def upload_pdf(pdf_bytes: bytes, key: str, cfg: R2Config) -> None:
    """Upload PDF bytes to R2 at *key*. Raises on any error — no fallback."""
    _client(cfg).put_object(
        Bucket=cfg.bucket,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
