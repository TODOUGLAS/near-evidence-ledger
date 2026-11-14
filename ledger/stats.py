"""Small statistics helpers (no hidden state; every random draw uses a seeded Generator)."""
from __future__ import annotations

import numpy as np

SEED = 20261114


def rng(offset: int = 0) -> np.random.Generator:
    return np.random.default_rng(SEED + offset)


def block_bootstrap_idx(n: int, block: int, g: np.random.Generator) -> np.ndarray:
    """Moving-block bootstrap indices (keeps short-range autocorrelation)."""
    nblocks = int(np.ceil(n / block))
    starts = g.integers(0, max(n - block + 1, 1), size=nblocks)
    idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
    return np.minimum(idx, n - 1)


def boot_ci(x: np.ndarray, stat, block: int = 3, n_boot: int = 2000, q=(5, 95),
            seed: int = 0) -> tuple[float, float]:
    g = rng(seed)
    x = np.asarray(x, float)
    vals = [stat(x[block_bootstrap_idx(len(x), block, g)]) for _ in range(n_boot)]
    lo, hi = np.percentile(vals, q)
    return float(lo), float(hi)


def boot_ci_pair(x: np.ndarray, y: np.ndarray, stat, block: int = 4, n_boot: int = 2000,
                 q=(5, 95), seed: int = 0) -> tuple[float, float]:
    """Paired moving-block bootstrap (same indices for x and y)."""
    g = rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    vals = []
    for _ in range(n_boot):
        i = block_bootstrap_idx(len(x), block, g)
        vals.append(stat(x[i], y[i]))
    lo, hi = np.nanpercentile(vals, q)
    return float(lo), float(hi)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a coverage proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return float(c - h), float(c + h)
