import re

import discord

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


class UnknownRoutePinFormatException(Exception):
    """Raised if the message cannot be parsed."""


class RoutePin:
    @classmethod
    def from_message(cls, message: discord.Message, places=None):
        if not message.embeds:
            raise UnknownRoutePinFormatException('Missing embeds!')

        embed = message.embeds[0]

        route_match = ROUTE_DESCRIPTION_PATTERN.search(embed.description)
        if not route_match:
            raise UnknownRoutePinFormatException('Unrecognized route format!')

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
