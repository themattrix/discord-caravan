import dataclasses
import re

from typing import Callable, Iterable

import discord

from . import sanitize

GUESTS_PATTERN = re.compile(
    r'^\+[ \t]*(?P<guests>\d+)$')

USER_WITH_GUESTS_PATTERN = re.compile(
    r'<@!?(?P<id>\d+)>(?:[ \t]*\+(?P<guests>\d+))?')


class InvalidGuestFormat(Exception):
    """Raised if the guest format was unrecognized."""


def gen_users(
        get_user: Callable[[int], discord.User],
        content: str
) -> Iterable[discord.User]:

    it = sanitize.gen_user_ids(content)
    it = (get_user(i) for i in it)
    it = (i for i in it if i is not None)

    yield from it


@dataclasses.dataclass(frozen=True)
class Member:
    user: discord.User
    guests: int


def gen_members(
        get_user: Callable[[int], discord.User],
        content: str
) -> Iterable[discord.User]:

    it = USER_WITH_GUESTS_PATTERN.finditer(content)
    it = (
        Member(
            user=get_user(int(i.group('id'))),
            guests=int(i.group('guests') or 0))
        for i in it)
    it = (i for i in it if i.user is not None)

    yield from it


def get_guest_count(content: str) -> int:
    if not content:
        guests = 0
    else:
        match = GUESTS_PATTERN.match(content)
        if not match:
            raise InvalidGuestFormat()
        guests = int(match.group('guests'))

    return guests
