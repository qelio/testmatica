"""Выполнение кода ученика с ограничениями.

Изоляция складывается из нескольких слоёв:
  * контейнер без доступа в интернет (внутренняя сеть Docker / NetworkPolicy в облаке),
    файловая система только для чтения, без Linux-привилегий, от пользователя nobody;
  * каждый запуск — отдельный процесс во временной папке с лимитами процессора, памяти,
    числа процессов, размера файлов и открытых дескрипторов;
  * чистое окружение: без переменных среды хост-процесса, python в изолированном режиме (-I).
"""

import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

OUTPUT_LIMIT = 64 * 1024  # сколько вывода сохраняем для сравнения и показа педагогу


@dataclass
class CaseResult:
    status: str  # passed | wrong_answer | runtime_error | time_limit | memory_limit
    time_ms: int
    output: str
    error: str


def _limits(time_limit_s: float, memory_mb: int):
    def apply() -> None:
        cpu = max(1, int(time_limit_s + 0.999))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        mem = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()

    return apply


def normalize(text: str) -> str:
    """Сравнение вывода без учёта пробелов в конце строк и пустых строк в конце."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip("\n").split("\n")).rstrip()


def run_case(code_path: str, workdir: str, stdin: str, expected: str, time_limit_s: float, memory_mb: int) -> CaseResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", code_path],
            input=stdin.encode(),
            capture_output=True,
            cwd=workdir,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"},
            timeout=time_limit_s * 2 + 1,  # «стенные» часы — страховка от sleep и ожидания ввода
            preexec_fn=_limits(time_limit_s, memory_mb),
        )
    except subprocess.TimeoutExpired:
        return CaseResult("time_limit", int((time.monotonic() - started) * 1000), "", "")
    elapsed = int((time.monotonic() - started) * 1000)
    out = proc.stdout[:OUTPUT_LIMIT].decode(errors="replace")
    err = proc.stderr[-OUTPUT_LIMIT:].decode(errors="replace")
    if proc.returncode != 0:
        if proc.returncode in (-9, -24) or elapsed > time_limit_s * 1000:  # SIGKILL / SIGXCPU
            return CaseResult("time_limit", elapsed, out, err)
        if "MemoryError" in err:
            return CaseResult("memory_limit", elapsed, out, err)
        return CaseResult("runtime_error", elapsed, out, err)
    if elapsed > time_limit_s * 1000:
        return CaseResult("time_limit", elapsed, out, err)
    status = "passed" if normalize(out) == normalize(expected) else "wrong_answer"
    return CaseResult(status, elapsed, out, err)


def run(code: str, tests: list[dict], time_limit_s: float, memory_mb: int, stop_on_fail: bool = True) -> list[CaseResult]:
    workdir = tempfile.mkdtemp(prefix="run-")
    try:
        path = os.path.join(workdir, "main.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        results = []
        for case in tests:
            r = run_case(path, workdir, case["input"], case["expected"], time_limit_s, memory_mb)
            results.append(r)
            if stop_on_fail and r.status != "passed":
                break
        return results
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
