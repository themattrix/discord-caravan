import re

from typing import Callable, Iterable, Optional

import discord

from . import natural_language
from . import sanitize

ROUTE_DESCRIPTION_PATTERN = re.compile(
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


class RoutePin:
    @classmethod
    def from_message(cls, message: discord.Message, places=None):
        if not message.embeds:
            raise RoutePinFormatException('Missing embeds!')

        embed = message.embeds[0]

        route_match = ROUTE_DESCRIPTION_PATTERN.search(embed.description)
        if not route_match:
            raise RoutePinFormatException('Unrecognized route format!')

        route = route_match.group('route') if places else None
        if route:
            i = sanitize.clean_route(route)
            i = (places.get_exact(n) for n in i)
            route = tuple(i)

        return cls(
            channel_name=message.channel.name,
            route=route,
            message=message)

    def __init__(self, channel_name, route=(), message=None):
        self.channel_name = channel_name
        self.route = tuple(route or ())
        self.message = message

    def with_updated_route(self, route):
        return self.__class__(
            channel_name=self.channel_name,
            route=route,
            message=self.message)

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
            f'- {p.name}' for p in self.route)

    @property
    def map_link(self):
        return 'https://www.google.com/maps/dir/{}'.format(
            '/'.join(i.location for i in self.route))

    @property
    def content_and_embed(self):
        return {
            'content': self.title_string,
            'embed': discord.Embed(
                title=f'Click here for route directions!',
                url=self.map_link,
                description=(
                    f'{self.route_header_string}\n'
                    f'{self.route_string}')),
        }


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

