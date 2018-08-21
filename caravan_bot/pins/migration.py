from typing import Tuple, Optional, Callable

from .. import caravan_model
from .format import base_pin
from .format import members_pin
from .format import route_pin

import discord


async def migrate(
        version: str,
        bot_pins: Tuple[discord.Message, ...],
        channel: discord.TextChannel,
        model: caravan_model.CaravanModel
) -> Tuple[base_pin.BasePin, ...]:

    return await MIGRATION_FN[version](
        bot_pins=bot_pins,
        channel=channel,
        model=model)


async def ensure_pins(
        channel: discord.TextChannel,
        model: caravan_model.CaravanModel,
        existing_route_pin: Optional[discord.Message] = None,
        existing_members_pin: Optional[discord.Message] = None,
) -> Tuple[base_pin.BasePin, ...]:

    # noinspection PyArgumentList
    pins = (
        route_pin.RoutePin(message=existing_route_pin),
        members_pin.MembersPin(message=existing_members_pin),
    )

    for p in pins:
        await p.ensure_post(channel=channel, model=model)
    for p in reversed(pins):
        await p.ensure_pinned()

    return pins


MIGRATION_FN = {}


def register(version: str):
    def decorator(fn: Callable):
        MIGRATION_FN[version] = fn
        return fn
    return decorator


@register('v1')
async def _(
        bot_pins: Tuple[discord.Message, ...],
        channel: discord.TextChannel,
        model: caravan_model.CaravanModel
) -> Tuple[Optional[base_pin.BasePin], ...]:

    existing_route_pin, existing_members_pin = None, None

    for p in bot_pins:
        if 'Route' in p.embeds[0].footer.text:
            existing_route_pin = p
        else:
            existing_members_pin = p

    return await ensure_pins(
        channel=channel,
        model=model,
        existing_route_pin=existing_route_pin,
        existing_members_pin=existing_members_pin)
