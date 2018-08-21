import contextlib
import dataclasses
import functools
import itertools
import re

from typing import Dict

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
    # noinspection PyUnresolvedReferences
    server_re: re.Pattern
    # noinspection PyUnresolvedReferences
    channel_re: re.Pattern
    channels: Dict[discord.TextChannel, caravan_channel.CaravanChannel] = (
        dataclasses.field(default_factory=dict))

    def __post_init__(self):
        super().__init__()

    async def on_ready(self):
        log.info(f'Logged in as "{self.user.name}" ({self.user.id})')

        for channel in self.get_all_channels():
            await self._init_channel(channel)

        log.info(self._get_all_channels_message())

    async def on_guild_channel_create(self, channel):
        await self._init_channel(channel)

    async def on_guild_channel_delete(self, channel):
        with contextlib.suppress(KeyError):
            self.channels.pop(channel)
            channel_log(channel, 'INFO', 'Channel deleted.')

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
                    get_user=self.get_user,
                    bot_user=self.user))
        except discord.errors.Forbidden as e:
            c_log('ERROR', f'Ignoring channel. Bot lacking permissions: {e}')
        except exceptions.InvalidPinFormat as e:
            c_log('ERROR', f'Ignoring channel. Invalid pin format: {e}')

    def _get_all_channels_message(self) -> str:
        if not self.channels:
            return 'Found 0 caravan channels.'

        it = self.channels.keys()
        it = sorted(it, key=lambda i: i.guild.id)
        it = itertools.groupby(it, key=lambda i: i.guild.id)
        it = (tuple(g) for _, g in it)
        it = sorted(it, key=lambda g: g[0].guild.name)
        it = (sorted(g, key=lambda c: c.name) for g in it)

        return 'Found {} caravan {}:\n{}'.format(
            len(self.channels),
            natural_language.pluralize('channel', self.channels),
            '\n'.join(
                f'  {g[0].guild.name}\n' + '\n'.join(
                    f'    → {c.name}' for c in g)
                for g in it))
