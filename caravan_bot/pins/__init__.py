import dataclasses

import discord

from . import route_pin
from . import members_pin


@dataclasses.dataclass
class Pins:
    route: route_pin.RoutePin
    members: members_pin.MembersPin

    async def ensure_pinned(self, channel: discord.TextChannel):
        await self.route.ensure_post(channel=channel)
        await self.members.ensure_post(channel=channel)
        await self.members.ensure_pin()
        await self.route.ensure_pin()
