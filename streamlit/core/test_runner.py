"""SignFinder test runner v1.15.

Запускает pytest на unit/integration тестах из /app/sf_tests/.
Тесты живут в signfinder-core/tests/ и копируются в контейнер при билде.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Optional


# Путь к тестам в Streamlit-контейнере (скопированы из signfinder-core/tests/)
_TESTS_DIR = os.environ.get("SIGNFINDER_TESTS_PATH", "/app/sf_tests")


def run_quick_tests(timeout: int = 120) -> dict:
    """Запустить unit + integration тесты через pytest.

    Возвращает:
    {
      "status": "passed" | "failed" | "error",
      "passed": int,
      "failed": int,
      "errors": int,
      "duration_sec": float,
      "details": [{"module": str, "passed": int, "failed": int}],
      "output": str,
      "error_message": str | None,
    }
    """
    if not os.path.isdir(_TESTS_DIR):
        return {
            "status": "error",
            "passed": 0, "failed": 0, "errors": 1,
            "duration_sec": 0.0,
            "details": [],
            "output": "",
            "error_message": f"Директория тестов не найдена: {_TESTS_DIR}",
        }

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = tmp.name

    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                _TESTS_DIR,
                "-v", "--tb=short",
                "--json-report",
                f"--json-report-file={report_path}",
                "--ignore", os.path.join(_TESTS_DIR, "test_api_integration.py"),
                "-q",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
        output = result.stdout + result.stderr

        return _parse_report(report_path, output)

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "passed": 0, "failed": 0, "errors": 1,
            "duration_sec": float(timeout),
            "details": [],
            "output": "Таймаут выполнения тестов",
            "error_message": f"Тесты не завершились за {timeout} сек",
        }
    except Exception as e:
        return {
            "status": "error",
            "passed": 0, "failed": 0, "errors": 1,
            "duration_sec": 0.0,
            "details": [],
            "output": "",
            "error_message": str(e),
        }
    finally:
        try:
            os.unlink(report_path)
        except Exception:
            pass


def run_integration_tests(timeout: int = 60) -> dict:
    """Запустить только API integration тесты."""
    integration_file = os.path.join(_TESTS_DIR, "test_api_integration.py")
    if not os.path.isfile(integration_file):
        return {
            "status": "error",
            "passed": 0, "failed": 0, "errors": 1,
            "duration_sec": 0.0,
            "details": [],
            "output": "",
            "error_message": "test_api_integration.py не найден",
        }

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = tmp.name

    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                integration_file,
                "-v", "--tb=short",
                "--json-report",
                f"--json-report-file={report_path}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
        output = result.stdout + result.stderr
        return _parse_report(report_path, output)
    except Exception as e:
        return {
            "status": "error",
            "passed": 0, "failed": 0, "errors": 1,
            "duration_sec": 0.0,
            "details": [],
            "output": "",
            "error_message": str(e),
        }
    finally:
        try:
            os.unlink(report_path)
        except Exception:
            pass


def run_full_eval(api_base_url: str, api_key: str, corpus: dict, providers: list[str]) -> dict:
    """Прогнать corpus.json через API, сравнить с expected.

    Возвращает per-provider KPI таблицу.
    providers: ["anthropic", "deepseek"]
    """
    import httpx
    import time

    results: dict[str, dict] = {}

    for provider in providers:
        kpi = {
            "template_accuracy": 0.0,
            "traffic_light_accuracy": 0.0,
            "anchor_precision": 0.0,
            "json_validity_rate": 0.0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
            "total_docs": 0,
            "errors": 0,
            "per_doc": [],
        }

        documents = corpus.get("documents", [])
        if not documents:
            results[provider] = kpi
            continue

        headers = {"Authorization": f"Bearer {api_key}"}
        latencies: list[float] = []
        tl_correct = 0
        tpl_correct = 0
        sig_correct = 0
        json_valid = 0
        doc_errors = 0

        with httpx.Client(timeout=180.0) as c:
            # Переключаем активного провайдера (пустые ключи → API сохранит существующие,
            # сбросит синглтон SignFinder — следующий analyze пойдёт на нужный LLM)
            try:
                c.post(
                    f"{api_base_url}/v1/config/llm",
                    headers=headers,
                    json={"active_provider": provider, "providers": {}},
                )
            except Exception:
                pass

            for doc_entry in documents:
                fname = doc_entry.get("filename", "?")
                expected_tl = doc_entry.get("expected_traffic_light", "yellow")
                expected_sig = doc_entry.get("expected_signature_count")
                expected_tpl = doc_entry.get("expected_template_name") or ""
                expected_side = doc_entry.get("expected_our_side") or {}

                # 1. Скачиваем файл документа из корпуса
                try:
                    fr = c.get(f"{api_base_url}/v1/corpus/files/{fname}", headers=headers)
                except Exception as e:
                    doc_errors += 1
                    kpi["per_doc"].append({
                        "filename": fname, "expected_tl": expected_tl,
                        "actual_tl": None, "match": False,
                        "note": f"скачивание не удалось: {e}",
                    })
                    continue
                if fr.status_code != 200:
                    doc_errors += 1
                    kpi["per_doc"].append({
                        "filename": fname, "expected_tl": expected_tl,
                        "actual_tl": None, "match": False,
                        "note": "файл не сохранён в корпусе (пересохрани пакет)",
                    })
                    continue
                pdf_bytes = fr.content

                # 2. Прогон через /v1/analyze
                t0 = time.monotonic()
                try:
                    ar = c.post(
                        f"{api_base_url}/v1/analyze",
                        headers=headers,
                        files={"file": (fname, pdf_bytes, "application/pdf")},
                    )
                    latencies.append((time.monotonic() - t0) * 1000)
                except Exception as e:
                    doc_errors += 1
                    kpi["per_doc"].append({
                        "filename": fname, "expected_tl": expected_tl,
                        "actual_tl": None, "match": False,
                        "note": f"analyze error: {e}",
                    })
                    continue

                if ar.status_code != 200:
                    doc_errors += 1
                    kpi["per_doc"].append({
                        "filename": fname, "expected_tl": expected_tl,
                        "actual_tl": None, "match": False,
                        "note": f"analyze {ar.status_code}: {ar.text[:80]}",
                    })
                    continue

                data = ar.json()

                # 3. Сравнение с expected
                actual_tl = data.get("traffic_light")
                actual_sig = len(data.get("anchors") or [])
                actual_side = data.get("our_side") or {}
                actual_tpl = (data.get("matched_template") or {}).get("best_match_template_id") or ""

                if not data.get("error"):
                    json_valid += 1

                tl_ok = (actual_tl == expected_tl)
                if tl_ok:
                    tl_correct += 1
                if actual_tpl == expected_tpl:
                    tpl_correct += 1

                if expected_sig is not None:
                    sig_ok = (actual_sig == expected_sig)
                    if sig_ok:
                        sig_correct += 1
                    sig_note = f"подписи {actual_sig}/{expected_sig} {'✓' if sig_ok else '✗'}"
                else:
                    sig_ok = True
                    sig_correct += 1
                    sig_note = f"подписи {actual_sig}"

                side_note = _compare_our_side(expected_side, actual_side)
                match = tl_ok and sig_ok

                kpi["per_doc"].append({
                    "filename": fname,
                    "expected_tl": expected_tl,
                    "actual_tl": actual_tl,
                    "match": match,
                    "note": f"{sig_note}; {side_note}",
                })

        n = len(documents)
        kpi["total_docs"] = n
        kpi["errors"] = doc_errors
        kpi["traffic_light_accuracy"] = tl_correct / n if n else 0.0
        kpi["template_accuracy"] = tpl_correct / n if n else 0.0
        kpi["anchor_precision"] = sig_correct / n if n else 0.0
        kpi["json_validity_rate"] = json_valid / n if n else 0.0
        if latencies:
            sorted_lat = sorted(latencies)
            m = len(sorted_lat)
            kpi["latency_p50_ms"] = sorted_lat[m // 2]
            kpi["latency_p95_ms"] = sorted_lat[min(m - 1, int(m * 0.95))]

        results[provider] = kpi

    return results


def _compare_our_side(expected: dict, actual: dict) -> str:
    """Мягкое сравнение нашей стороны по токенам ФИО подписанта."""
    import re as _re
    if not expected:
        return "our_side: n/a"
    exp_signer = (expected.get("signer") or "").lower()
    act_signer = (actual.get("signer") or "").lower()
    exp_tokens = {t for t in _re.findall(r"[а-яёa-z]+", exp_signer) if len(t) >= 4}
    act_tokens = {t for t in _re.findall(r"[а-яёa-z]+", act_signer) if len(t) >= 4}
    if not exp_tokens:
        return "signer: n/a"
    overlap = exp_tokens & act_tokens
    return f"signer {'✓' if overlap else '✗'}"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_report(report_path: str, output: str) -> dict:
    """Разбирает JSON-отчёт pytest-json-report."""
    try:
        with open(report_path) as f:
            report = json.load(f)
    except Exception:
        # Если JSON-отчёт недоступен — парсим текстовый вывод
        return _parse_output_fallback(output)

    summary = report.get("summary", {})
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    errors = summary.get("error", 0)
    duration = report.get("duration", 0.0)

    # Детализация по модулям
    modules: dict[str, dict] = {}
    for test in report.get("tests", []):
        node = test.get("nodeid", "")
        module = node.split("::")[0].replace(_TESTS_DIR + "/", "").replace(".py", "")
        if module not in modules:
            modules[module] = {"module": module, "passed": 0, "failed": 0}
        if test.get("outcome") == "passed":
            modules[module]["passed"] += 1
        else:
            modules[module]["failed"] += 1

    status = "passed" if (failed + errors) == 0 else "failed"

    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "duration_sec": round(duration, 2),
        "details": list(modules.values()),
        "output": output[-8000:],   # последние 8КБ
        "error_message": None,
    }


def _parse_output_fallback(output: str) -> dict:
    """Минимальный парсинг вывода pytest без JSON-отчёта."""
    passed = failed = errors = 0
    for line in output.splitlines():
        if " passed" in line:
            try:
                passed = int(line.strip().split()[0])
            except Exception:
                pass
        if " failed" in line:
            try:
                failed = int(line.strip().split()[0])
            except Exception:
                pass
        if " error" in line:
            try:
                errors = int(line.strip().split()[0])
            except Exception:
                pass
    status = "passed" if (failed + errors) == 0 else "failed"
    return {
        "status": status,
        "passed": passed, "failed": failed, "errors": errors,
        "duration_sec": 0.0,
        "details": [],
        "output": output[-8000:],
        "error_message": None,
    }
