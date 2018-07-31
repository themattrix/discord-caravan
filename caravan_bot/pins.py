import dataclasses
import enum
import re

from typing import Callable, Iterable, Optional, Tuple

import discord

from . import natural_language
from . import places
from . import sanitize

STATUS_PATTERN = re.compile(
    r'\bStatus\b.*?—\s*(?P<status>\w+)',
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
    re.IGNORECASE | re.VERBOSE
)


class RoutePinFormatException(Exception):
    """Raised if the message cannot be parsed."""


class CaravanStatusAlreadyCorrect(Exception):
    """Raised when the caravan status does not need to be changed."""


class UnknownRouteLocations(Exception):
    """Raised when one or more route location names is unrecognized."""

    def __init__(self, unknown_names):
        self.unknown_names = unknown_names


class CaravanStatus(enum.Enum):
    PLANNING = 0
    ACTIVE = 1
    COMPLETED = 2


ENUM_TO_STATUS_STRING = {
    CaravanStatus.PLANNING: 'Planning... :map:',
    CaravanStatus.ACTIVE: 'Active! :race_car:',
    CaravanStatus.COMPLETED: 'Completed! :fireworks:',
}

STATUS_TOKEN_TO_ENUM = {
    'planning': CaravanStatus.PLANNING,
    'active': CaravanStatus.ACTIVE,
    'completed': CaravanStatus.COMPLETED,
}


@dataclasses.dataclass
class RouteStop:
    place: places.Place
    visited: bool

    def __str__(self):
        return '{strike}{name}{strike}'.format(
            strike='~~' if self.visited else '',
            name=self.place.name)


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
                    visited=node.visited)
            except places.PlaceNotFoundException:
                unknown_place_names.append(node.name)

    it = sanitize.clean_route(route)
    it = gen_stops(it)
    route = tuple(it)

    if unknown_place_names:
        raise UnknownRouteLocations(unknown_names=unknown_place_names)

    return route


class RoutePin:
    @classmethod
    def from_message(
            cls,
            message: discord.Message,
            all_places: Optional[places.Places] = None):

        if not message.embeds:
            raise RoutePinFormatException('Missing embeds!')

        embed = message.embeds[0]

        status_match = STATUS_PATTERN.search(embed.description)
        if not status_match:
            raise RoutePinFormatException('Unrecognized status format!')

        try:
            status = STATUS_TOKEN_TO_ENUM[
                status_match.group('status').casefold()]
        except KeyError:
            raise RoutePinFormatException(
                f'Unrecognized status: {status_match.group("status")}')

        route_match = ROUTE_PATTERN.search(embed.description)
        if not route_match:
            raise RoutePinFormatException('Unrecognized route format!')

        route = route_match.group('route') if all_places else None
        if route:
            route = get_route(route=route, all_places=all_places, fuzzy=False)

        return cls(
            channel_name=message.channel.name,
            route=route,
            status=status,
            message=message)

    def __init__(
            self,
            channel_name: str,
            route: Optional[Iterable[RouteStop]] = (),
            status: CaravanStatus = CaravanStatus.PLANNING,
            message: discord.Message = None):

        self.channel_name = channel_name
        self.route = tuple(route or ())
        self.status = status
        self.message = message

    def reroute(self, route):
        self.route = route

    def start(self):
        if self.status == CaravanStatus.ACTIVE:
            raise CaravanStatusAlreadyCorrect(
                'The caravan is already in progress!')
        self.status = CaravanStatus.ACTIVE

    def stop(self):
        if self.status in {CaravanStatus.PLANNING, CaravanStatus.COMPLETED}:
            raise CaravanStatusAlreadyCorrect(
                'The caravan is already _not_ in progress!')
        self.status = CaravanStatus.COMPLETED

    def reset(self):
        if self.status == CaravanStatus.PLANNING:
            raise CaravanStatusAlreadyCorrect(
                'The caravan is already in the planning phase!')
        self.status = CaravanStatus.PLANNING
        for s in self.route:
            s.visited = False

    @property
    def remaining_route(self) -> Tuple[RouteStop, ...]:
        return tuple(i for i in self.route if not i.visited)

    @property
    def title_string(self):
        return f':blue_car: __**{self.channel_name}**__ :red_car:'

    @property
    def route_header_string(self):
        return '**Route** — _{} with `!route`_'.format(
            'set' if not self.route else 'change')

    @property
    def route_string(self):
        return '_No route set!_' if not self.route else '\n'.join(
            f'- {s}' for s in self.route)

    @property
    def status_string(self):
        return f'**Status** — {ENUM_TO_STATUS_STRING[self.status]}'

    @property
    def map_link(self):
        locations = '/'.join(
            i.place.location for i in self.remaining_route)
        return None if not locations else (
            f'https://www.google.com/maps/dir/{locations}')

    @property
    def content_and_embed(self):
        url = self.map_link
        return {
            'content': self.title_string,
            'embed': discord.Embed(
                title=(
                    'Please set a route!' if not url else
                    'Click here for route directions!'),
                url=url,
                description=(
                    f'\n'
                    f'{self.status_string}\n'
                    f'\n'
                    f'{self.route_header_string}\n'
                    f'{self.route_string}'))}


MEMBERS_PATTERN = re.compile(
    r'.*Leader.*\n'
    r'(?:'
    r'  _No.*|'           # no leaders set
    r'  (?P<leaders>.*)'  # leaders set 
    r')',
    re.IGNORECASE | re.VERBOSE
)


class MembersPinFormatException(Exception):
    """Raised if the message cannot be parsed."""


class MembersPin:
    @classmethod
    def from_message(cls, message: discord.Message, gen_users: Callable):
        match = MEMBERS_PATTERN.search(message.content)
        if not match:
            raise MembersPinFormatException('Unrecognized members format!')

        leaders_string = match.group('leaders') or ''

        return cls(
            leaders=gen_users(sanitize.gen_user_ids(leaders_string)),
            message=message)

    def __init__(
            self,
            leaders: Iterable[discord.User] = (),
            message: Optional[discord.Message] = None):
        self.leaders = frozenset(leaders)
        self.message = message

    def with_updated_leaders(self, leaders: Iterable[discord.User]):
        return self.__class__(leaders=leaders, message=self.message)

    @property
    def leaders_header_string(self):
        return '**Caravan Leader{}** — _{} with `!leaders`_'.format(
            '' if len(self.leaders) == 1 else 's',
            'set' if not self.leaders else 'change')

    @property
    def sorted_leaders(self):
        return sorted(self.leaders, key=lambda u: u.id)

    @property
    def leaders_list_string(self):
        return natural_language.join(u.mention for u in self.sorted_leaders)

    @property
    def leaders_string(self):
        return '_No leaders set!_' if not self.leaders else (
            self.leaders_list_string)

    @property
    def content_and_embed(self):
        return {
            'content': (
                f'{self.leaders_header_string}\n'
                f'{self.leaders_string}'),
        }

