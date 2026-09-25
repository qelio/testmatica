"""Записи занятий в S3: корзина сервиса video (туда же пишет egress)."""

from urllib.parse import quote

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import settings

_session = aioboto3.Session(
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name=settings.s3_region,
)
_config = Config(signature_version="s3v4", s3={"addressing_style": "path"})


def _client(endpoint: str):
    return _session.client("s3", endpoint_url=endpoint, config=_config)


async def ensure_bucket() -> None:
    async with _client(settings.s3_endpoint) as s3:
        try:
            await s3.create_bucket(Bucket=settings.s3_bucket)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise


async def delete(key: str) -> None:
    async with _client(settings.s3_endpoint) as s3:
        await s3.delete_object(Bucket=settings.s3_bucket, Key=key)


async def url(key: str, filename: str, download: bool) -> str:
    """Ссылка для просмотра в плеере или для скачивания (ТЗ: скачивание доступно участникам)."""
    disposition = f"{'attachment' if download else 'inline'}; filename*=UTF-8''{quote(filename)}"
    async with _client(settings.s3_public_endpoint) as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key, "ResponseContentType": "video/mp4",
                    "ResponseContentDisposition": disposition},
            ExpiresIn=settings.url_ttl_seconds,
        )
