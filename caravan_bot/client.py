import contextlib
import dataclasses
import functools
import itertools

from typing import Dict, Union, Optional, Pattern

from .log import log, channel_log
from .pins import exceptions
from . import caravan_channel
from . import commands
from . import places
from . import natural_language

import discord


@dataclasses.dataclass
class CaravanClient(discord.Client):
    gyms: places.Places
    server_re: Pattern
    channel_re: Pattern
    channels: Dict[discord.TextChannel, caravan_channel.CaravanChannel] = (
        dataclasses.field(default_factory=dict))

    def __post_init__(self):
        super().__init__()

    async def on_ready(self):
        log.info(f'Logged in as "{self.user.name}" ({self.user.id})')

        for channel in self.get_all_channels():
            await self._init_channel(channel)

        log.info(self._get_all_channels_message())

    async def on_guild_channel_create(self, channel: discord.TextChannel):
        await self._init_channel(channel)

    async def on_guild_channel_delete(self, channel: discord.TextChannel):
        with contextlib.suppress(KeyError):
            self.channels.pop(channel)
            channel_log(channel, 'INFO', 'Channel deleted.')

    async def on_member_remove(self, member: discord.Member):
        for channel, caravan in self.channels.items():
            if member.guild != channel.guild:
                continue
            await caravan.handle_member_remove(user=member)

    async def on_member_ban(
            self,
            guild: discord.Guild,
            user: Union[discord.User, discord.Member]):

        if not isinstance(user, discord.Member):
            # If we receive a User instead of a Member, then the user was
            # banned after leaving the server. In that case, we don't care
            # since by definition they can't be part of a caravan.
            return

        for channel, caravan in self.channels.items():
            if guild != channel.guild:
                continue
            await caravan.handle_member_remove(user=user)

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return  # don't respond to ourselves

        if message.channel not in self.channels:
            return  # only respond in caravan channels

        c_log = functools.partial(channel_log, message.channel)
        c_log('INFO', f'From {message.author.name}: {message.content}')

        try:
            cmd_msg = commands.CommandMessage.from_message(message)
        except (commands.NotACommand, commands.NoSuchCommand):
            return
        except commands.CommandSuggestion as e:
            await message.channel.send(
                f'Did you mean `!{e.suggested_command}`?')
            c_log('INFO', (
                f'Suggesting "!{e.suggested_command}" (score: {e.score}) '
                f'instead of "!{e.given_command}".'))
            return
        else:
            await self.channels[message.channel].handle_command(cmd_msg)

    async def _init_channel(self, channel: discord.TextChannel):
        if not isinstance(channel, discord.TextChannel):
            return  # not a text channel

        if not channel.guild:
            return  # possibly a direct message from someone

        if not self.server_re.match(channel.guild.name):
            return  # does not match given server name pattern

        if not self.channel_re.match(channel.name):
            return  # does not match given channel name pattern

        c_log = functools.partial(channel_log, channel)

        if self.user not in channel.members:
            c_log('WARNING', f'Bot is not a member of this channel.')
            return

        try:
            self.channels[channel] = (
                await caravan_channel.CaravanChannel.from_channel(
                    channel=channel,
                    gyms=self.gyms,
                    bot_user=self.user,
                    get_user=self.get_user_from_id))
        except discord.errors.Forbidden as e:
            c_log('ERROR', f'Ignoring channel. Bot lacking permissions: {e}')
        except exceptions.InvalidPinFormat as e:
            c_log('ERROR', f'Ignoring channel. Invalid pin format: {e}')

    async def get_user_from_id(self, user_id: int) -> Optional[discord.User]:
        return self.get_user(user_id) or await self.get_user_info(user_id)

    def _get_all_channels_message(self) -> str:
        if not self.channels:
            return 'Found 0 caravan channels. Waiting for new ones...'

        p = natural_language.pluralize

        # Sort by guild (server) name, and then by channel name.
        channels = self.channels.keys()
        sorted_channels = sorted(channels, key=lambda i: i.guild.id)
        by_guild = itertools.groupby(sorted_channels, key=lambda i: i.guild.id)
        guilds = (tuple(g) for _, g in by_guild)
        sorted_guilds = sorted(guilds, key=lambda g: g[0].guild.name)
        fully_sorted = (sorted(g, key=lambda c: c.name) for g in sorted_guilds)

        def format_server(guild):
            return f'  {guild[0].guild.name}\n' + '\n'.join(
                format_channel(c) for c in guild)

        def format_channel(channel):
            caravan = self.channels[channel]
            members = caravan.model.total_members
            stops = len(caravan.model.route)
            return (
                f'    → {channel.name} ('
                f'{members} {p("member", members)}, '
                f'{stops} {p("stop", stops)})')

        return (
            f'Monitoring {len(self.channels)} caravan '
            f'{p("channel", self.channels)}:\n' + '\n'.join(
                format_server(g) for g in fully_sorted))
