from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx

from app.config import settings
from app.policy import MB

from .conftest import INTERNAL, bearer, upload


def internal_s3(url: str) -> str:
    """Ссылка подписана публичным адресом; из контейнера ходим во внутренний, путь и подпись те же."""
    parsed = urlparse(url)
    return f"{settings.s3_endpoint}{parsed.path}?{parsed.query}"


async def test_upload_and_download(client):
    user = uuid4()
    resp = await upload(client, user, "Решение задачи.pdf", b"%PDF-1.4 hello")
    assert resp.status_code == 201, resp.text
    f = resp.json()
    # Тип определяется по расширению, а не по заголовку клиента.
    assert (f["filename"], f["mime"], f["size"], f["purpose"]) == ("Решение задачи.pdf", "application/pdf", 14, "answer")

    own = (await client.get(f"/files/{f['id']}", headers=bearer(user))).json()
    assert own["url"].startswith(settings.s3_public_endpoint)
    assert "inline" in unquote(own["url"])  # PDF открывается в браузере
    async with httpx.AsyncClient() as s3:
        body = await s3.get(internal_s3(own["url"]))
    assert body.content == b"%PDF-1.4 hello"

    # Чужой файл напрямую не отдаётся.
    assert (await client.get(f"/files/{f['id']}", headers=bearer(uuid4()))).status_code == 404


async def test_non_inline_types_are_downloaded(client):
    user = uuid4()
    f = (await upload(client, user, "работа.docx", b"PK..docx")).json()
    url = (await client.get(f"/files/{f['id']}", headers=bearer(user))).json()["url"]
    assert "attachment" in unquote(url)


async def test_policy(client):
    user = uuid4()
    bad_type = await upload(client, user, "virus.exe", b"MZ")
    assert bad_type.status_code == 422 and bad_type.json()["error"]["code"] == "file_type_not_allowed"
    too_big = await upload(client, user, "photo.png", b"x" * (5 * MB + 1), purpose="avatar")
    assert too_big.status_code == 413
    empty = await upload(client, user, "empty.txt", b"")
    assert empty.json()["error"]["code"] == "empty_file"
    unknown = await upload(client, user, "a.pdf", b"x", purpose="whatever")
    assert unknown.json()["error"]["code"] == "invalid_purpose"
    # Путь в имени файла отрезается.
    safe = await upload(client, user, "../../etc/passwd.txt", b"root")
    assert safe.json()["filename"] == "passwd.txt"


async def test_claim_checks_owner_and_purpose(client):
    owner, other = uuid4(), uuid4()
    f = (await upload(client, owner)).json()
    body = {"owner_id": str(owner), "purpose": "answer", "file_ids": [f["id"]], "claimed_by": "assessment"}

    assert (await client.post("/internal/files/claim", json=body)).status_code == 403  # без токена
    stolen = await client.post("/internal/files/claim", json={**body, "owner_id": str(other)}, headers=INTERNAL)
    assert stolen.status_code == 422
    wrong_purpose = await client.post("/internal/files/claim", json={**body, "purpose": "chat_attachment"}, headers=INTERNAL)
    assert wrong_purpose.status_code == 422

    ok = await client.post("/internal/files/claim", json=body, headers=INTERNAL)
    assert ok.status_code == 200 and ok.json()[0]["filename"] == "решение.pdf"
    # Повторно тем же сервисом — можно, другим — нет.
    assert (await client.post("/internal/files/claim", json=body, headers=INTERNAL)).status_code == 200
    other_service = await client.post("/internal/files/claim", json={**body, "claimed_by": "chat"}, headers=INTERNAL)
    assert other_service.status_code == 409

    # Прикреплённый файл удалить нельзя.
    assert (await client.delete(f"/files/{f['id']}", headers=bearer(owner))).status_code == 409


async def test_urls_and_delete_unclaimed(client):
    user = uuid4()
    a = (await upload(client, user, "a.png", b"\x89PNG")).json()
    b = (await upload(client, user, "b.txt", b"hello")).json()
    urls = (await client.post("/internal/files/urls", json={"file_ids": [a["id"], b["id"]]}, headers=INTERNAL)).json()
    assert set(urls) == {a["id"], b["id"]} and urls[a["id"]]["url"]

    assert (await client.delete(f"/files/{b['id']}", headers=bearer(user))).status_code == 204
    urls = (await client.post("/internal/files/urls", json={"file_ids": [a["id"], b["id"]]}, headers=INTERNAL)).json()
    assert set(urls) == {a["id"]}


async def test_content_files_by_permanent_link(client):
    """Картинки и файлы в тексте: постоянная ссылка без входа ведёт на свежую ссылку в хранилище."""
    user = uuid4()
    img = (await upload(client, user, "график.png", b"\x89PNG fake", purpose="content")).json()
    doc = (await upload(client, user, "условие.docx", b"PK..docx", purpose="content")).json()
    heic = await upload(client, user, "фото.heic", b"heic", purpose="content")
    assert heic.status_code == 422  # браузеры не показывают

    resp = await client.get(f"/files/{img['id']}/content", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["location"].startswith(settings.s3_public_endpoint)
    assert "inline" in unquote(resp.headers["location"])
    async with httpx.AsyncClient() as s3:
        assert (await s3.get(internal_s3(resp.headers["location"]))).content == b"\x89PNG fake"
    loc = (await client.get(f"/files/{doc['id']}/content", follow_redirects=False)).headers["location"]
    assert "attachment" in unquote(loc)  # документ — только скачивание

    # Файлы с другими назначениями (ответы, документы об образовании) так не отдаются.
    private = (await upload(client, user, "диплом.pdf", b"%PDF", purpose="document")).json()
    assert (await client.get(f"/files/{private['id']}/content", follow_redirects=False)).status_code == 404
    assert (await client.get(f"/files/{uuid4()}/content", follow_redirects=False)).status_code == 404
