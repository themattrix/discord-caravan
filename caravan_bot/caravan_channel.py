import dataclasses
import functools

from typing import Callable, Iterable, Tuple, Optional

import discord
import inflection

from .roles import Role
from .pins import init_pins
from .pins.format import base_pin
from . import caravan_model
from . import commands
from . import members
from . import natural_language
from . import places
from . import route


class InvalidCommandArgs(Exception):
    """Raised if the command syntax is invalid."""


@dataclasses.dataclass
class CaravanChannel:
    channel: discord.TextChannel
    model: caravan_model.CaravanModel
    pins: Tuple[base_pin.BasePin, ...]
    get_user: Callable[[int], discord.User]
    gyms: places.Places

    @classmethod
    async def from_channel(
            cls,
            channel: discord.TextChannel,
            gyms: places.Places,
            get_user: Callable[[int], discord.User],
            bot_user: discord.User
    ) -> 'CaravanChannel':

        # Create an empty model to be populated as the pins are parsed.
        model = caravan_model.CaravanModel(channel=channel)

        return cls(
            channel=channel,
            model=model,
            pins=await init_pins(
                model=model,
                channel=channel,
                bot_user=bot_user,
                all_places=gyms,
                get_user=get_user),
            get_user=get_user,
            gyms=gyms)

    async def info(self, msg):
        if msg:
            await self.channel.send(msg)

    async def warn(self, msg):
        if msg:
            await self.channel.send(f':warning: {msg}')

    async def handle_command(self, cmd_msg: commands.CommandMessage):
        command = commands.commands[cmd_msg.name]
        # noinspection PyProtectedMember
        author_roles = frozenset(self.model.gen_roles(
            cmd_msg.message.author._user))

        if not author_roles & command.allowed_roles:
            await self.warn(
                'Only {who} are able to {what}!'.format(
                    who=natural_language.join(
                        inflection.pluralize(r.name.lower())
                        for r in command.allowed_roles),
                    what=command.description.rstrip('.').lower()))
            return

        try:
            receipt = await command.handler(self, cmd_msg)
        except InvalidCommandArgs as e:
            await self.warn(
                f'{e}\n'
                f'\nUsage:\n'
                f'```\n'
                f'{command.usage}\n'
                f'```')
        except caravan_model.RouteNotUpdated:
            await self.info(
                f'No change to existing {len(self.model.route)}-gym route! '
                f':map:')
        except caravan_model.DuplicatePlacesException as e:
            await self.warn(
                'The following {} duplicated: {}'.format(
                    'gyms is' if len(e.duplicate_places) == 1 else 'gyms are',
                    natural_language.join(
                        f'**{p.name}**' for p in e.duplicate_places)))
        except route.UnknownPlaceNames as e:
            await self.warn(
                'The following {} not recognized: {}'.format(
                    'gym is' if len(e.unknown_names) == 1 else 'gyms are',
                    natural_language.join(
                        f'**{u}**' for u in e.unknown_names)))
        else:
            if receipt is not None:
                # update pins
                for p in self.pins:
                    await p.update(receipt=receipt, model=self.model)

                # reply to user so they know the command was processed
                for r in user_responses(receipt):
                    await self.info(r)

    @commands.register(
        'help',
        description='Display the help for all commands or a specific command.',
        usage='!{cmd} [command]'
    )
    async def _help(self, cmd_msg: commands.CommandMessage):
        # noinspection PyProtectedMember
        user_roles = frozenset(
            self.model.gen_roles(cmd_msg.message.author._user))

        j = natural_language.join

        def roles(role_iter: Iterable[Role], markdown=lambda x: x):
            it = (r.name.casefold() for r in role_iter)
            it = sorted(it)
            it = (markdown(r) for r in it)
            return j(it)

        if not cmd_msg.args:
            def gen_help_lines():
                for cmd in commands.unique_commands:
                    if not cmd.allowed_roles & user_roles:
                        continue  # only display help for user's roles
                    yield (
                        f'`!{cmd.preferred}` — '
                        f'{cmd.description} _({roles(cmd.allowed_roles)})_')

            display_roles = user_roles - frozenset({Role.ANYONE})

            await self.info(
                f'{cmd_msg.message.author.mention}, your caravan '
                f'{"role is" if len(display_roles) == 1 else "roles are"} '
                f'{roles(display_roles, lambda x: f"**{x}**")}. '
                f'You may use the following commands:\n' +
                '\n'.join(gen_help_lines()))
        else:
            def gen_help_lines():
                try:
                    cmd = commands.commands[commands.get_command_name(
                        cmd_msg.args.lstrip('!').casefold())]
                except commands.NoSuchCommand:
                    pass  # do nothing; might be intended for another bot
                except commands.CommandSuggestion as e:
                    yield f'_Did you mean `!help {e.suggested_command}`?_'
                else:
                    # The "anyone" role is implied in this context.
                    yield f'{cmd.description} _({roles(cmd.allowed_roles)})_'
                    yield '```'
                    yield cmd.usage
                    yield '```'

            await self.info('\n'.join(gen_help_lines()))

    @commands.register(
        'leader', 'leaders',
        description='Set the caravan leader or leaders.',
        usage='!{cmd} @user [@user]...',
        allowed_roles={Role.ADMIN, Role.LEADER},
        preferred='leaders'
    )
    async def _leaders(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.LeaderUpdateReceipt]:

        users = tuple(members.gen_users(
            get_user=self.get_user, content=cmd_msg.args))
        if not users:
            raise InvalidCommandArgs('You must specify at least one leader.')
        try:
            return self.model.set_leaders(leaders=users)
        except caravan_model.LeadersNotUpdated:
            await self.info(
                f'No change in caravan leadership. Current '
                f'{leaders_msg(self.model.leaders, ": ")}. :crown:')

    @commands.register(
        'route',
        description='Set the caravan route.',
        usage=(
            '!{cmd}\n'
            '- <gym>\n'
            '- <gym>\n'
            '- ...\n'),
        allowed_roles={Role.LEADER}
    )
    async def _route(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.RouteUpdateReceipt]:
        try:
            return self.model.set_route(new_route=(
                s.place for s in route.get_caravan_route(
                    content=cmd_msg.args,
                    all_places=self.gyms,
                    fuzzy=True)))
        except caravan_model.EmptyRouteException:
            raise InvalidCommandArgs(
                'You must specify at least one gym in the route; preferably '
                'more!')

    @commands.register(
        'start', 'resume',
        description='Start or resume the caravan.',
        allowed_roles={Role.LEADER},
        preferred='start'
    )
    async def _start(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.ModeUpdateReceipt]:
        try:
            return self.model.start()
        except caravan_model.ModeNotUpdated:
            await self.info(
                'The caravan has already been started!')

    @commands.register(
        'stop', 'done',
        description='Stop the caravan.',
        allowed_roles={Role.LEADER},
        preferred='stop'
    )
    async def _stop(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.ModeUpdateReceipt]:
        try:
            return self.model.stop()
        except caravan_model.ModeNotUpdated:
            await self.info(
                'The caravan is already _not_ active!')

    @commands.register(
        'reset',
        description='Reset the caravan.',
        allowed_roles={Role.LEADER}
    )
    async def _reset(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.ModeUpdateReceipt]:
        try:
            return self.model.reset()
        except caravan_model.ModeNotUpdated:
            await self.info(
                'The caravan is already _not_ active!')

    @commands.register(
        'next',
        description='Advance the caravan to the next gym.',
        allowed_roles={Role.LEADER}
    )
    async def _next(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.RouteAdvancedReceipt]:
        try:
            return self.model.advance()
        except caravan_model.RouteNotActive:
            await self.warn(
                'The caravan is not in active mode, so it can\'t be '
                'advanced!\n'
                '_First start the caravan with `!start`._')
        except caravan_model.RouteExhausted:
            await self.warn(
                'Can\'t advance the caravan; no more gyms!\n'
                '_Try adding gyms with `!add` or `!append`._')

    @commands.register(
        'skip',
        description='Skip the current gym.',
        usage='!{cmd} [reason]',
        allowed_roles={Role.LEADER}
    )
    async def _skip(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.RouteAdvancedReceipt]:
        try:
            return self.model.advance(skip_reason=cmd_msg.args)
        except caravan_model.RouteNotActive:
            await self.warn(
                'The caravan is not in active mode, so it can\'t be '
                'advanced!\n'
                '_First start the caravan with `!start`._')
        except caravan_model.RouteExhausted:
            await self.warn(
                'No more gyms to skip!\n'
                '_Try adding gyms with `!add` or `!append`._')

    @commands.register(
        'add',
        description=(
            'Add a gym or gyms before the next one if the caravan is active, '
            'or to the end of the route otherwise.'),
        usage=(
            '!{cmd} <gym>\n'
            '\n'
            '!{cmd}\n'
            '- <gym>\n'
            '- <gym>\n'
            '- ...'),
        allowed_roles={Role.LEADER}
    )
    async def _add(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.RouteUpdateReceipt]:
        return await self._impl_add(
            content=cmd_msg.args,
            append=self.model.mode != caravan_model.CaravanMode.ACTIVE)

    @commands.register(
        'append',
        description=(
            'Add a gym or gyms to the end of the route.'),
        usage=(
            '!{cmd} <gym>\n'
            '\n'
            '!{cmd}\n'
            '- <gym>\n'
            '- <gym>\n'
            '- ...'),
        allowed_roles={Role.LEADER}
    )
    async def _append(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.RouteUpdateReceipt]:
        return await self._impl_add(content=cmd_msg.args, append=True)

    @commands.register(
        'remove', 'delete',
        description='Remove a gym or gyms from the route.',
        usage=(
            '!{cmd} <gym>\n'
            '\n'
            '!{cmd}\n'
            '- <gym>\n'
            '- <gym>\n'
            '- ...'),
        allowed_roles={Role.LEADER},
        preferred='remove'
    )
    async def _remove(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.RouteUpdateReceipt]:
        try:
            return self.model.remove_stops(
                places_iter=(
                    s.place for s in route.get_caravan_route(
                        content=cmd_msg.args,
                        all_places=self.gyms,
                        fuzzy=True)))
        except caravan_model.EmptyRouteException:
            raise InvalidCommandArgs(
                'You must specify at least one gym to remove.')

    @commands.register(
        'join',
        description='Join the route, optionally with guests.',
        usage='!{cmd} [+N]',
    )
    async def _join(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.MemberUpdateReceipt]:
        try:
            # noinspection PyProtectedMember
            return self.model.member_join(
                user=cmd_msg.message.author._user,
                guests=members.get_guest_count(cmd_msg.args))
        except members.InvalidGuestFormat:
            raise InvalidCommandArgs(
                'Guests must be specified like `!join +2` for you plus two '
                'guests.')
        except caravan_model.TooManyGuests as e:
            await self.warn(
                f'Typo? **{e.guests}** is a _lot_ of guests.')
        except caravan_model.MembersNotUpdated:
            # noinspection PyProtectedMember
            guest_count = self.model.members[cmd_msg.message.author._user]
            await self.info(
                f'You\'re already a member of this caravan with {guest_count} '
                f'{natural_language.pluralize("guest", guest_count)}.\n'
                f'_Modify your guest count with `!join +N`._')

    @commands.register(
        'leave',
        description='Leave the route along with registered guests.',
        allowed_roles={Role.MEMBER},
    )
    async def _leave(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.MemberUpdateReceipt]:
        try:
            # noinspection PyProtectedMember
            return self.model.member_leave(user=cmd_msg.message.author._user)
        except caravan_model.MembersNotUpdated:
            await self.info(
                'You\'re already _not_ a member of this caravan!')

    async def _impl_add(
            self,
            content: str,
            append: bool
    ) -> Optional[caravan_model.RouteUpdateReceipt]:
        try:
            return self.model.add_stops(
                route_slice=(
                    s.place for s in route.get_caravan_route(
                        content=content,
                        all_places=self.gyms,
                        fuzzy=True)),
                append=append)
        except caravan_model.EmptyRouteException:
            raise InvalidCommandArgs(
                'You must specify at least one gym to add.')


#
# Helpers
#

def leaders_msg(leaders: Iterable[discord.User], sep: str = ' ') -> str:
    mentions = sorted(u.mention for u in leaders)
    return (
        f'{natural_language.pluralize("leader", mentions)}{sep}'
        f'{natural_language.join(mentions)}')


@functools.singledispatch
def user_responses(receipt) -> Iterable[str]:
    raise NotImplementedError(
        f'No handler for {type(receipt)} receipt: {receipt}')


@user_responses.register
def _(receipt: caravan_model.LeaderUpdateReceipt) -> Iterable[str]:

    def gen_sentences():
        if receipt.leaders_added:
            yield (
                f'Added caravan {leaders_msg(receipt.leaders_added)}. :crown:')
        if receipt.leaders_removed:
            yield (
                f'Removed caravan {leaders_msg(receipt.leaders_removed)}.')

    yield ' '.join(gen_sentences())


@user_responses.register
def _(receipt: caravan_model.MemberUpdateReceipt) -> Iterable[str]:
    p = natural_language.pluralize

    if receipt.is_new_user is not None:
        if receipt.is_new_user:
            yield 'Welcome to the caravan, {who}!{guests}'.format(
                who=receipt.user.mention,
                guests=(
                    '' if not receipt.guests else (
                        f' You\'ve joined with {receipt.guests} '
                        f'{p("guest", receipt.guests)}.')))
        else:
            yield (
                f'You\'ve adjusted your guest count from '
                f'**{receipt.guests - receipt.guests_delta}** to '
                f'**{receipt.guests}**, {receipt.user.mention}.')
    else:
        yield (
            'Farewell, {who}! :wave: You\'ve left the caravan{guests}{leader}.'
            ''.format(
                who=receipt.user.mention,
                guests=(
                    f' with {receipt.guests} {p("guest", receipt.guests)}'
                    if receipt.guests else ''),
                leader=(
                    ' and resigned your caravan leader role'
                    if receipt.was_leader else '')))


@user_responses.register
def _(receipt: caravan_model.ModeUpdateReceipt) -> Iterable[str]:
    if receipt.new_mode == caravan_model.CaravanMode.ACTIVE:
        yield (
            'Caravan **active**! :race_car:\n'
            '_Advance the caravan with `!next` or `!skip [reason]`. '
            'You may `!stop` or `!reset` the caravan at any time. '
            'A stopped caravan can be resumed again with `!start`._')
        yield from gen_next_place_message(
            next_place=receipt.next_place,
            is_first=True)

    elif receipt.new_mode == caravan_model.CaravanMode.COMPLETED:
        p = natural_language.pluralize
        j = natural_language.join
        s = receipt.caravan_statistics

        def gen_stats_clauses():
            yield f'Visited **{s.visited}** {p("gym", s.visited)}'
            if s.skipped:
                yield f'skipped **{s.skipped}** {p("gym", s.skipped)}'
            if s.remaining:
                yield f'**{s.remaining}** {p("gym", s.remaining)} unvisited'

        yield (
            f'Caravan **complete**! :checkered_flag:\n'
            f'_{j(gen_stats_clauses())}._')

    else:
        yield (
            'Caravan reset back to **planning** mode! :map:\n'
            '_All gyms have been reset to **unvisited**. Start the caravan '
            'again with `!start`._')


@user_responses.register
def _(receipt: caravan_model.RouteUpdateReceipt) -> Iterable[str]:
    if receipt.is_reorder_only:
        yield 'Reordered route!'
    else:
        p = natural_language.pluralize
        j = natural_language.join

        def gen_clauses():
            if receipt.places_added:
                yield (
                    f'{"appended" if receipt.appended else "added"} '
                    f'**{len(receipt.places_added)}** '
                    f'{p("gym", receipt.places_added)}')
            if receipt.places_removed:
                yield (
                    f'removed **{len(receipt.places_removed)}** '
                    f'{p("gym", receipt.places_removed)}')

        yield (
            f'{j(gen_clauses()).capitalize()}. '
            f'The new route has **{len(receipt.new_route)}** '
            f'{p("gym", receipt.new_route)}. :map:')

    if receipt.mode == caravan_model.CaravanMode.ACTIVE:
        yield from gen_next_place_message(
            next_place=receipt.next_place,
            is_first=False)


@user_responses.register
def _(receipt: caravan_model.RouteAdvancedReceipt) -> Iterable[str]:
    yield from gen_next_place_message(
        next_place=receipt.next_place,
        is_first=False)


def gen_next_place_message(next_place: Optional[places.Place], is_first: bool):
    if next_place:
        yield (
            f'{"First" if is_first else "Next"} up: **{next_place.name}**\n'
            f':map: {next_place.maps_link}')
    else:
        yield 'No more gyms! _Try adding new gyms with `!add` or `!append`._'
