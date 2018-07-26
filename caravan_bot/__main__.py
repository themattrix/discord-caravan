import asyncio
import contextlib
import os
import logging

import discord


log = logging.getLogger('bot')


class MyClient(discord.Client):
    def __init__(self):
        super().__init__()
        self.caravan_channels = set()

    async def on_ready(self):
        log.info(f'Logged in as "{self.user.name}" ({self.user.id})')

        for c in self.get_all_channels():
            await self._init_channel(c)

        log.info(f'Found {len(self.caravan_channels)} caravan channel(s)')

    async def on_guild_channel_create(self, channel):
        await self._init_channel(channel)

    async def on_guild_channel_delete(self, channel):
        with contextlib.suppress(KeyError):
            self.caravan_channels.remove(channel)
            log.info(
                f'Removed caravan channel "{channel}" from server '
                f'"{channel.guild.name}"')

    async def on_message(self, message):
        # don't respond to ourselves
        if message.author == self.user:
            return

        # only respond in caravan channels
        if message.channel not in self.caravan_channels:
            return

        if message.content.startswith('!test'):
            counter = 0
            tmp = await message.channel.send('Calculating messages...')
            async for msg in message.channel.history(limit=100):
                if msg.author == message.author:
                    counter += 1
            await tmp.edit(content=f'You have {counter} messages.')

        elif message.content.startswith('!sleep'):
            with message.channel.typing():
                await asyncio.sleep(5.0)
                await message.channel.send('Done sleeping.')

    async def _init_channel(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return  # not a text channel

        if not is_caravan_channel(channel):
            return  # not a caravan channel

        self.caravan_channels.add(channel)

        if any(p.author == self.user for p in await channel.pins()):
            return  # already has a pinned message

        welcome = await channel.send(
            f':blue_car: __**{channel.name}**__ :red_car:')

        # noinspection PyProtectedMember
        await channel._state.http.pin_message(
            channel_id=channel.id,
            message_id=welcome.id)


def is_caravan_channel(channel):
    return 'caravan' in channel.name.casefold()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    client = MyClient()
    client.run(os.environ['DISCORD_BOT_TOKEN'])
