Pipeline Reference

The pipeline runs three top-level stages, each with its own checklist of sub-tasks that must pass
before promotion.

(cid:127) Data ingestion

n schema validation

n null-rate audit

n window normalisation

(cid:127) Feature preparation

(cid:127) Model training

Smoothing Utility

The reference implementation is nine lines of dependency-free Python:

def moving_average(xs, k):
    if k <= 0:
        raise ValueError("window must be positive")
    acc = 0.0
    out = []
    for i, x in enumerate(xs):
        acc += x
        if i >= k:
            acc -= xs[i - k]
        out.append(acc / min(i + 1, k))
    return out

