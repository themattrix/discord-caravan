import dataclasses
import json

import fuzzywuzzy.process

from .log import log


class PlaceNotFoundException(ValueError):
    """Raised when a given place was not found."""


@dataclasses.dataclass
class Place:
    name: str
    location: str


class Places:
    @classmethod
    def from_json(cls, path):
        with path.open() as f:
            places = json.load(f)

        log.info(f'Loaded {len(places)} place(s) from "{path}".')

        return cls(places=places)

    def __init__(self, places):
        self.places = places

    def get_exact(self, name) -> Place:
        try:
            return Place(name=name, location=self.places[name])
        except KeyError:
            raise PlaceNotFoundException(name)

    def get_fuzzy(self, fuzzy_name) -> Place:
        result = fuzzywuzzy.process.extractOne(
            query=fuzzy_name,
            choices=tuple(self.places),
            score_cutoff=50)

        if not result:
            raise PlaceNotFoundException(fuzzy_name)

        real_name, score = result
        log.info(
            f'Matched "{fuzzy_name}" to place "{real_name}" with score '
            f'{score}.')

        return Place(name=real_name, location=self.places[real_name])
