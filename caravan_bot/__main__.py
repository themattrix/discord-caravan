import contextlib
import os
import logging
import pathlib
import re
import sys

import discord

from .log import log
from . import places
from . import pins
from . import sanitize


COMMAND_PATTERN = re.compile(
    r'^\s*!+\s*(?P<command>.*)')


class MyClient(discord.Client):
    def __init__(self, gyms):
        super().__init__()
        self.gyms = gyms
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

        match = COMMAND_PATTERN.search(message.content)
        if not match:
            return  # not a command

        if match.group('command').strip().casefold() == 'route':
            gyms_not_found = []

            def gen_gyms(names):
                for n in names:
                    try:
                        yield self.gyms.get_fuzzy(fuzzy_name=n)
                    except places.PlaceNotFoundException:
                        gyms_not_found.append(n)

            gyms = sanitize.clean_route(message.content)
            gyms = tuple(gen_gyms(gyms))

            if gyms_not_found:
                await message.channel.send(
                    'Failed to find the following gym{}: {}'.format(
                        '' if len(gyms_not_found) == 1 else 's',
                        ', '.join(f'"{g}"' for g in gyms_not_found)))
                return

            pin = await self._get_route_pin(message.channel)

            if gyms:
                pin = pin.with_updated_route(route=gyms)

                await pin.message.edit(**pin.content_and_embed)
                await message.channel.send(
                    f'Updated the route! ({len(gyms)} stops)')
            else:
                if pin.route:
                    await message.channel.send(
                        f'{pin.route_header_string}\n'
                        f'{pin.route_string}')
                else:
                    await message.channel.send(
                        'Usage:\n'
                        '```\n'
                        '!route\n'
                        '- <gym-name>\n'
                        '- <gym-name>\n'
                        '- ...\n'
                        '```')

    async def _init_channel(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return  # not a text channel

        if not is_caravan_channel(channel):
            return  # not a caravan channel

        self.caravan_channels.add(channel)

        if await self._get_route_pin(channel):
            return  # already has a pinned message

        welcome = await channel.send(
            **pins.RoutePin(channel.name).content_and_embed)

        # noinspection PyProtectedMember
        await channel._state.http.pin_message(
            channel_id=channel.id,
            message_id=welcome.id)

    async def _get_route_pin(self, channel):
        for p in await channel.pins():
            if p.author == self.user:
                with contextlib.suppress(pins.UnknownRoutePinFormatException):
                    return pins.RoutePin.from_message(
                        message=p,
                        places=self.gyms)


def is_caravan_channel(channel):
    return 'caravan' in channel.name.casefold()


def main():
    client = MyClient(gyms=places.Places.from_json(pathlib.Path(sys.argv[1])))
    client.run(os.environ['DISCORD_BOT_TOKEN'])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
