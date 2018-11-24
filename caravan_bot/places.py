import dataclasses
import itertools
import json
import operator
import pathlib

from typing import Dict, Iterator

import fuzzywuzzy.process

from . import natural_language
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

    @property
    def lat_long(self):
        return tuple(float(c) for c in self.location.split(','))


@dataclasses.dataclass(frozen=True)
class FuzzyPlace:
    certainty: float
    place: Place


@dataclasses.dataclass
class Places:
    places: Dict[str, Place]
    aliases: Dict[str, str]

    def __post_init__(self):
        self.__choices = tuple(itertools.chain(self.places, self.aliases))

    @classmethod
    def from_json(cls, path: pathlib.Path) -> 'Places':
        with path.open() as f:
            raw_places = json.load(f)
        log.info(f'Loaded {len(raw_places)} place(s) from "{path}".')
        return cls.from_dict(raw_places)

    @classmethod
    def from_dict(cls, raw_places: dict) -> 'Places':
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

    def get_exact(self, name: str) -> Place:
        try:
            return self.places[name]
        except KeyError:
            raise PlaceNotFoundException(name)

    def get_fuzzy(
            self,
            fuzzy_name: str,
            score_cutoff: int = 60,
            limit: int = 3
            ) -> Iterator[FuzzyPlace]:

        results = fuzzywuzzy.process.extractBests(
            query=fuzzy_name,
            choices=tuple(self.__choices),
            score_cutoff=score_cutoff,
            limit=limit)

        if not results:
            raise PlaceNotFoundException(fuzzy_name)

        j = natural_language.join
        log.info(
            f'Matched "{fuzzy_name}" to '
            f'{j(f"{name} ({score}%)" for name, score in results)}')

        # Sort the results by score so that each unique place will end up with
        # the highest score from all of its matches.
        unique_results = {
            self.places[self.aliases.get(name, name)]: score
            for name, score in sorted(results, key=operator.itemgetter(1))}

        yield from (
            FuzzyPlace(certainty=score / 100.0, place=place)
            for place, score in unique_results.items())
