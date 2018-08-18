from typing import Iterable, Sized, Union

import inflection


def join(seq: Iterable[str]):
    seq = tuple(seq)

    if not seq:
        return ''
    if len(seq) == 1:
        return seq[0]
    if len(seq) == 2:
        return f'{seq[0]} and {seq[1]}'

    return ', '.join(seq[:-1]) + f', and {seq[-1]}'


def pluralize(word: str, collection: Union[Sized, int]) -> str:
    """
    Pluralize the given word, based off of either a sized collection or
    off an item count.
    """
    count = collection if isinstance(collection, int) else len(collection)
    return word if count == 1 else inflection.pluralize(word)
