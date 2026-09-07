# **Pipeline Reference** 

The pipeline runs three top-level stages, each with its own checklist of sub-tasks that must pass before promotion. 

- Data ingestion 

   - I schema validation 

I null-rate audit 

I window normalisation 

- Feature preparation 

- Model training 

## **Smoothing Utility** 

The reference implementation is nine lines of dependency-free Python: 

```
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
```

