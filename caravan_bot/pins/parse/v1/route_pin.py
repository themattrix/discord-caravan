import re

import discord

from .... import caravan_model
from .... import places
from .... import route
from ... import exceptions


def populate_model(
        message: discord.Message,
        model: caravan_model.CaravanModel,
        all_places: places.Places):

    if not message.embeds:
        raise exceptions.InvalidPinFormat('Missing embeds!')

    if len(message.embeds) != 1:
        raise exceptions.InvalidPinFormat(
            f'Expected 1 embed but found {len(message.embeds)}.')

    embed = message.embeds[0]

    if len(embed.fields) != 2:
        raise exceptions.InvalidPinFormat(
            f'Expected 2 embed fields but found {len(embed.fields)}.')

    mode_field, route_field = embed.fields

    mode_match = MODE_PATTERN.search(mode_field.value)
    if not mode_match:
        raise exceptions.InvalidPinFormat('Unrecognized mode format!')

    try:
        model.mode = MODE_TOKEN_TO_ENUM[
            mode_match.group('mode').casefold()]
    except KeyError:
        raise exceptions.InvalidPinFormat(
            f'Unrecognized mode: {mode_match.group("mode")}')

    if not NO_ROUTE_PATTERN.match(route_field.value):
        model.route = route.get_caravan_route(
            content=route_field.value,
            all_places=all_places,
            fuzzy=False)


#
# Helpers
#

MODE_PATTERN = re.compile(r'^(?P<mode>\w+)')
NO_ROUTE_PATTERN = re.compile(r'^_?No route.*', re.IGNORECASE)

MODE_TOKEN_TO_ENUM = {
    'planning': caravan_model.CaravanMode.PLANNING,
    'active': caravan_model.CaravanMode.ACTIVE,
    'completed': caravan_model.CaravanMode.COMPLETED,
}
