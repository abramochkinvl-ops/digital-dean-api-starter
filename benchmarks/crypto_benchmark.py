"""Відтворюваний експеримент із шістьма криптографічними комбінаціями."""

import argparse
import csv
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import platform
from random import Random
from secrets import token_bytes
from statistics import median, quantiles
from subprocess import check_output
from time import get_clock_info, perf_counter_ns
from uuid import uuid4

import Crypto
import cryptography
from cryptography.hazmat.backends.openssl.backend import backend as openssl_backend

from app.schemas.benchmark_report import BenchmarkReport
from app.security.adapters import open_bytes, seal_bytes
from app.security.nonce import NonceSequence
from app.security.profiles import BACKENDS, KEY_BYTES


SIZES_BYTES = (1024, 65536, 1048576)
WARMUP = 10
SERIES = 5
OPERATIONS_PER_SERIES = 100
SHUFFLE_SEED = 2026
BENCHMARK_AAD = b"digital-dean-practice-02-benchmark".ljust(64, b".")
RAW_COLUMNS = (
    "run_id", "backend", "algorithm", "size_bytes", "operation",
    "series_index", "operations", "total_ns", "mean_ns",
)


def measure_batch(operation, arguments) -> tuple[int, float]:
    if not arguments:
        raise ValueError("Empty batch")
    start = perf_counter_ns()
    for item in arguments:
        operation(*item)
    total_ns = perf_counter_ns() - start
    if total_ns <= 0:
        raise ValueError("Invalid elapsed time")
    return total_ns, total_ns / len(arguments)


def summarize(series_mean_ns, size_bytes) -> dict:
    if len(series_mean_ns) != SERIES:
        raise ValueError("Five series required")
    q1, _, q3 = quantiles(series_mean_ns, n=4, method="inclusive")
    typical = median(series_mean_ns)
    if typical <= 0:
        raise ValueError("Time must be positive")
    return {
        "median_ns": typical,
        "iqr_ns": q3 - q1,
        "throughput_mib_s": size_bytes * 1e9 / (2**20 * typical),
    }


def environment() -> dict:
    cpu = platform.processor() or platform.machine()
    aes_flag = None
    if platform.system() == "Windows":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            label, _, value = line.partition(":")
            if label.strip() == "model name":
                cpu = value.strip()
            if label.strip() in ("flags", "Features"):
                aes_flag = "aes" in value.split()
                break
    return {
        "cpu": cpu,
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "cryptography": cryptography.__version__,
        "pycryptodome": Crypto.__version__,
        "openssl": openssl_backend.openssl_version_text(),
        "aes_cpu_flag": aes_flag,
        "timer_resolution_ns": get_clock_info("perf_counter").resolution * 1e9,
    }


def run_benchmark(output_dir: Path) -> None:
    from benchmarks.plot_results import plot_results

    code_commit = check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    measured_at = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid4())
    configs = {
        (backend, algorithm): (token_bytes(key_bytes), NonceSequence())
        for backend, (algorithm, key_bytes) in product(BACKENDS, KEY_BYTES.items())
    }
    shuffle = Random(SHUFFLE_SEED)
    raw_rows, results = [], []

    for size in SIZES_BYTES:
        message = token_bytes(size)
        prepared = {}
        for pair, (key, nonces) in configs.items():
            nonce = nonces.next()
            ct, tag = seal_bytes(*pair, key, nonce, message, BENCHMARK_AAD)
            prepared[pair] = (*pair, key, nonce, ct, tag, BENCHMARK_AAD)
            if open_bytes(*prepared[pair]) != message:
                raise RuntimeError("Incorrect round trip before measurement")

        for label, operation in (("encrypt", seal_bytes), ("decrypt", open_bytes)):
            series_by_pair = {pair: [] for pair in configs}
            for series_index in range(SERIES + 1):
                order = list(configs)
                shuffle.shuffle(order)
                count = WARMUP if series_index == 0 else OPERATIONS_PER_SERIES
                for pair in order:
                    key, nonces = configs[pair]
                    if label == "encrypt":
                        arguments = [(*pair, key, nonces.next(), message, BENCHMARK_AAD) for _ in range(count)]
                    else:
                        arguments = [prepared[pair]] * count
                    total, mean = measure_batch(operation, arguments)
                    if series_index == 0:
                        continue
                    series_by_pair[pair].append(mean)
                    raw_rows.append(dict(zip(RAW_COLUMNS, (
                        run_id, *pair, size, label, series_index, count, total, mean
                    ))))

            for (backend, algorithm), means in series_by_pair.items():
                results.append({
                    "backend": backend,
                    "algorithm": algorithm,
                    "size_bytes": size,
                    "operation": label,
                    "series_mean_ns": means,
                    **summarize(means, size),
                })

    report = BenchmarkReport.model_validate({
        "schema_version": 1,
        "run_id": run_id,
        "measured_at_utc": measured_at,
        "code_commit": code_commit,
        "environment": environment(),
        "parameters": {
            "sizes_bytes": list(SIZES_BYTES),
            "warmup": WARMUP,
            "series": SERIES,
            "operations_per_series": OPERATIONS_PER_SERIES,
            "aad_bytes": len(BENCHMARK_AAD),
            "includes_cipher_setup": True,
            "shuffle_seed": SHUFFLE_SEED,
        },
        "results": results,
    })
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "raw.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RAW_COLUMNS)
        writer.writeheader()
        writer.writerows(raw_rows)
    plot_results(report, output_dir)
    temporary = output_dir / "report.json.tmp"
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_dir / "report.json")
    print(f"Серій: {len(raw_rows)}. Підсумкових рядків: {len(results)}. Каталог: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Вимірювання для практичної роботи 2")
    parser.add_argument("--output-dir", type=Path, required=True)
    run_benchmark(parser.parse_args().output_dir)


if __name__ == "__main__":
    main()
