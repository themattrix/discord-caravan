import re

from typing import Callable, Iterable, Optional

import discord

from .. import natural_language
from .. import sanitize
from . import base_pin

MEMBERS_PATTERN = re.compile(
    r'.*Leader.*\n'
    r'(?:'
    r'  _No.*|'           # no leaders set
    r'  (?P<leaders>.*)'  # leaders set 
    r')',
    re.IGNORECASE | re.VERBOSE)


class MembersPinFormatException(Exception):
    """Raised if the message cannot be parsed."""


class MembersPin(base_pin.BasePin):
    @classmethod
    def from_message(cls, message: discord.Message, gen_users: Callable):
        match = MEMBERS_PATTERN.search(message.content)
        if not match:
            raise MembersPinFormatException('Unrecognized members format!')

        leaders_string = match.group('leaders') or ''

        return cls(
            leaders=gen_users(sanitize.gen_user_ids(leaders_string)),
            message=message)

    def __init__(
            self,
            leaders: Iterable[discord.User] = (),
            message: Optional[discord.Message] = None):
        super().__init__()
        self.leaders = frozenset(leaders)
        self.message = message

    def update_leaders(self, leaders: Iterable[discord.User]):
        self.leaders = frozenset(leaders)

    @property
    def leaders_header_string(self):
        return '**Caravan Leader{}**{}'.format(
            '' if len(self.leaders) == 1 else 's',
            '' if self.leaders else ' — _set with `!leaders`_')

    @property
    def sorted_leaders(self):
        return sorted(self.leaders, key=lambda u: u.id)

    @property
    def leaders_list_string(self):
        return natural_language.join(u.mention for u in self.sorted_leaders)

    @property
    def leaders_string(self):
        return '_No leaders set!_' if not self.leaders else (
            self.leaders_list_string)

    @property
    def content_and_embed(self):
        return {
            'content': (
                f'{self.leaders_header_string}\n'
                f'{self.leaders_string}'),
        }
