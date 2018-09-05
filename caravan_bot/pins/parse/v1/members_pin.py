import discord

from .... import caravan_model
from .... import iteration
from .... import members
from ... import exceptions
from .. import parse_receipts


def populate_model(
        message: discord.Message,
        model: caravan_model.CaravanModel
) -> parse_receipts.MembersParseReceipt:

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

    present_leaders, = iteration.bucket(
        members.gen_members(
            channel=message.channel,
            content=leader_field.value),
        lambda u: isinstance(u, discord.Member))

    present_members, missing_members = iteration.bucket(
        members.gen_caravan_members(
            channel=message.channel,
            content=member_field.value),
        lambda m: isinstance(m.user, discord.Member),
        lambda m: isinstance(m.user, int))

    model.leaders = frozenset(present_leaders)
    model.members = {m.user: m.guests for m in present_members}

    return parse_receipts.MembersParseReceipt(
        missing_members={m.user: m.guests for m in missing_members})
