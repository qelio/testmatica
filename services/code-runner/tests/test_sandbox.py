"""Тесты песочницы. Запускаются внутри контейнера code-runner (там действуют все ограничения)."""

import os

from fastapi.testclient import TestClient

from app.main import app

H = {"X-Internal-Token": os.environ.get("INTERNAL_TOKEN", "dev-internal-token")}
client = TestClient(app)

SUM = "a, b = map(int, input().split())\nprint(a + b)\n"


def run(code, tests=None, **kw):
    tests = tests or [{"input": "2 3", "expected": "5"}, {"input": "10 -4", "expected": "6\n"}]
    resp = client.post("/run", json={"code": code, "tests": tests, **kw}, headers=H)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_correct_solution_passes_all_cases():
    result = run(SUM)
    assert result["passed"] is True
    assert [c["status"] for c in result["cases"]] == ["passed", "passed"]


def test_wrong_answer_stops_at_first_failed_case():
    result = run("a, b = map(int, input().split())\nprint(a - b)\n", tests=[
        {"input": "2 0", "expected": "2"}, {"input": "2 3", "expected": "5"}, {"input": "1 1", "expected": "2"},
    ])
    assert result["passed"] is False
    assert [(c["number"], c["status"]) for c in result["cases"]] == [(1, "passed"), (2, "wrong_answer")]


def test_runtime_error_and_trailing_whitespace():
    assert run("print(1/0)")["cases"][0]["status"] == "runtime_error"
    ok = run("print('5   ')\nprint()", tests=[{"input": "", "expected": "5"}])
    assert ok["passed"] is True


def test_infinite_loop_hits_time_limit():
    result = run("while True: pass", tests=[{"input": "", "expected": ""}], time_limit_s=1)
    assert result["cases"][0]["status"] == "time_limit"
    sleeper = run("import time; time.sleep(30)", tests=[{"input": "", "expected": ""}], time_limit_s=1)
    assert sleeper["cases"][0]["status"] == "time_limit"


def test_memory_limit():
    result = run("x = bytearray(400 * 1024 * 1024)", tests=[{"input": "", "expected": ""}], memory_limit_mb=64)
    assert result["cases"][0]["status"] in ("memory_limit", "runtime_error")


def test_no_network_and_no_secrets():
    code = (
        "import os, socket\n"
        "print(sorted(k for k in os.environ if 'TOKEN' in k))\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=2); print('net')\n"
        "except OSError:\n"
        "    print('no-net')\n"
    )
    assert run(code, tests=[{"input": "", "expected": "[]\nno-net"}])["passed"] is True


def test_fork_bomb_is_contained():
    code = "import os\nfor _ in range(200):\n    try:\n        os.fork()\n    except OSError:\n        break\nprint('ok')"
    result = run(code, tests=[{"input": "", "expected": "ok"}], time_limit_s=2)
    assert result["cases"][0]["status"] in ("passed", "wrong_answer", "runtime_error", "time_limit")
    # Сервис жив и работает дальше.
    assert run(SUM)["passed"] is True


def test_cannot_write_outside_workdir():
    code = "open('/srv/app/hacked.py', 'w').write('x')"
    assert run(code, tests=[{"input": "", "expected": ""}])["cases"][0]["status"] == "runtime_error"


def test_requires_internal_token():
    assert client.post("/run", json={"code": "print(1)", "tests": [{"input": "", "expected": "1"}]}).status_code == 403
