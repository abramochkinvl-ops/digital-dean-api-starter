"""Графіки пропускної здатності з квартилями п’яти серій."""

from pathlib import Path
from statistics import quantiles

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.schemas.benchmark_report import BenchmarkReport
from app.security.profiles import BACKENDS, KEY_BYTES


def plot_results(report: BenchmarkReport, output_dir: Path) -> None:
    colors = ("#0C7080", "#845097", "#B25923")
    for operation, title in (
        ("encrypt", "Шифрування"),
        ("decrypt", "Розшифрування з перевіркою тега"),
    ):
        fig, ax = plt.subplots(figsize=(9, 5.4), layout="constrained")
        for index, algorithm in enumerate(KEY_BYTES):
            for backend_index, backend in enumerate(BACKENDS):
                rows = sorted(
                    (
                        r for r in report.results
                        if (r.operation, r.algorithm, r.backend) == (operation, algorithm, backend)
                    ),
                    key=lambda r: r.size_bytes,
                )
                x = [r.size_bytes / 1024 for r in rows]
                typical = [r.throughput_mib_s for r in rows]
                lower, upper = [], []
                for row in rows:
                    q1, _, q3 = quantiles(row.series_mean_ns, n=4, method="inclusive")
                    factor = row.size_bytes * 1e9 / 2**20
                    lower.append(factor / q3)
                    upper.append(factor / q1)
                ax.errorbar(
                    x, typical, yerr=[
                        [y - lo for y, lo in zip(typical, lower)],
                        [hi - y for y, hi in zip(typical, upper)],
                    ],
                    color=colors[index], linestyle=("-", "--")[backend_index],
                    marker=("o", "s")[backend_index], capsize=3, linewidth=1.6,
                    label=f"{algorithm} · {backend}",
                )
        ax.set_xscale("log", base=2)
        ax.set_xticks([1, 64, 1024], labels=["1", "64", "1024"])
        ax.set_yscale("log")
        ax.set_xlabel("Розмір повідомлення, КіБ")
        ax.set_ylabel("Пропускна здатність, МіБ/с")
        ax.set_title(title + "\nМедіана п’яти серій і межі Q1–Q3", loc="left", fontsize=14)
        ax.grid(color="#CBD5E1", linewidth=.65, alpha=.75)
        ax.legend(fontsize=8, ncol=2, loc="lower right", framealpha=.94)
        fig.savefig(output_dir / (operation + "-throughput.png"), dpi=180)
        plt.close(fig)
