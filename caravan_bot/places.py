import dataclasses
import itertools
import json

from typing import Dict

import fuzzywuzzy.process

from .log import log


class PlaceNotFoundException(ValueError):
    """Raised when a given place was not found."""


@dataclasses.dataclass(frozen=True)
class Place:
    name: str
    location: str

    @property
    def maps_link(self):
        return f'https://maps.google.com/?q={self.location}'


@dataclasses.dataclass
class Places:
    places: Dict[str, Place]
    aliases: Dict[str, str]

    def __post_init__(self):
        self.__choices = tuple(itertools.chain(self.places, self.aliases))

    @classmethod
    def from_json(cls, path):
        with path.open() as f:
            raw_places = json.load(f)

        log.info(f'Loaded {len(raw_places)} place(s) from "{path}".')

        return cls(
            places={
                p: Place(name=p, location=v['location'])
                for p, v in raw_places.items()
            },
            aliases={
                a: p
                for p, v in raw_places.items()
                for a in v.get('aliases', ())
            })

    def get(self, name: str, fuzzy: bool) -> Place:
        return self.get_fuzzy(name) if fuzzy else self.get_exact(name)

    def get_exact(self, name: str) -> Place:
        try:
            return self.places[name]
        except KeyError:
            raise PlaceNotFoundException(name)

    def get_fuzzy(self, fuzzy_name: str) -> Place:
        result = fuzzywuzzy.process.extractOne(
            query=fuzzy_name,
            choices=tuple(self.__choices))

        if not result:
            raise PlaceNotFoundException(fuzzy_name)

        matched_name, score = result

        log.info(
            f'Matched "{fuzzy_name}" to "{matched_name}" with score {score}.')

        if score < 80:
            raise PlaceNotFoundException(fuzzy_name)

        return self.places[self.aliases.get(matched_name, matched_name)]
