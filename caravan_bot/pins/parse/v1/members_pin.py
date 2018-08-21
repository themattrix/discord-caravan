from typing import Callable

import discord

from .... import caravan_model
from ... import exceptions


def populate_model(
        message: discord.Message,
        model: caravan_model.CaravanModel,
        gen_users: Callable,
        gen_members: Callable):

    if not message.embeds:
        raise exceptions.InvalidPinFormat('Missing embeds!')

    if len(message.embeds) != 1:
        raise exceptions.InvalidPinFormat(
            f'Expected 1 embed but found {len(message.embeds)}.')

    embed = message.embeds[0]

    if len(embed.fields) != 2:
        raise exceptions.InvalidPinFormat(
            f'Expected 2 embed fields but found {len(embed.fields)}.')

    leader_field, member_field = embed.fields

    model.leaders = frozenset(gen_users(leader_field.value))
    model.members = {m.user: m.guests for m in gen_members(member_field.value)}
