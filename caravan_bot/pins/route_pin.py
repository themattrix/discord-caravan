import dataclasses
import re

from typing import Dict

import discord

from .. import caravan_model
from .. import places
from .. import route
from . import base_pin


class InvalidRoutePinFormat(Exception):
    """Raised if the message cannot be parsed."""


@dataclasses.dataclass
class RoutePin(base_pin.BasePin):
    update_for = frozenset({
        caravan_model.ModeUpdateReceipt,
        caravan_model.RouteUpdateReceipt,
        caravan_model.RouteAdvancedReceipt,
    })

    def content_and_embed(self, model: caravan_model.CaravanModel) -> Dict:
        return content_and_embed(model)


def populate_model(
        message: discord.Message,
        model: caravan_model.CaravanModel,
        all_places: places.Places):

    if not message.embeds:
        raise InvalidRoutePinFormat('Missing embeds!')

    embed = message.embeds[0]

    if not embed.description:
        raise InvalidRoutePinFormat('Missing route description!')

    mode_match = MODE_PATTERN.search(embed.description)
    if not mode_match:
        raise InvalidRoutePinFormat('Unrecognized mode format!')

    try:
        model.mode = MODE_TOKEN_TO_ENUM[
            mode_match.group('mode').casefold()]
    except KeyError:
        raise InvalidRoutePinFormat(
            f'Unrecognized mode: {mode_match.group("mode")}')

    route_match = ROUTE_PATTERN.search(embed.description)
    if not route_match:
        raise InvalidRoutePinFormat('Unrecognized route format!')

    route_str = route_match.group('route')
    if route_str:
        model.route = route.get_caravan_route(
            content=route_str,
            all_places=all_places,
            fuzzy=False)


def content_and_embed(model: caravan_model.CaravanModel) -> Dict:
    unvisited = tuple(s for s in model.route if not s.visited)

    route_header_string = '**Route**' + (
        '' if model.route else ' — _set with `!route`_')

    route_string = '_No route set!_' if not model.route else '\n'.join(
        f'- {stop_string(s)}' for s in model.route)

    status_string = f'**Status** — {ENUM_TO_MODE_STRING[model.mode]}'

    map_link = None if not unvisited else (
        'https://www.google.com/maps/dir/' + '/'.join(
            i.place.location for i in unvisited))

    if model.mode == caravan_model.CaravanMode.COMPLETED:
        title = 'Caravan complete!'
    elif not model.route:
        title = 'Please set a route!'
    else:
        title = 'Click here for {}route directions!'.format(
            'remaining ' if len(unvisited) < len(model.route) else '')

    if unvisited and model.mode != caravan_model.CaravanMode.COMPLETED:
        url = map_link
    else:
        url = None

    return {
        'content': f':blue_car: __**{model.channel.name}**__ :red_car:',
        'embed': discord.Embed(
            title=title,
            url=url,
            description=(
                f'\n'
                f'{status_string}\n'
                f'\n'
                f'{route_header_string}\n'
                f'{route_string}'))}


#
# Helpers
#

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

ENUM_TO_MODE_STRING = {
    caravan_model.CaravanMode.PLANNING: 'Planning... :map:',
    caravan_model.CaravanMode.ACTIVE: 'Active! :race_car:',
    caravan_model.CaravanMode.COMPLETED: 'Completed! :checkered_flag:',
}

MODE_TOKEN_TO_ENUM = {
    'planning': caravan_model.CaravanMode.PLANNING,
    'active': caravan_model.CaravanMode.ACTIVE,
    'completed': caravan_model.CaravanMode.COMPLETED,
}


def stop_string(stop: caravan_model.CaravanStop):
    return '{strike}{name}{strike}{skip}'.format(
        strike='~~' if stop.visited else '',
        name=stop.place.name,
        skip='' if stop.skip_reason is None else ' — _skipped{}_'.format(
            '' if not stop.skip_reason else f': "{stop.skip_reason}"'))
