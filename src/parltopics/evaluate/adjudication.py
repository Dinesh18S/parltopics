"""After-review metrics (docs/06 §2.4, D55/D56/D58): the reviewer's label replaces PolitMonitor's for reviewed affairs;
each confusion cell's reviewer-yes rate is scaled to the cell's size in the test split and to the population."""

import random

CELLS = ("TP", "FN", "FP", "TN")  # TP/FN: PolitMonitor-tagged; FP/TN: not tagged (model shown / not shown)


def _point(sizes: dict[str, int], rates: dict[str, float], prevalence: float) -> tuple[float | None, float | None]:
    pos = sizes["TP"] + sizes["FN"]
    neg = sizes["FP"] + sizes["TN"]
    m1_r1 = prevalence * sizes["TP"] * rates["TP"] / pos + (1 - prevalence) * sizes["FP"] * rates["FP"] / neg
    m1 = prevalence * sizes["TP"] / pos + (1 - prevalence) * sizes["FP"] / neg
    r1 = (prevalence * (sizes["TP"] * rates["TP"] + sizes["FN"] * rates["FN"]) / pos
          + (1 - prevalence) * (sizes["FP"] * rates["FP"] + sizes["TN"] * rates["TN"]) / neg)
    return (m1_r1 / m1 if m1 else None), (m1_r1 / r1 if r1 else None)


def after_review(sizes: dict[str, int], answers: dict[str, list[int]], prevalence: float, n_boot: int = 1000,
                 seed: int = 0) -> dict:
    """sizes: cell → affairs in the test split; answers: cell → reviewer labels (1 digital / 0 not) of reviewed,
    decided affairs. Population precision/recall with the reviewer as gold; stratified bootstrap over answers."""
    rates = {c: sum(answers[c]) / len(answers[c]) for c in CELLS}
    precision, recall = _point(sizes, rates, prevalence)
    rng = random.Random(seed)
    ps, rs = [], []
    for _ in range(n_boot):
        boot = {c: sum(rng.choices(answers[c], k=len(answers[c]))) / len(answers[c]) for c in CELLS}
        p, r = _point(sizes, boot, prevalence)
        if p is not None and r is not None:
            ps.append(p)
            rs.append(r)
    ci = lambda xs: [sorted(xs)[int(0.025 * (len(xs) - 1))], sorted(xs)[int(0.975 * (len(xs) - 1))]] if xs else None
    return {"precision": precision, "precision_ci95": ci(ps), "recall": recall, "recall_ci95": ci(rs),
            "reviewer_yes_rate": rates, "answered": {c: len(answers[c]) for c in CELLS}, "cell_sizes": sizes}
