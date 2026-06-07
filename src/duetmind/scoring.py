from __future__ import annotations

from collections import Counter
from math import log2


def cosine_distance_from_token_sets(a_text: str, b_text: str) -> float:
    a_tokens = a_text.lower().split()
    b_tokens = b_text.lower().split()
    if not a_tokens or not b_tokens:
        return 1.0

    a_counts = Counter(a_tokens)
    b_counts = Counter(b_tokens)

    vocab = set(a_counts) | set(b_counts)
    dot = sum(a_counts[t] * b_counts[t] for t in vocab)
    a_norm = sum(v * v for v in a_counts.values()) ** 0.5
    b_norm = sum(v * v for v in b_counts.values()) ** 0.5
    if a_norm == 0 or b_norm == 0:
        return 1.0
    cos = dot / (a_norm * b_norm)
    return 1.0 - cos


def jaccard_similarity(a_tokens: set[str], b_tokens: set[str]) -> float:
    if not a_tokens and not b_tokens:
        return 1.0
    union = a_tokens | b_tokens
    if not union:
        return 0.0
    return len(a_tokens & b_tokens) / len(union)


def jensen_shannon_distance(tokens_a: list[str], tokens_b: list[str]) -> float:
    # Distance in [0,1]
    pa = Counter(tokens_a)
    pb = Counter(tokens_b)
    vocab = set(pa) | set(pb)
    if not vocab:
        return 0.0
    suma = sum(pa.values()) or 1
    sumb = sum(pb.values()) or 1

    dist_a = {k: pa[k] / suma for k in vocab}
    dist_b = {k: pb[k] / sumb for k in vocab}
    mean = {k: 0.5 * (dist_a[k] + dist_b[k]) for k in vocab}

    def kl(p: dict[str, float], m: dict[str, float]) -> float:
        val = 0.0
        for k, pv in p.items():
            if pv > 0:
                val += pv * log2(pv / m[k])
        return val

    jsd = 0.5 * kl(dist_a, mean) + 0.5 * kl(dist_b, mean)
    return min(1.0, jsd ** 0.5)


def financial_discount(tokens_fase: int, presupuesto_fase: int) -> float:
    ratio = tokens_fase / max(1, presupuesto_fase)
    return max(0.5, 1.0 - ratio * ratio)


def compute_score(
    agreement_a: float,
    stability_s: float,
    risk_r: float,
    confidence_a: float,
    confidence_b: float,
    tokens_fase: int,
    presupuesto_fase: int,
) -> float:
    c_ajustada = ((confidence_a + confidence_b) / 2.0) * (agreement_a * stability_s)
    fd = financial_discount(tokens_fase, presupuesto_fase)
    score = (
        (agreement_a * 0.30)
        + (stability_s * 0.25)
        + (risk_r * 0.25)
        + (c_ajustada * 0.20)
    ) * fd
    return score * 10.0
