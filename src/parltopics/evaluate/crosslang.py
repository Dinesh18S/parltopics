"""Cross-language consistency (docs/06 §4): the same affair classified in each official language version."""

from itertools import combinations

from parltopics.evaluate.metrics import wilson


def cohen_kappa(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def _rate(k: int, n: int) -> dict:
    return {"agree": k, "n": n, "rate": k / n if n else None, "ci95": list(wilson(k, n))}


def crosslang_binary(labels: dict[int, dict[str, int]], langs: list[str]) -> dict:
    """labels: affair → {lang: 1 shown as match / 0 not}. Affairs missing a language are skipped and counted."""
    full = {a: v for a, v in labels.items() if all(lang in v for lang in langs)}
    out = {"n": len(full), "skipped_incomplete": len(labels) - len(full),
           "all_agree": _rate(sum(len({v[lang] for lang in langs}) == 1 for v in full.values()), len(full)),
           "pairs": {}}
    for x, y in combinations(langs, 2):
        a = [full[k][x] for k in sorted(full)]
        b = [full[k][y] for k in sorted(full)]
        out["pairs"][f"{x}-{y}"] = {"agreement": sum(p == q for p, q in zip(a, b)) / len(a) if a else None,
                                     "kappa": cohen_kappa(a, b)}
    out["positive_rate"] = {lang: sum(v[lang] for v in full.values()) / len(full) if full else None for lang in langs}
    return out


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def crosslang_sets(sets: dict[int, dict[str, list[str]]], langs: list[str]) -> dict:
    """sets: affair → {lang: labels in rank order}. Top-label agreement and Jaccard of label sets."""
    full = {a: v for a, v in sets.items() if all(lang in v for lang in langs)}
    top = {a: {lang: (v[lang][0] if v[lang] else None) for lang in langs} for a, v in full.items()}
    out = {"n": len(full), "skipped_incomplete": len(sets) - len(full),
           "top_all_agree": _rate(sum(len(set(t.values())) == 1 for t in top.values()), len(full)), "pairs": {}}
    for x, y in combinations(langs, 2):
        jac = [_jaccard(set(full[a][x]), set(full[a][y])) for a in full]
        out["pairs"][f"{x}-{y}"] = {"top_agreement": sum(top[a][x] == top[a][y] for a in full) / len(full) if full else None,
                                     "jaccard_mean": sum(jac) / len(jac) if jac else None}
    return out
