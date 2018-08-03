from typing import Iterable


def join(seq: Iterable[str]):
    seq = tuple(seq)

    if not seq:
        return ''
    if len(seq) == 1:
        return seq[0]
    if len(seq) == 2:
        return f'{seq[0]} and {seq[1]}'

    return ', '.join(seq[:-1]) + f', and {seq[-1]}'
