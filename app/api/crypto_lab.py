"""Маршрут читає звіт із серверної конфігурації."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.schemas.benchmark_report import BenchmarkReport


router = APIRouter(prefix="/api/v1/lab/crypto", tags=["crypto-lab"])
DEFAULT_REPORT = Path(__file__).resolve().parents[2] / "results/practice-02/report.json"
REPORT_PATH = Path(os.environ.get("CRYPTO_BENCHMARK_REPORT", DEFAULT_REPORT))
UNAVAILABLE = "Benchmark results unavailable"


def load_benchmark_report(path: Path) -> BenchmarkReport:
    return BenchmarkReport.model_validate_json(path.read_bytes())


@router.get(
    "/benchmark-results", response_model=BenchmarkReport,
    responses={404: {"description": UNAVAILABLE}, 500: {"description": UNAVAILABLE}},
)
def get_benchmark_results() -> BenchmarkReport:
    """Повернути збережені результати повного базового експерименту."""
    try:
        return load_benchmark_report(REPORT_PATH)
    except FileNotFoundError:
        raise HTTPException(404, UNAVAILABLE) from None
    except (OSError, ValidationError):
        raise HTTPException(500, UNAVAILABLE) from None
