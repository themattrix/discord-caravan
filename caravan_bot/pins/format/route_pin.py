import dataclasses

from typing import Dict

import discord

from ... import caravan_model
from . import base_pin


@dataclasses.dataclass
class RoutePin(base_pin.BasePin):
    update_for = frozenset({
        caravan_model.ModeUpdateReceipt,
        caravan_model.RouteUpdateReceipt,
        caravan_model.RouteAdvancedReceipt,
    })

    def content_and_embed(self, model: caravan_model.CaravanModel) -> Dict:
        return content_and_embed(model)


def content_and_embed(model: caravan_model.CaravanModel) -> Dict:
    unvisited = tuple(s for s in model.route if not s.visited)

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

    embed = discord.Embed(title=title, url=url)

    embed.add_field(
        name='Status',
        value=ENUM_TO_MODE_STRING[model.mode],
        inline=False)

    embed.add_field(
        name='Route',
        value=(
            '_No route set! A leader may set one with `!route`._'
            if not model.route else '\n'.join(
                f'- {stop_string(s)}' for s in model.route)),
        inline=False)

    embed.set_footer(text='Route | Caravan Bot v1')

    return {
        'content': f':blue_car: __**{model.channel.name}**__ :red_car:',
        'embed': embed}


#
# Helpers
#

ENUM_TO_MODE_STRING = {
    caravan_model.CaravanMode.PLANNING: 'Planning... :map:',
    caravan_model.CaravanMode.ACTIVE: 'Active! :race_car:',
    caravan_model.CaravanMode.COMPLETED: 'Completed! :checkered_flag:',
}


def stop_string(stop: caravan_model.CaravanStop):
    return '{strike}{name}{strike}{skip}'.format(
        strike='~~' if stop.visited else '',
        name=stop.place.name,
        skip='' if stop.skip_reason is None else ' — _skipped{}_'.format(
            '' if not stop.skip_reason else f': "{stop.skip_reason}"'))
