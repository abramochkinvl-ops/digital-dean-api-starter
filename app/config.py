"""Явна навчальна конфігурація закладу; зміни діють після перезапуску."""

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstitutionSettings:
    enrollment_year_min: int
    enrollment_year_max: int


def load_settings() -> InstitutionSettings:
    defaults = json.loads(Path(__file__).with_name("institution.json").read_text())
    lower = int(os.environ.get("ENROLLMENT_YEAR_MIN", defaults["enrollment_year_min"]))
    upper = int(os.environ.get("ENROLLMENT_YEAR_MAX", defaults["enrollment_year_max"]))
    if lower > upper:
        raise ValueError("Мінімальний рік вступу не може перевищувати максимальний.")
    return InstitutionSettings(lower, upper)


settings = load_settings()
