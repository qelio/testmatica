"""Перенос картинки с другого сайта к нам (вставили текст вместе с картинкой из интернета).

Сервер сам ходит по чужому адресу, поэтому — защита от SSRF: только http/https, только публичные адреса
(никаких localhost, внутренней сети Docker и адреса метаданных облака), соединение — ровно с проверенным IP,
переадресации проверяются заново, размер и время ограничены, принимаются только картинки — по содержимому файла."""

import asyncio
import ipaddress
import re
import socket
from email.message import Message
from urllib.parse import urljoin, urlsplit

import httpx
from testmatica_common.errors import ApiError

from .policy import MB, PURPOSES

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


async def _public_ip(host: str, port: int, unavailable: ApiError) -> str:
    """IP-адрес хоста, если он публичный; иначе — отказ (внутренняя сеть, localhost, метаданные облака)."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise unavailable from None
    addrs = {info[4][0] for info in infos}
    if not addrs or any(not ipaddress.ip_address(a).is_global for a in addrs):
        raise unavailable
    return sorted(addrs)[0]


EGE_FILE = re.compile(r"https://(?:[a-z0-9-]+-)?(?:ege|oge)\.sdamgia\.ru/get_file\?id=\d+")
EGE_UNAVAILABLE = ApiError(422, "ege_file_unavailable", "Не удалось перенести файл из «РЕШУ ОГЭ/ЕГЭ»")


async def _download(url: str, *, ege: bool = False) -> tuple[bytes, httpx.Headers]:
    unavailable = EGE_UNAVAILABLE if ege else UNAVAILABLE
    limit = PURPOSES["content"].max_size if ege else MAX_BYTES
    try:
        async with asyncio.timeout(25), httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                if ege and not EGE_FILE.fullmatch(url):
                    raise unavailable
                parts = urlsplit(url)
                if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                    raise unavailable
                port = parts.port or (443 if parts.scheme == "https" else 80)
                ip = await _public_ip(parts.hostname, port, unavailable)
                # Соединяемся с проверенным адресом, сохраняя исходное имя для проверки TLS.
                host_ip = f"[{ip}]" if ":" in ip else ip
                target = parts._replace(netloc=f"{host_ip}:{port}").geturl()
                request = client.build_request(
                    "GET", target,
                    headers={"Host": parts.netloc, "User-Agent": "Mozilla/5.0" if ege else "TestMatica image import",
                             "Accept": "*/*" if ege else "image/*"},
                    extensions={"sni_hostname": parts.hostname},
                )
                response = await client.send(request, stream=True)
                try:
                    if response.is_redirect and "location" in response.headers:
                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code != 200:
                        raise unavailable
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > limit:
                            label = "Файл" if ege else "Картинка"
                            raise ApiError(413, "file_too_large", f"{label} больше {limit // MB} МБ")
                        data.extend(chunk)
                    return bytes(data), response.headers
                finally:
                    await response.aclose()
    except (httpx.HTTPError, TimeoutError, ValueError):
        raise unavailable from None
    raise unavailable


async def fetch_image(url: str) -> tuple[bytes, str, str]:
    data, _ = await _download(url)
    kind = sniff(data)
    if kind is None:
        raise UNAVAILABLE
    return data, *kind


async def fetch_ege_file(url: str) -> tuple[bytes, str]:
    data, headers = await _download(url, ege=True)
    disposition = Message()
    disposition["Content-Disposition"] = headers.get("content-disposition", "")
    filename = disposition.get_filename()
    if not filename or disposition.get_content_disposition() != "attachment" or not data:
        raise EGE_UNAVAILABLE
    return data, filename
