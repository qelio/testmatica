"""Песочница для кода учеников. Доступна только сервису заданий по внутренней сети;
выполняет по одному запуску за раз (последовательность — ещё один барьер между решениями)."""

import asyncio
import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import sandbox

TOKEN = os.environ.get("INTERNAL_TOKEN", "dev-internal-token")
_lock = asyncio.Lock()

app = FastAPI(title="Тестматика · code-runner", version="0.1.0")


class Case(BaseModel):
    input: str = Field("", max_length=1_000_000)
    expected: str = Field("", max_length=1_000_000)


class RunRequest(BaseModel):
    language: str = "python"
    code: str = Field(max_length=100_000)
    tests: list[Case] = Field(min_length=1, max_length=100)
    time_limit_s: float = Field(2, gt=0, le=10)
    memory_limit_mb: int = Field(256, ge=32, le=512)
    stop_on_fail: bool = True


class CaseOut(BaseModel):
    number: int
    status: str
    time_ms: int
    output: str
    error: str


class RunResponse(BaseModel):
    passed: bool
    cases: list[CaseOut]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse)
async def run(body: RunRequest, x_internal_token: str | None = Header(None)) -> RunResponse:
    if not x_internal_token or not hmac.compare_digest(x_internal_token, TOKEN):
        raise HTTPException(403, "forbidden")
    if body.language != "python":
        raise HTTPException(422, "Поддерживается только Python")
    async with _lock:
        results = await asyncio.to_thread(
            sandbox.run,
            body.code,
            [c.model_dump() for c in body.tests],
            body.time_limit_s,
            body.memory_limit_mb,
            body.stop_on_fail,
        )
    cases = [
        CaseOut(number=i + 1, status=r.status, time_ms=r.time_ms, output=r.output, error=r.error)
        for i, r in enumerate(results)
    ]
    return RunResponse(passed=len(cases) == len(body.tests) and all(c.status == "passed" for c in cases), cases=cases)
