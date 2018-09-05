from typing import Tuple, Optional

import discord

from .... import caravan_model
from .... import places
from .. import parse_receipts
from . import route_pin
from . import members_pin


def populate_model(
        model: caravan_model.CaravanModel,
        bot_pins: Tuple[discord.Message],
        all_places: places.Places
        ) -> Optional[parse_receipts.MembersParseReceipt]:
    """
    Populate the model with whatever this message contains.
    """
    member_parse_receipt = None

    for p in bot_pins:
        if 'Route' in p.embeds[0].footer.text:
            route_pin.populate_model(
                message=p,
                model=model,
                all_places=all_places)
        else:
            member_parse_receipt = members_pin.populate_model(
                message=p,
                model=model)

    return member_parse_receipt
