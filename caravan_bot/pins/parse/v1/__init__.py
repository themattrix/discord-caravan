import functools

from typing import Callable, Tuple

import discord

from .... import caravan_model
from .... import members
from .... import places
from . import route_pin
from . import members_pin


def populate_model(
        model: caravan_model.CaravanModel,
        bot_pins: Tuple[discord.Message],
        all_places: places.Places,
        get_user: Callable[[int], discord.User]):
    """
    Populate the model with whatever this message contains.
    """
    for p in bot_pins:
        if 'Route' in p.embeds[0].footer.text:
            route_pin.populate_model(
                message=p,
                model=model,
                all_places=all_places)
        else:
            members_pin.populate_model(
                message=p,
                model=model,
                gen_users=functools.partial(members.gen_users, get_user),
                gen_members=functools.partial(members.gen_members, get_user))
