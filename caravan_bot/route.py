import collections
import dataclasses

from typing import Iterable, Optional, Tuple

from . import natural_language
from . import places
from . import sanitize


class EmptyRouteException(Exception):
    """Raised when a route was expected to be non-empty."""


class RouteUnchangedException(Exception):
    """Raised when the route was expected to change, but didn't."""


class InvalidRouteException(Exception):
    """Raised when the route contains invalid names or duplicate stops."""

    def __init__(self, unknowns=(), duplicates=()):
        self.unknowns = unknowns
        self.duplicates = duplicates

    def unknowns_str(self) -> str:
        return 'Unknown route location{}: {}'.format(
            '' if len(self.unknowns) == 1 else 's',
            natural_language.join(f'"{u}"' for u in self.unknowns))

    def duplicates_str(self) -> str:
        return 'Duplicate route location{}: {}'.format(
            '' if len(self.duplicates) == 1 else 's',
            natural_language.join(f'"{n}"' for n in self.duplicates))


class Route:
    @classmethod
    def from_message(
            cls,
            content: str,
            all_places: places.Places,
            fuzzy: bool) -> 'Route':

        unknown_place_names = []

        def gen_stops(route_nodes: Iterable[sanitize.RouteNode]):
            for node in route_nodes:
                try:
                    yield RouteStop(
                        place=all_places.get(name=node.name, fuzzy=fuzzy),
                        visited=node.visited,
                        skip_reason=node.skip_reason)
                except places.PlaceNotFoundException:
                    unknown_place_names.append(node.name)

        stops = tuple(gen_stops(sanitize.clean_route(content)))

        duplicate_stop_names = tuple(
            stop.place.name for stop, count
            in collections.Counter(stops).items()
            if count > 1)

        if unknown_place_names or duplicate_stop_names:
            raise InvalidRouteException(
                unknowns=sorted(unknown_place_names),
                duplicates=sorted(duplicate_stop_names))

        return cls(stops=stops)

    def __init__(self, stops: Iterable['RouteStop'] = ()):
        self.stops = tuple(stops)

    def __bool__(self):
        return bool(self.stops)

    def reset(self):
        for s in self.stops:
            s.reset()

    def advance(self):
        self._advance()

    def skip(self, reason: Optional[str]):
        prev = self._advance()
        prev.skip_reason = reason or ''

    def _advance(self) -> 'RouteStop':
        remaining = self.remaining
        if not remaining:
            raise RouteExhausted()
        remaining[0].visited = True
        return remaining[0]

    def add(self, route: 'Route', append: bool):
        if not route.stops:
            raise EmptyRouteException()

        # Ensure that the added route does not duplicate any of the existing
        # stops.
        duplicate_stops = frozenset(route.stops) & frozenset(self.stops)

        if duplicate_stops:
            raise InvalidRouteException(
                duplicates=sorted(s.place.name for s in duplicate_stops))

        insert_at = len(self.stops) if append else self.first_unvisited_index
        self.stops = (
            self.stops[:insert_at] + route.stops + self.stops[insert_at:])

    def remove(self, route: 'Route') -> int:
        if not route.stops:
            raise EmptyRouteException()

        stops = tuple(s for s in self.stops if s not in frozenset(route.stops))
        removed_len = len(self.stops) - len(stops)

        if removed_len == 0:
            raise RouteUnchangedException()

        self.stops = stops

        return removed_len

    @property
    def first_unvisited_index(self) -> int:
        i = 0
        for i, s in enumerate(self.stops):
            if not s.visited:
                return i
        return i + 1

    @property
    def remaining(self) -> Tuple['RouteStop', ...]:
        return tuple(i for i in self.stops if not i.visited)

    @property
    def statistics(self) -> 'RouteStatistics':
        return RouteStatistics.from_route(self.stops)


class RouteExhausted(Exception):
    """Raised when attempting to advance past the end of the route."""


@dataclasses.dataclass(unsafe_hash=True)
class RouteStop:
    place: places.Place
    visited: bool = dataclasses.field(
        default=False, compare=False)
    skip_reason: Optional[str] = dataclasses.field(
        default=None, compare=False)

    def reset(self):
        self.visited = False
        self.skip_reason = None


@dataclasses.dataclass
class RouteStatistics:
    stops_visited: int
    stops_skipped: int
    stops_remaining: int

    @classmethod
    def from_route(cls, route: Iterable[RouteStop]):
        visited, skipped, remaining = 0, 0, 0

        for s in route:
            if s.visited and s.skip_reason is None:
                visited += 1
            elif s.visited:
                skipped += 1
            else:
                remaining += 1

        return cls(
            stops_visited=visited,
            stops_skipped=skipped,
            stops_remaining=remaining)
