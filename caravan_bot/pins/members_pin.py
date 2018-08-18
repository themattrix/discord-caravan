import dataclasses

from typing import Callable, Dict

import discord

from .. import caravan_model
from .. import natural_language
from . import base_pin


class InvalidMembersPinFormat(Exception):
    """Raised if the message cannot be parsed."""


CARAVAN_SIZE_WARNING_THRESHOLD = 16


@dataclasses.dataclass
class MembersPin(base_pin.BasePin):
    update_for = frozenset({
        caravan_model.LeaderUpdateReceipt,
        caravan_model.MemberUpdateReceipt,
    })

    def content_and_embed(self, model: caravan_model.CaravanModel) -> Dict:
        return content_and_embed(model)


def populate_model(
        message: discord.Message,
        model: caravan_model.CaravanModel,
        gen_users: Callable,
        gen_members: Callable):

    if not message.embeds:
        raise InvalidMembersPinFormat('Missing embeds!')

    if len(message.embeds) != 1:
        raise InvalidMembersPinFormat(
            f'Expected 1 embed but found {len(message.embeds)}.')

    embed = message.embeds[0]

    if len(embed.fields) != 2:
        raise InvalidMembersPinFormat(
            f'Expected 2 embed fields but found {len(embed.fields)}.')

    leader_field, member_field = embed.fields

    model.leaders = frozenset(gen_users(leader_field.value))
    model.members = {m.user: m.guests for m in gen_members(member_field.value)}


def content_and_embed(model: caravan_model.CaravanModel) -> Dict:
    p = natural_language.pluralize
    j = natural_language.join

    embed = discord.Embed(title='Caravan Members')

    embed.add_field(
        name=f'{p("Leader", model.leaders)} :crown:',
        value=(
            '_No leaders set! An admin may set the leader(s) with `!leaders`._'
            if not model.leaders else j(
                u.mention for u in sorted(model.leaders, key=lambda u: u.id))),
        inline=False)

    embed.add_field(
        name=f'{p("Member", model.members)} :busts_in_silhouette:',
        value=(
            '_No members! Be the first to `!join`._'
            if not model.members else j(
                format_member(u, model.members[u])
                for u in sorted(model.members, key=lambda u: u.id))),
        inline=False)

    return {
        'content': (
            None if len(model.members) <= CARAVAN_SIZE_WARNING_THRESHOLD else (
                f'_Nearing a full caravan ({len(model.members)} members)! '
                f'Consider splitting this caravan into multiples._ '
                f':arrow_up_down:')),
        'embed': embed,
    }


def format_member(user: discord.User, guests: int) -> str:
    return user.mention if not guests else f'{user.mention} +{guests}'
