import contextlib
import os
import logging
import pathlib
import re
import sys

from typing import Iterable, Generator

import discord

from .log import log
from .pins import route_pin
from .pins import members_pin
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
        self.caravan_pins = {}

    async def on_ready(self):
        log.info(f'Logged in as "{self.user.name}" ({self.user.id})')

        for c in self.get_all_channels():
            await self._init_channel(c)

        log.info(f'Found {len(self.caravan_pins)} caravan channel(s)')

    async def on_guild_channel_create(self, channel):
        await self._init_channel(channel)

    async def on_guild_channel_delete(self, channel):
        with contextlib.suppress(KeyError):
            self.caravan_pins.pop(channel)
            log.info(
                f'Removed caravan channel "{channel}" from server '
                f'"{channel.guild.name}"')

    async def on_message(self, message):
        # don't respond to ourselves
        if message.author == self.user:
            return

        # only respond in caravan channels
        if message.channel not in self.caravan_pins:
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
        pin = self.caravan_pins[message.channel].members

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

        pin.update_leaders(leaders=users)

        await pin.flush()
        await message.channel.send(
            'Updated the leader{} to {}!'.format(
                '' if len(users) == 1 else 's',
                pin.leaders_list_string))

    async def _on_route_command(self, message):
        is_leader = self._message_author_is_leader(message)

        try:
            route = route_pin.get_route(
                route=message.content,
                all_places=self.gyms,
                fuzzy=True)
            gyms_not_found = ()
        except route_pin.UnknownRouteLocations as e:
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

        pin = self.caravan_pins[message.channel].route

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
        if not self._message_author_is_leader(message):
            await message.channel.send(
                f':warning: Only caravan leaders are allowed to {command} the '
                f'caravan!')
            return

        pin = self.caravan_pins[message.channel].route

        if command == 'resume':
            command = 'start'
        try:
            getattr(pin, command)()
        except route_pin.CaravanModeAlreadyCorrect as e:
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
        if not self._message_author_is_leader(message):
            await message.channel.send(
                ':warning: Only caravan leaders are allowed to advance the '
                'caravan!')
            return

        pin = self.caravan_pins[message.channel].route

        if pin.mode != route_pin.CaravanMode.ACTIVE:
            await message.channel.send(
                ':warning: Caravan not in active mode, so it can\'t be '
                'advanced! _First start the caravan with `!start`._')
            return

        try:
            if command == 'next':
                pin.advance()
            else:
                pin.skip(reason=args)

        except route_pin.RouteExhausted:
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
                'Congratulations — **route complete**! :first_place:\n'
                '_Feel free to `!add` additional stops!_\n')

    async def _on_add_command(self, message, command, args):
        if not self._message_author_is_leader(message):
            await message.channel.send(
                ':warning: Only caravan leaders are allowed to modify the '
                'route!')
            return

        pin = self.caravan_pins[message.channel].route

        append = (
            command == 'append' or pin.mode == route_pin.CaravanMode.PLANNING)

        try:
            route = route_pin.get_route(
                route=f'- {args}' if args else message.content,
                all_places=self.gyms,
                fuzzy=True)

            pin.add_route(route=route, append=append)

        except route_pin.EmptyRouteException:
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

        except route_pin.UnknownRouteLocations as e:
            await message.channel.send(
                ':warning: Failed to find the following gym{}: {}'.format(
                    '' if len(e.unknown_names) == 1 else 's',
                    ', '.join(f'"{g}"' for g in e.unknown_names)))
            return

        await pin.flush()
        await message.channel.send(
            'Added {} stop{} to the route!'.format(
                len(route), '' if len(route) == 1 else 's'))

        if not append and route_pin.CaravanMode.ACTIVE:
            await message.channel.send(pin.remaining_route[0].place.name)

    async def _init_channel(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return  # not a text channel

        if not is_caravan_channel(channel):
            return  # not a caravan channel

        self.caravan_pins[channel] = await self._get_pins(channel)
        await self.caravan_pins[channel].ensure_pinned(channel)

    def _message_author_is_leader(self, message) -> bool:
        # noinspection PyProtectedMember
        return message.author._user in (
            self.caravan_pins[message.channel].members.leaders)

    def _ids_to_users(
            self,
            ids: Iterable[str]
            ) -> Generator[discord.User, None, None]:
        it = (self.get_user(i) for i in ids)
        it = (i for i in it if i is not None)
        yield from it

    async def _get_pins(self, channel) -> pins.Pins:
        members, route = None, None

        for p in await channel.pins():
            if p.author != self.user:
                continue
            if 'Leader' in p.content:
                members = members_pin.MembersPin.from_message(
                    message=p,
                    gen_users=self._ids_to_users)
            else:
                route = route_pin.RoutePin.from_message(
                    message=p,
                    all_places=self.gyms)

        return pins.Pins(
            route=route or route_pin.RoutePin(channel_name=channel.name),
            members=members or members_pin.MembersPin())




def is_caravan_channel(channel):
    return 'caravan' in channel.name.casefold()


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
