import contextlib
import os
import logging
import pathlib
import re
import sys

from typing import Iterable, Generator

import discord

from .log import log
from . import natural_language
from . import places
from . import pins
from . import sanitize


COMMAND_PATTERN = re.compile(
    r'^\s*!+[ \t]*(?P<command>\w+)(?:[ \t]+(?P<args>.*))?')


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

        command, args = match.group('command'), match.group('args')
        command = command.casefold()

        if command in {'leader', 'leaders'}:
            await self._on_leaders_command(message=message, args=args)

        elif command == 'route':
            await self._on_route_command(message=message)

        elif command in {'start', 'stop', 'resume', 'reset'}:
            await self._on_mode_command(message=message, command=command)

        elif command in {'next', 'skip'}:
            await self._on_advance_command(
                message=message,
                command=command,
                args=args)

        elif command in {'add', 'append'}:
            await self._on_add_command(
                message=message,
                command=command,
                args=args)

    async def _on_leaders_command(self, message, args):
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

        it = sanitize.gen_user_ids(args)
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
                f'New route pinned! ({len(route)} stops)\n'
                f'_You may change it again with `!route` or add stops with '
                f'`!add`._')
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
        except pins.CaravanModeAlreadyCorrect as e:
            await message.channel.send(str(e))
            return

        await pin.flush()
        await message.channel.send(
            pin.status_string.replace('Status', 'Caravan'))

        if command == 'start':
            try:
                await message.channel.send(pin.remaining_route[0].place.name)
            except IndexError:
                await message.channel.send(
                    ':warning: The caravan is active but no route is set! '
                    '_Set a route with `!route` or add stops with `!add`._')

        elif command == 'stop':
            await message.channel.send(get_route_statistics_message(
                stats=pin.route_statistics))

    async def _on_advance_command(self, message, command, args):
        if not await self._message_author_is_leader(message):
            await message.channel.send(
                ':warning: Only caravan leaders are allowed to advance the '
                'caravan!')
            return

        pin = await self._get_route_pin(message.channel)

        if pin.mode != pins.CaravanMode.ACTIVE:
            await message.channel.send(
                ':warning: Caravan not in active mode, so it can\'t be '
                'advanced! _First start the caravan with `!start`._')
            return

        try:
            if command == 'next':
                pin.advance()
            else:
                pin.skip(reason=args)

        except pins.RouteExhausted:
            await message.channel.send(
                ':warning: Can\'t advance the caravan; no more stops! _Try '
                'adding stops with `!add`._')
            return

        await pin.flush()

        try:
            next_stop = pin.remaining_route[0]
            # Just output the place name and let the Professor Willow Bot
            # provide the details.
            await message.channel.send(next_stop.place.name)

        except IndexError:
            await message.channel.send(
                'Congratulations — route **complete**! :first_place:\n'
                '_Feel free to `!add` additional stops!_\n')

    async def _on_add_command(self, message, command, args):
        if not await self._message_author_is_leader(message):
            await message.channel.send(
                ':warning: Only caravan leaders are allowed to modify the '
                'route!')
            return

        pin = await self._get_route_pin(message.channel)

        append = command == 'append' or pin.mode == pins.CaravanMode.PLANNING

        try:
            route = pins.get_route(
                route=f'- {args}' if args else message.content,
                all_places=self.gyms,
                fuzzy=True)

            pin.add_route(route=route, append=append)

        except pins.EmptyRouteException:
            await message.channel.send(
                f'Usages:\n'
                f'```\n'
                f'!{command} <gym-name>\n'
                f'\n'
                f'!{command}\n'
                f'- <gym-name>\n'
                f'- <gym-name>\n'
                f'- ...\n'
                f'```')
            return

        await pin.flush()
        await message.channel.send(
            'Added {} stop{} to the route!'.format(
                len(route), '' if len(route) == 1 else 's'))

        if not append and pins.CaravanMode.ACTIVE:
            await message.channel.send(pin.remaining_route[0].place.name)

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


def get_route_statistics_message(stats):
    def gen_msg():
        yield 'Visited **{}** gym{}'.format(
            stats.stops_visited,
            '' if stats.stops_visited == 1 else 's')
        if stats.stops_skipped:
            yield 'skipped **{}** gym{}'.format(
                stats.stops_skipped,
                '' if stats.stops_skipped == 1 else 's')
        if stats.stops_remaining:
            yield '**{}** gym{} unvisited'.format(
                stats.stops_remaining,
                '' if stats.stops_remaining == 1 else 's')

    return '_{}._'.format(natural_language.join(gen_msg()))


def main():
    client = CaravanClient(
        gyms=places.Places.from_json(pathlib.Path(sys.argv[1])))
    client.run(os.environ['DISCORD_BOT_TOKEN'])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
