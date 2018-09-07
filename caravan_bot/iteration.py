from typing import Any, Iterable, Tuple


def bucket(iterable: Iterable, *bucket_fns) -> Tuple[Tuple[Any, ...], ...]:
    buckets = tuple([] for _ in bucket_fns)

    for i in iterable:
        for index, goes_in_bucket in enumerate(bucket_fns):
            if goes_in_bucket(i):
                buckets[index].append(i)

    return tuple(tuple(b) for b in buckets)