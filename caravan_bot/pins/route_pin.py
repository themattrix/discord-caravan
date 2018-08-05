import enum
import re

from typing import Optional

import discord

from .. import places
from ..route import Route, RouteStop
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
            route = Route.from_message(
                content=route,
                all_places=all_places,
                fuzzy=False)

        return cls(
            channel_name=message.channel.name,
            route=route,
            mode=mode,
            message=message)

    def __init__(
            self,
            channel_name: str,
            route: Optional[Route] = None,
            mode: CaravanMode = CaravanMode.PLANNING,
            message: discord.Message = None):

        super().__init__()
        self.channel_name = channel_name
        self.route = route or Route()
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
        self.route.reset()

    def advance(self):
        self.route.advance()

    def skip(self, reason: Optional[str]):
        self.route.skip(reason=reason)

    def add_route(self, route: Route, append: bool):
        self.route.add(route=route, append=append)

    def remove_stops(self, route: Route) -> int:
        return self.route.remove(route=route)

    @property
    def title_string(self):
        return f':blue_car: __**{self.channel_name}**__ :red_car:'

    @property
    def route_header_string(self):
        return '**Route**' + ('' if self.route else ' — _set with `!route`_')

    @property
    def route_string(self):
        return '_No route set!_' if not self.route else '\n'.join(
            f'- {stop_string(s)}' for s in self.route.stops)

    @property
    def status_string(self):
        return f'**Status** — {ENUM_TO_MODE_STRING[self.mode]}'

    @property
    def map_link(self):
        locations = '/'.join(
            i.place.location for i in self.route.remaining)
        return None if not locations else (
            f'https://www.google.com/maps/dir/{locations}')

    @property
    def title(self):
        if self.mode == CaravanMode.COMPLETED:
            return 'Caravan complete!'
        if not self.route:
            return 'Please set a route!'
        remaining = self.route.remaining
        if remaining:
            return 'Click here for {}route directions!'.format(
                'remaining ' if len(remaining) < len(self.route.stops) else '')

    @property
    def content_and_embed(self):
        url = None
        if self.route.remaining and self.mode != CaravanMode.COMPLETED:
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


def stop_string(stop: RouteStop):
    return '{strike}{name}{strike}{skip}'.format(
        strike='~~' if stop.visited else '',
        name=stop.place.name,
        skip='' if stop.skip_reason is None else ' — _skipped{}_'.format(
            '' if not stop.skip_reason else f': "{stop.skip_reason}"'))
