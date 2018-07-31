import contextlib
import os
import logging
import pathlib
import re
import sys

from typing import Iterable, Generator

import discord

from .log import log
from . import places
from . import pins
from . import sanitize


COMMAND_PATTERN = re.compile(
    r'^\s*!+\s*(?P<command>.*)')


class CaravanClient(discord.Client):
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

        command_type = match.group('command').strip().split()[0].casefold()

        if command_type in {'leader', 'leaders'}:
            await self._on_leaders_command(
                message=message,
                full_command=match.group('command'))

        elif command_type == 'route':
            await self._on_route_command(
                message=message)

        elif command_type in {'start', 'stop', 'resume', 'reset'}:
            await self._on_mode_command(
                message=message,
                command=command_type)

        elif command_type in {'next', 'skip'}:
            await self._on_advance_command(
                message=message,
                command_type=command_type,
                full_command=match.group('command'))

    async def _on_leaders_command(self, message, full_command):
        pin = await self._get_members_pin(message.channel)

        # noinspection PyProtectedMember
        is_authorized = (
            message.author.permissions_in(message.channel).administrator or
            message.author._user in pin.leaders)

        if not is_authorized:
            await message.channel.send(
                ':warning: Only admins and caravan leaders are allowed to '
                'delegate caravan leaders! {}'.format(
                    'No leaders are currently set.' if not pin.leaders else (
                        'The current leader{} {}.'.format(
                            ' is' if len(pin.leaders) == 1 else 's are ',
                            pin.leaders_list_string))))
            return

        it = sanitize.gen_user_ids(full_command)
        it = self._ids_to_users(it)
        users = tuple(it)

        if not users:
            await message.channel.send(
                'Usage:\n'
                '```\n'
                '!leaders @user [@user]...\n'
                '```')
            return

        pin = pin.with_updated_leaders(leaders=users)

        await pin.flush()
        await message.channel.send(
            'Updated the leader{} to {}!'.format(
                '' if len(users) == 1 else 's',
                pin.leaders_list_string))

    async def _on_route_command(self, message):
        is_leader = await self._message_author_is_leader(message)

        try:
            route = pins.get_route(
                route=message.content,
                all_places=self.gyms,
                fuzzy=True)
            gyms_not_found = ()
        except pins.UnknownRouteLocations as e:
            route = ()
            gyms_not_found = e.unknown_names

        if not is_leader and (route or gyms_not_found):
            await message.channel.send(
                ':warning: Only caravan leaders are allowed to set a route! '
                'You may query the route with `!route`.')
            return

        if gyms_not_found:
            await message.channel.send(
                ':warning: Failed to find the following gym{}: {}'.format(
                    '' if len(gyms_not_found) == 1 else 's',
                    ', '.join(f'"{g}"' for g in gyms_not_found)))
            return

        pin = await self._get_route_pin(message.channel)

        if route:
            pin.reroute(route=route)

            await pin.flush()
            await message.channel.send(
                f'Updated the route! ({len(route)} stops)')
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

    async def _on_mode_command(self, message, command):
        if not await self._message_author_is_leader(message):
            await message.channel.send(
                f':warning: Only caravan leaders are allowed to {command} the '
                f'caravan!')
            return

        pin = await self._get_route_pin(message.channel)

        if command == 'resume':
            command = 'start'
        try:
            getattr(pin, command)()
        except pins.CaravanStatusAlreadyCorrect as e:
            await message.channel.send(str(e))
            return

        await pin.flush()
        await message.channel.send(pin.status_string)

    async def _on_advance_command(self, message, command_type, full_command):
        if not await self._message_author_is_leader(message):
            await message.channel.send(
                ':warning: Only caravan leaders are allowed to advance the '
                'caravan!')
            return

        pin = await self._get_route_pin(message.channel)

        if pin.status != pins.CaravanStatus.ACTIVE:
            await message.channel.send(
                ':warning: Caravan not in active mode, so it can\'t be '
                'advanced! (First start the caravan with `!start`.)')
            return

        try:
            if command_type == 'next':
                pin.advance()
            else:
                try:
                    reason = full_command.split(maxsplit=1)[1]
                except IndexError:
                    reason = None
                pin.skip(reason=reason)

        except pins.RouteExhausted:
            await message.channel.send(  # TODO: suggest !add'ing more stops
                ':warning: Can\'t advance the caravan; no more stops!')
            return

        await pin.flush()

        try:
            next_stop = pin.remaining_route[0]
            # Just output the place name and let the Professor Willow Bot
            # provide the details.
            await message.channel.send(next_stop.place.name)
        except IndexError:
            await message.channel.send(
                'Congratulations! Route complete! :first_place:')

    async def _init_channel(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return  # not a text channel

        if not is_caravan_channel(channel):
            return  # not a caravan channel

        self.caravan_channels.add(channel)

        if not await self._get_route_pin(channel):
            await pin_message(await channel.send(
                **pins.RoutePin(channel.name).content_and_embed))

        if not await self._get_members_pin(channel):
            await pin_message(await channel.send(
                **pins.MembersPin().content_and_embed))

    async def _get_route_pin(self, channel) -> pins.RoutePin:
        for p in await channel.pins():
            if p.author == self.user:
                with contextlib.suppress(pins.RoutePinFormatException):
                    return pins.RoutePin.from_message(
                        message=p,
                        all_places=self.gyms)

    async def _get_members_pin(self, channel) -> pins.MembersPin:
        for p in await channel.pins():
            if p.author == self.user:
                with contextlib.suppress(pins.MembersPinFormatException):
                    return pins.MembersPin.from_message(
                        message=p,
                        gen_users=self._ids_to_users)

    async def _message_author_is_leader(self, message) -> bool:
        # noinspection PyProtectedMember
        return message.author._user in (
            (await self._get_members_pin(message.channel)).leaders)

    def _ids_to_users(
            self,
            ids: Iterable[str]
            ) -> Generator[discord.User, None, None]:
        it = (self.get_user(i) for i in ids)
        it = (i for i in it if i is not None)
        yield from it


def is_caravan_channel(channel):
    return 'caravan' in channel.name.casefold()


async def pin_message(message):
    # noinspection PyProtectedMember
    await message.channel._state.http.pin_message(
        channel_id=message.channel.id,
        message_id=message.id)


def main():
    client = CaravanClient(
        gyms=places.Places.from_json(pathlib.Path(sys.argv[1])))
    client.run(os.environ['DISCORD_BOT_TOKEN'])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
