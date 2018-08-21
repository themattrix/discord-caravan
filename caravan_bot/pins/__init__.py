import functools
import importlib
import importlib.resources
import re

from typing import Callable, Tuple

import discord

from ..log import channel_log
from .. import caravan_model
from .. import places
from .. import route
from .format import base_pin
from . import exceptions
from . import migration


async def init_pins(
        model: caravan_model.CaravanModel,
        channel: discord.TextChannel,
        bot_user: discord.User,
        all_places: places.Places,
        get_user: Callable[[int], discord.User]
) -> Tuple[base_pin.BasePin, ...]:
    """
    Populate the model with whatever the pinned messages in this
    channel contain.
    """
    bot_pins = await channel.pins()
    bot_pins = (i for i in bot_pins if i.author == bot_user)
    bot_pins = tuple(bot_pins)

    c_log = functools.partial(channel_log, channel)

    if not bot_pins:
        c_log('INFO', 'Fresh caravan channel! Initializing...')
        return await migration.ensure_pins(channel=channel, model=model)

    try:
        footer_text = bot_pins[0].embeds[0].footer.text
        match = FOOTER_VERSION.search(footer_text)
    except IndexError:
        raise exceptions.InvalidPinFormat('Missing embeds!') from None
    except AttributeError:
        raise exceptions.InvalidPinFormat('Missing footer!') from None

    if not match:
        raise exceptions.InvalidPinFormat(
            f'Unable to get version from footer text: {footer_text}') from None

    pin_version = match.group('version')
    c_log('INFO', f'Parsing {pin_version} pins.')

    try:
        PIN_VERSIONS[pin_version].populate_model(
            model=model,
            bot_pins=bot_pins,
            all_places=all_places,
            get_user=get_user)
    except KeyError:
        raise exceptions.InvalidPinFormat(
            f'Unknown pin version: {pin_version}') from None
    except exceptions.InvalidPinFormat as e:
        raise exceptions.InvalidPinFormat(
            f'Invalid pin format: {e}') from None
    except route.UnknownPlaceNames as e:
        raise exceptions.InvalidPinFormat(
            f'Invalid gym(s): {e.unknown_names}') from None

    return await migration.migrate(
        version=pin_version,
        bot_pins=bot_pins,
        channel=channel,
        model=model)


#
# Helpers
#

FOOTER_VERSION = re.compile(r'\b(?P<version>v\d+)', re.IGNORECASE)

PIN_VERSIONS = {}


def __import_pin_versions():
    for name in importlib.resources.contents(f'{__name__}.parse'):
        if not name.startswith('v'):
            continue
        name = name[:-3] if name.endswith('.py') else name
        PIN_VERSIONS[name] = importlib.import_module(
            f'{__name__}.parse.{name}')


__import_pin_versions()
