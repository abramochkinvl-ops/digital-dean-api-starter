"""Схема перевіреного підсумку базового експерименту."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


Backend = Literal["cryptography", "pycryptodome"]
Algorithm = Literal["AES-128-GCM", "AES-256-GCM", "ChaCha20-Poly1305"]
Size = Literal[1024, 65536, 1048576]
Operation = Literal["encrypt", "decrypt"]
Positive = Annotated[FiniteFloat, Field(gt=0)]


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Environment(ReportModel):
    cpu: str
    os: str
    architecture: str
    python: str
    cryptography: str
    pycryptodome: str
    openssl: str
    aes_cpu_flag: bool | None
    timer_resolution_ns: Positive


class Parameters(ReportModel):
    sizes_bytes: list[int]
    warmup: Literal[10]
    series: Literal[5]
    operations_per_series: Literal[100]
    aad_bytes: Literal[64]
    includes_cipher_setup: Literal[True]
    shuffle_seed: int

    @model_validator(mode="after")
    def baseline_sizes(self):
        if self.sizes_bytes != [1024, 65536, 1048576]:
            raise ValueError("Invalid baseline sizes")
        return self


class Result(ReportModel):
    backend: Backend
    algorithm: Algorithm
    size_bytes: Size
    operation: Operation
    series_mean_ns: list[Positive] = Field(min_length=5, max_length=5)
    median_ns: Positive
    iqr_ns: Annotated[FiniteFloat, Field(ge=0)]
    throughput_mib_s: Positive


class BenchmarkReport(ReportModel):
    schema_version: Literal[1]
    run_id: str = Field(min_length=1)
    measured_at_utc: str = Field(min_length=1)
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    environment: Environment
    parameters: Parameters
    results: list[Result] = Field(min_length=36, max_length=36)

    @model_validator(mode="after")
    def all_combinations_once(self):
        ids = {(r.backend, r.algorithm, r.size_bytes, r.operation) for r in self.results}
        if len(ids) != 36:
            raise ValueError("Missing or duplicated benchmark combination")
        return self
