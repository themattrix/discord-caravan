import dataclasses
import enum
import re

from typing import Iterable, Optional, Tuple

import discord

from .. import places
from .. import sanitize
from . import base_pin

MODE_PATTERN = re.compile(
    r'\bStatus\b.*?—\s*(?P<mode>\w+)',
    re.IGNORECASE)

ROUTE_PATTERN = re.compile(
    r'.*Route.*\n'
    r'(?:'
    r'  _No.*|'      # no route set
    r'  (?P<route>'  # route set 
    r'      (?:-\s.*\n)*'  
    r'      (?:-\s.*)'
    r'  )'
    r')',
    re.IGNORECASE | re.VERBOSE)


class RoutePinFormatException(Exception):
    """Raised if the message cannot be parsed."""


class CaravanModeAlreadyCorrect(Exception):
    """Raised when the caravan mode does not need to be changed."""


class EmptyRouteException(Exception):
    """Raised when a route was expected to be non-empty."""


class UnknownRouteLocations(Exception):
    """Raised when one or more route location names is unrecognized."""

    def __init__(self, unknown_names):
        self.unknown_names = unknown_names

    def __str__(self):
        return 'Unknown route location{}: {}'.format(
            '' if len(self.unknown_names) == 1 else 's',
            ', '.join(f'"{u}"' for u in self.unknown_names))


class RouteExhausted(Exception):
    """Raised when attempting to advance past the end of the route."""


class CaravanMode(enum.Enum):
    PLANNING = 0
    ACTIVE = 1
    COMPLETED = 2


ENUM_TO_MODE_STRING = {
    CaravanMode.PLANNING: 'Planning... :map:',
    CaravanMode.ACTIVE: 'Active! :race_car:',
    CaravanMode.COMPLETED: 'Completed! :fireworks:',
}

MODE_TOKEN_TO_ENUM = {
    'planning': CaravanMode.PLANNING,
    'active': CaravanMode.ACTIVE,
    'completed': CaravanMode.COMPLETED,
}


@dataclasses.dataclass
class RouteStop:
    place: places.Place
    visited: bool = False
    skip_reason: Optional[str] = None

    def reset(self):
        self.visited = False
        self.skip_reason = None

    def __str__(self):
        return '{strike}{name}{strike}{skip}'.format(
            strike='~~' if self.visited else '',
            name=self.place.name,
            skip='' if self.skip_reason is None else ' — _skipped{}_'.format(
                '' if not self.skip_reason else f': "{self.skip_reason}"'))


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


def get_route(
        route: str,
        all_places: places.Places,
        fuzzy: bool) -> Tuple[RouteStop, ...]:

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

    it = sanitize.clean_route(route)
    it = gen_stops(it)
    route = tuple(it)

    if unknown_place_names:
        raise UnknownRouteLocations(unknown_names=unknown_place_names)

    return route


class RoutePin(base_pin.BasePin):
    @classmethod
    def from_message(
            cls,
            message: discord.Message,
            all_places: Optional[places.Places] = None):

        if not message.embeds:
            raise RoutePinFormatException('Missing embeds!')

        embed = message.embeds[0]

        mode_match = MODE_PATTERN.search(embed.description)
        if not mode_match:
            raise RoutePinFormatException('Unrecognized mode format!')

        try:
            mode = MODE_TOKEN_TO_ENUM[
                mode_match.group('mode').casefold()]
        except KeyError:
            raise RoutePinFormatException(
                f'Unrecognized mode: {mode_match.group("mode")}')

        route_match = ROUTE_PATTERN.search(embed.description)
        if not route_match:
            raise RoutePinFormatException('Unrecognized route format!')

        route = route_match.group('route') if all_places else None
        if route:
            route = get_route(route=route, all_places=all_places, fuzzy=False)

        return cls(
            channel_name=message.channel.name,
            route=route,
            mode=mode,
            message=message)

    def __init__(
            self,
            channel_name: str,
            route: Optional[Iterable[RouteStop]] = (),
            mode: CaravanMode = CaravanMode.PLANNING,
            message: discord.Message = None):

        super().__init__()
        self.channel_name = channel_name
        self.route = tuple(route or ())
        self.mode = mode
        self.message = message

    def reroute(self, route):
        self.route = route

    def start(self):
        if self.mode == CaravanMode.ACTIVE:
            raise CaravanModeAlreadyCorrect(
                'The caravan is already in progress!')
        self.mode = CaravanMode.ACTIVE

    def stop(self):
        if self.mode in {CaravanMode.PLANNING, CaravanMode.COMPLETED}:
            raise CaravanModeAlreadyCorrect(
                'The caravan is already _not_ in progress!')
        self.mode = CaravanMode.COMPLETED

    def reset(self):
        if self.mode == CaravanMode.PLANNING:
            raise CaravanModeAlreadyCorrect(
                'The caravan is already in the planning phase!')
        self.mode = CaravanMode.PLANNING
        for s in self.route:
            s.reset()

    def advance(self):
        self._advance()

    def skip(self, reason: Optional[str]):
        prev = self._advance()
        prev.skip_reason = reason or ''

    def _advance(self) -> RouteStop:
        remaining = self.remaining_route
        if not remaining:
            raise RouteExhausted()
        remaining[0].visited = True
        return remaining[0]

    @property
    def first_unvisited_index(self) -> int:
        for i, s in enumerate(self.route):
            if not s.visited:
                return i
        return 0

    def add_route(self, route: Tuple[RouteStop], append: bool):
        if not route:
            raise EmptyRouteException()
        insert_at = len(self.route) if append else self.first_unvisited_index
        self.route = (
            self.route[:insert_at] + route + self.route[insert_at:])

    @property
    def remaining_route(self) -> Tuple[RouteStop, ...]:
        return tuple(i for i in self.route if not i.visited)

    @property
    def route_statistics(self) -> RouteStatistics:
        return RouteStatistics.from_route(self.route)

    @property
    def title_string(self):
        return f':blue_car: __**{self.channel_name}**__ :red_car:'

    @property
    def route_header_string(self):
        return '**Route**' + ('' if self.route else ' — _set with `!route`_')

    @property
    def route_string(self):
        return '_No route set!_' if not self.route else '\n'.join(
            f'- {s}' for s in self.route)

    @property
    def status_string(self):
        return f'**Status** — {ENUM_TO_MODE_STRING[self.mode]}'

    @property
    def map_link(self):
        locations = '/'.join(
            i.place.location for i in self.remaining_route)
        return None if not locations else (
            f'https://www.google.com/maps/dir/{locations}')

    @property
    def title(self):
        if self.mode == CaravanMode.COMPLETED:
            return 'Caravan complete!'
        if not self.route:
            return 'Please set a route!'
        remaining = self.remaining_route
        if remaining:
            return 'Click here for {}route directions!'.format(
                'remaining ' if len(remaining) < len(self.route) else '')

    @property
    def content_and_embed(self):
        url = None
        if self.remaining_route and self.mode != CaravanMode.COMPLETED:
            url = self.map_link
        return {
            'content': self.title_string,
            'embed': discord.Embed(
                title=self.title,
                url=url,
                description=(
                    f'\n'
                    f'{self.status_string}\n'
                    f'\n'
                    f'{self.route_header_string}\n'
                    f'{self.route_string}'))}
