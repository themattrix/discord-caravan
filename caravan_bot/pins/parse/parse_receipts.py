import dataclasses

from typing import Dict, Union

import discord


@dataclasses.dataclass(frozen=True)
class MembersParseReceipt:
    missing_members: Dict[Union[discord.User, int], int]
