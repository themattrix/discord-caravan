from typing import Any, Iterable, Iterator, List, Tuple, TypeVar   # noqa


def bucket(iterable: Iterable, *bucket_fns) -> Tuple[Tuple[Any, ...], ...]:
    buckets = tuple([] for _ in bucket_fns)  # type: Tuple[List[Any], ...]

    for i in iterable:
        for index, goes_in_bucket in enumerate(bucket_fns):
            if goes_in_bucket(i):
                buckets[index].append(i)

    return tuple(tuple(b) for b in buckets)


T = TypeVar('T')


def unique_product(
        choices_iter: Iterable[Iterable[T]]
        ) -> Iterator[Tuple[T, ...]]:

    choices = tuple(
        tuple(i) for i in choices_iter)  # type: Tuple[Tuple[T, ...], ...]
    indices = [0 for _ in choices]  # type: List[int]
    product = []  # type: List[T]

    while True:
        c = len(product)

        try:
            while True:
                i = choices[c][indices[c]]
                if i is None or i not in product:
                    break
                indices[c] += 1

            product.append(i)

            if len(product) == len(choices):
                yield tuple(product)
                product.pop()
                indices[c] += 1

        except IndexError:
            if not product:
                break
            product.pop()
            indices[c] = 0
            indices[c - 1] += 1
