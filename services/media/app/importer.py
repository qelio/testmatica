"""Перенос картинки с другого сайта к нам (вставили текст вместе с картинкой из интернета).

Сервер сам ходит по чужому адресу, поэтому — защита от SSRF: только http/https, только публичные адреса
(никаких localhost, внутренней сети Docker и адреса метаданных облака), соединение — ровно с проверенным IP,
переадресации проверяются заново, размер и время ограничены, принимаются только картинки — по содержимому файла."""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from testmatica_common.errors import ApiError

MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(10.0)

# Сигнатуры картинок: доверяем содержимому, а не заголовку Content-Type.
SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": (".png", "image/png"),
    b"\xff\xd8\xff": (".jpg", "image/jpeg"),
    b"GIF87a": (".gif", "image/gif"),
    b"GIF89a": (".gif", "image/gif"),
}

UNAVAILABLE = ApiError(422, "image_unavailable", "Не удалось перенести картинку с другого сайта — сохраните её и вставьте файлом")


def sniff(data: bytes) -> tuple[str, str] | None:
    for sig, kind in SIGNATURES.items():
        if data.startswith(sig):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None


async def _public_ip(host: str, port: int) -> str:
    """IP-адрес хоста, если он публичный; иначе — отказ (внутренняя сеть, localhost, метаданные облака)."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise UNAVAILABLE from None
    addrs = {info[4][0] for info in infos}
    if not addrs or any(not ipaddress.ip_address(a).is_global for a in addrs):
        raise UNAVAILABLE
    return sorted(addrs)[0]


async def fetch_image(url: str) -> tuple[bytes, str, str]:
    """Скачать картинку: (содержимое, расширение, mime)."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                raise UNAVAILABLE
            port = parts.port or (443 if parts.scheme == "https" else 80)
            ip = await _public_ip(parts.hostname, port)
            # Соединяемся с уже проверенным IP: повторный DNS-запрос мог бы вернуть внутренний адрес.
            host_ip = f"[{ip}]" if ":" in ip else ip
            target = parts._replace(netloc=f"{host_ip}:{port}").geturl()
            request = client.build_request(
                "GET", target, headers={"Host": parts.netloc, "User-Agent": "TestMatica image import", "Accept": "image/*"},
                extensions={"sni_hostname": parts.hostname},
            )
            try:
                response = await client.send(request, stream=True)
            except httpx.HTTPError:
                raise UNAVAILABLE from None
            try:
                if response.is_redirect and "location" in response.headers:
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.status_code != 200:
                    raise UNAVAILABLE
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise ApiError(413, "file_too_large", "Картинка больше 10 МБ")
            finally:
                await response.aclose()
            kind = sniff(bytes(data))
            if kind is None:
                raise UNAVAILABLE
            return bytes(data), *kind
    raise UNAVAILABLE
