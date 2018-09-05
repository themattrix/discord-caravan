import dataclasses
import re

from typing import Iterable, Union

import discord

from . import sanitize

GUESTS_PATTERN = re.compile(
    r'^\+[ \t]*(?P<guests>\d+)$')

USER_WITH_GUESTS_PATTERN = re.compile(
    r'<@!?(?P<id>\d+)>(?:[ \t]*\+(?P<guests>\d+))?')


class InvalidGuestFormat(Exception):
    """Raised if the guest format was unrecognized."""


def gen_members(
        channel: discord.TextChannel,
        content: str,
) -> Iterable[Union[discord.Member, int]]:

    it = sanitize.gen_user_ids(content)
    it = (channel.guild.get_member(i) or i for i in it)
    it = (i for i in it if i is not None)

    yield from it


@dataclasses.dataclass(frozen=True)
class CaravanMember:
    user: Union[discord.Member, int]
    guests: int


def gen_caravan_members(
        channel: discord.TextChannel,
        content: str,
) -> Iterable[CaravanMember]:

    for m in USER_WITH_GUESTS_PATTERN.finditer(content):
        user_id = int(m.group('id'))
        guests = int(m.group('guests') or 0)
        member = channel.guild.get_member(user_id)
        yield CaravanMember(user=member or user_id, guests=guests)


def get_guest_count(content: str) -> int:
    if not content:
        guests = 0
    else:
        match = GUESTS_PATTERN.match(content)
        if not match:
            raise InvalidGuestFormat()
        guests = int(match.group('guests'))

    return guests
