import re

from . import sanitize

MESSAGE_PATTERN = re.compile(
    r'^'
    r'.*\n+'
    r'.*Route.*(?:\s+\(.*\))?\n+'
    r'(?:'
    r'  _Set\sa\sroute.*|'
    r'  (?P<route>(?:.|\n)+)'
    r')'
    r'$',
    re.IGNORECASE | re.VERBOSE)


class UnknownRoutePinFormatException(Exception):
    """Raised if the message cannot be parsed."""


class RoutePin:
    @classmethod
    def from_message(cls, message, places=None):
        match = MESSAGE_PATTERN.match(message.content)
        if not match:
            raise ValueError()
            # raise UnknownRoutePinFormatException()

        route = match.group('route') if places else None
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

    @property
    def title_string(self):
        return f':blue_car: __**{self.channel_name}**__ :red_car:'

    @property
    def route_title_string(self):
        return '**Route**' + (
            '' if not self.route else f' (:map: {self.map_link})')

    @property
    def route_string(self):
        return '_Set a route with `!route`._' if not self.route else '\n'.join(
            f'- {p.name}' for p in self.route)

    @property
    def map_link(self):
        return 'https://www.google.com/maps/dir/{}'.format(
            '/'.join(i.location for i in self.route))

    # TODO: use embeds
    def __str__(self):
        return (
            f'{self.title_string}\n'
            f'\n'
            f'{self.route_title_string}\n'
            f'{self.route_string}')
