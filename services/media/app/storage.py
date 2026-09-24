"""Работа с S3-хранилищем."""

from typing import BinaryIO
from urllib.parse import quote

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import settings
from .policy import is_inline, safe_filename

_session = aioboto3.Session(
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name=settings.s3_region,
)
_config = Config(signature_version="s3v4", s3={"addressing_style": "path"})


def _client(endpoint: str):
    return _session.client("s3", endpoint_url=endpoint, config=_config)


async def ensure_bucket() -> None:
    """Создать корзину, если её нет. Список корзин не надёжен (зависит от прав ключа),
    поэтому просто пробуем создать и считаем «уже есть» успехом."""
    async with _client(settings.s3_endpoint) as s3:
        try:
            await s3.create_bucket(Bucket=settings.s3_bucket)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise


async def put(key: str, body: BinaryIO, mime: str) -> None:
    async with _client(settings.s3_endpoint) as s3:
        await s3.upload_fileobj(body, settings.s3_bucket, key, ExtraArgs={"ContentType": mime})


async def size_of(key: str) -> int:
    async with _client(settings.s3_endpoint) as s3:
        head = await s3.head_object(Bucket=settings.s3_bucket, Key=key)
        return int(head["ContentLength"])


async def delete(key: str) -> None:
    async with _client(settings.s3_endpoint) as s3:
        await s3.delete_object(Bucket=settings.s3_bucket, Key=key)


async def presigned_url(key: str, filename: str, mime: str) -> str:
    """Ссылка на скачивание, подписанная публичным адресом хранилища.
    Изображения и PDF открываются в браузере, остальное — только скачивается."""
    name = safe_filename(filename)
    disposition = "inline" if is_inline(name) else "attachment"
    async with _client(settings.s3_public_endpoint) as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.s3_bucket,
                "Key": key,
                "ResponseContentType": mime if disposition == "inline" else "application/octet-stream",
                "ResponseContentDisposition": f"{disposition}; filename*=UTF-8''{quote(name)}",
            },
            ExpiresIn=settings.url_ttl_seconds,
        )
