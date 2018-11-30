import contextlib
import dataclasses
import functools
import itertools
import random

from typing import Any, Callable, Coroutine, Iterable, Tuple, Optional

import discord
import inflection

from .roles import Role
from .pins import init_pins
from .pins.format import base_pin
from .pins.parse import parse_receipts
from . import caravan_model
from . import commands
from . import members
from . import natural_language
from . import places
from . import place_graph
from . import route


class InvalidCommandArgs(Exception):
    """Raised if the command syntax is invalid."""


@dataclasses.dataclass
class CaravanChannel:
    channel: discord.TextChannel
    model: caravan_model.CaravanModel
    pins: Tuple[base_pin.BasePin, ...]
    gyms: places.Places

    @classmethod
    async def from_channel(
            cls,
            channel: discord.TextChannel,
            gyms: places.Places,
            bot_user: discord.ClientUser,
            get_user: Callable[
                [int], Coroutine[Any, Any, Optional[discord.User]]],
    ) -> 'CaravanChannel':

        # Create an empty model to be populated as the pins are parsed.
        model = caravan_model.CaravanModel(channel=channel)

        pins_receipt = await init_pins(
            model=model,
            channel=channel,
            bot_user=bot_user,
            all_places=gyms)

        caravan = cls(
            channel=channel,
            model=model,
            pins=pins_receipt.pins,
            gyms=gyms)

        with contextlib.suppress(AttributeError):
            missing = pins_receipt.members_parse_receipt.missing_members  # type: ignore  # noqa

            if missing:
                await caravan.handle_receipt(
                    receipt=parse_receipts.MembersParseReceipt(
                        missing_members={
                            await get_user(user_id) or user_id: guests
                            for user_id, guests in missing.items()}))

        return caravan

    async def info(self, msg):
        if msg:
            await self.channel.send(msg)

    async def warn(self, msg):
        if msg:
            await self.channel.send(f':warning: {msg}')

    async def handle_command(self, cmd_msg: commands.CommandMessage):
        command = commands.commands[cmd_msg.name]
        author_roles = frozenset(self.model.gen_roles(
            cmd_msg.message.author))

        if not author_roles & command.allowed_roles:
            await self.warn(
                'Only {who} are able to {what}!'.format(
                    who=natural_language.join(
                        inflection.pluralize(r.name.lower())
                        for r in command.allowed_roles),
                    what=command.description.rstrip('.').lower()))
            return

        try:
            await self.handle_receipt(await command.handler(self, cmd_msg))
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
        except place_graph.NoPathThroughGraph:
            await self.warn(
                'Looks like you may have duplicated some gyms! Please check '
                'that each stop in your route is unique.')
        except caravan_model.DuplicatePlacesException as e:
            await self.warn(
                'The following {} duplicated: {}'.format(
                    'gym is' if len(e.duplicate_places) == 1 else 'gyms are',
                    natural_language.join(
                        f'**{p.name}**' for p in e.duplicate_places)))
        except route.UnknownPlaceNames as e:
            await self.warn(
                'The following {} not recognized: {}'.format(
                    'gym is' if len(e.unknown_names) == 1 else 'gyms are',
                    natural_language.join(
                        f'**{u}**' for u in e.unknown_names)))

    async def handle_receipt(self, receipt):
        if receipt is None:
            return

        # update pins
        for p in self.pins:
            await p.update(receipt=receipt, model=self.model)

        # message the channel so members know the caravan state has changed
        for r in user_notifications(receipt):
            await self.info(r)

    async def handle_member_remove(self, user: discord.Member):
        with contextlib.suppress(caravan_model.MembersNotUpdated):
            await self.handle_receipt(
                receipt=self.model.member_leave(user=user, left_server=True))

    @commands.register(
        'help',
        description='Display the help for all commands or a specific command.',
        usage='!{cmd} [command]'
    )
    async def _help(self, cmd_msg: commands.CommandMessage):
        user_roles = frozenset(
            self.model.gen_roles(cmd_msg.message.author))

        j = natural_language.join

        def roles(role_iter: Iterable[Role], markdown=lambda x: x):
            role_names = (r.name.casefold() for r in role_iter)
            sorted_roles = sorted(role_names)
            markdown_roles = (markdown(r) for r in sorted_roles)
            return j(markdown_roles)

        if not cmd_msg.args:
            def gen_help_lines():
                for cmd in commands.unique_commands:
                    if not cmd.allowed_roles & user_roles:
                        continue  # only display help for user's roles
                    yield (
                        f'`!{cmd.preferred}` — '
                        f'{cmd.description} _({roles(cmd.allowed_roles)})_')

            display_roles = user_roles - frozenset({Role.ANYONE})

            if display_roles:
                roles_description = (
                    f'your caravan '
                    f'{"role is" if len(display_roles) == 1 else "roles are"} '
                    f'{roles(display_roles, lambda x: f"**{x}**")}')
            else:
                roles_description = (
                    'you are not a member of this caravan (_yet_ :wink:)')

            await self.info(
                f'{cmd_msg.message.author.mention}, {roles_description}. '
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
        'leader', 'leaders',  # type: ignore
        description='Set the caravan leader or leaders.',
        usage='!{cmd} @user [@user]...',
        allowed_roles={Role.ADMIN, Role.LEADER},
        preferred='leaders'
    )
    async def _leaders(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.LeaderUpdateReceipt]:

        users = tuple(members.gen_members(
            channel=self.channel,
            content=cmd_msg.args))
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
            with self.channel.typing():  # can take a few seconds
                return self.model.set_route(new_route=(
                    s.place for s in route.get_caravan_route(
                        content=cmd_msg.args,
                        all_places=self.gyms,
                        fuzzy=True)))
        except caravan_model.EmptyRouteException:
            raise InvalidCommandArgs(
                'You must specify at least one gym in the route; preferably '
                'more!')

    # noinspection PyUnusedLocal
    @commands.register(
        'start', 'resume',  # type: ignore
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
            await self.info('The caravan has already been started!')

    # noinspection PyUnusedLocal
    @commands.register(
        'stop', 'done',  # type: ignore
        description='Stop the caravan.',
        allowed_roles={Role.LEADER},
        preferred='stop'
    )
    async def _stop(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.ModeUpdateReceipt]:
        try:
            # When the caravan is complete, it's not natural to `!next` past
            # the last stop. Therefore, `!stop` implies `!next`.
            with contextlib.suppress(caravan_model.RouteExhausted):
                self.model.advance()
            return self.model.stop()
        except (caravan_model.RouteNotActive, caravan_model.ModeNotUpdated):
            await self.info('The caravan is already _not_ active!')

    # noinspection PyUnusedLocal
    @commands.register(
        'reset',  # type: ignore
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
            await self.info('The caravan is already _not_ active!')

    # noinspection PyUnusedLocal
    @commands.register(
        'next',  # type: ignore
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
        'skip',  # type: ignore
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

    # noinspection PyUnusedLocal
    @commands.register(
        'prev', 'back',  # type: ignore
        description='Back the caravan up to the previous gym.',
        allowed_roles={Role.LEADER},
        preferred='prev'
    )
    async def _prev(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.RouteReversedReceipt]:
        try:
            return self.model.reverse()
        except caravan_model.RouteNotActive:
            await self.warn(
                'The caravan is not in active mode, so it can\'t be '
                'moved back one gym!\n'
                '_First start the caravan with `!start`._')
        except caravan_model.RouteAtBeginning:
            await self.warn(
                'Can\'t move the caravan back by one gym; it\'s already at '
                'the beginning!\n')

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
        'join',  # type: ignore
        description='Join the route, optionally with guests.',
        usage='!{cmd} [+N]',
    )
    async def _join(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.MemberUpdateReceipt]:
        try:
            return self.model.member_join(
                user=cmd_msg.message.author,
                guests=members.get_guest_count(cmd_msg.args))
        except members.InvalidGuestFormat:
            raise InvalidCommandArgs(
                'Guests must be specified like `!join +2` for you plus two '
                'guests.')
        except caravan_model.TooManyGuests as e:
            await self.warn(
                f'Typo? **{e.guests}** is a _lot_ of guests.')
        except caravan_model.MembersNotUpdated:
            guest_count = self.model.members[cmd_msg.message.author]
            await self.info(
                f'You\'re already a member of this caravan with {guest_count} '
                f'{natural_language.pluralize("guest", guest_count)}.\n'
                f'_Modify your guest count with `!join +N`._')

    @commands.register(
        'leave', 'unjoin',  # type: ignore
        description='Leave the route (with registered guests).',
        allowed_roles={Role.MEMBER},
        preferred='leave',
    )
    async def _leave(
            self,
            cmd_msg: commands.CommandMessage
    ) -> Optional[caravan_model.MemberUpdateReceipt]:
        try:
            return self.model.member_leave(
                user=cmd_msg.message.author,
                left_server=False)
        except caravan_model.MembersNotUpdated:
            await self.info('You\'re already _not_ a member of this caravan!')

    @commands.register(
        'notify',  # type: ignore
        description='Notify all caravan members of something.',
        usage='!{cmd} [message]',
    )
    async def _notify(self, cmd_msg: commands.CommandMessage):
        if not cmd_msg.args:
            raise InvalidCommandArgs('You must specify a message!')

        author = cmd_msg.message.author

        member_list = ' '.join(
            m.mention
            for m in sorted(
                self.model.members.keys(),
                key=lambda m: m.display_name)
            if m != author)

        if not member_list:
            await self.info(
                f'No{" other" if author in self.model.members else ""} '
                f'caravan members to notify!')
            return

        def get_relevant_author_role() -> str:
            roles = frozenset(self.model.gen_roles(author))

            # The author of a notification is most likely a caravan leader
            # informing the caravan of something important. For the purposes
            # of notifications, this role even supersedes ADMIN.
            if Role.LEADER in roles:
                return 'caravan leader'

            # If the author is not a leader but _is_ an admin, the notification
            # is likely server-related, or perhaps is being sent on behalf of
            # the leader (maybe even before a leader has been chosen).
            if Role.ADMIN in roles:
                return 'admin'

            # If the author is a caravan member with no other special role,
            # then it's pretty straightforward.
            if Role.MEMBER in roles:
                return 'caravan member'

            # Otherwise, this is a non-member messaging the caravan, perhaps
            # requesting info before joining.
            return 'non-caravan member'

        await self.info(
            f'**__{author.display_name}__ ({get_relevant_author_role()})** '
            f':loudspeaker:\n'
            f'{cmd_msg.args}\n'
            f'{member_list}')

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

def leaders_msg(leaders: Iterable[discord.Member], sep: str = ' ') -> str:
    mentions = sorted(u.mention for u in leaders)
    return (
        f'{natural_language.pluralize("leader", mentions)}{sep}'
        f'{natural_language.join(mentions)}')


@functools.singledispatch
def user_notifications(receipt) -> Iterable[str]:
    raise NotImplementedError(
        f'No handler for {type(receipt)} receipt: {receipt}')


@user_notifications.register  # type: ignore  # noqa
def _(receipt: caravan_model.LeaderUpdateReceipt) -> Iterable[str]:

    def gen_sentences():
        if receipt.leaders_added:
            yield (
                f'Added caravan {leaders_msg(receipt.leaders_added)}. :crown:')
        if receipt.leaders_removed:
            yield (
                f'Removed caravan {leaders_msg(receipt.leaders_removed)}.')

    yield ' '.join(gen_sentences())


@user_notifications.register  # type: ignore  # noqa
def _(receipt: parse_receipts.MembersParseReceipt) -> Iterable[str]:
    for user_or_id, guests in receipt.missing_members.items():
        yield from gen_member_left_server_messages(
            who=(
                'An unknown member _(deleted account?)_'
                if isinstance(user_or_id, int) else
                user_or_id.mention),
            guests=guests)


WAYS_TO_DIE = (
    'a broken arm',
    'a broken leg',
    'a fever',
    'a snakebite',
    'cholera',
    'drowning',
    'dysentery',
    'exhaustion',
    'measles',
    'typhoid',)


@user_notifications.register  # type: ignore  # noqa
def _(receipt: caravan_model.MemberJoinReceipt) -> Iterable[str]:
    p = natural_language.pluralize

    if not receipt.is_new_user:
        yield (
            f'You\'ve adjusted your guest count from '
            f'**{receipt.guests - receipt.guests_delta}** to '
            f'**{receipt.guests}**, {receipt.user.mention}.')
        return

    yield (
        'Welcome to the caravan, {who}!{guest_info}\n'
        '_{guest_example} {leave_example}_'.format(
            who=receipt.user.mention,
            guest_info=(
                '' if not receipt.guests else (
                    f' You\'ve joined with **{receipt.guests}** '
                    f'{p("guest", receipt.guests)}.')),
            guest_example=(
                'You may adjust your guest count with `!join [+N]`. '
                'For example, type `!join +{example_guests}` to change your '
                'guest count from {actual_guests} to {example_guests} guests.'
                .format(
                    actual_guests=receipt.guests,
                    example_guests=2 if receipt.guests != 2 else 3)),
            leave_example=(
                'You may also `!leave` this caravan at any point if your '
                'plans change.')))


@user_notifications.register  # type: ignore  # noqa
def _(receipt: caravan_model.MemberLeaveReceipt) -> Iterable[str]:
    p = natural_language.pluralize

    if receipt.left_server:
        yield from gen_member_left_server_messages(
            who=receipt.user.mention,
            guests=receipt.guests)
        return

    yield (
        '{who}{guests} {has_have}{both_all} died of {cause}. '
        ':skull_crossbones:\n'
        '_They have left the caravan{leader}._'.format(
            who=receipt.user.mention,
            guests=(
                f' and their {receipt.guests} {p("guest", receipt.guests)}'
                if receipt.guests else ''),
            has_have='have' if receipt.guests else 'has',
            both_all=' all' if receipt.guests > 1 else (
                ' both' if receipt.guests == 1 else ''),
            cause=random.choice(WAYS_TO_DIE),
            leader=(
                '' if not receipt.was_leader else
                ' and {} abandoned the caravan leader role'.format(
                    f'{receipt.user.display_name} has' if receipt.guests else
                    'have'))))


def gen_member_left_server_messages(who: str, guests: int):
    p = natural_language.pluralize
    yield (
        '{who}{guests} {has_have} left the server, and thus the caravan!'
        .format(
            who=who,
            guests=(
                f' and their {guests} {p("guest", guests)}' if guests else ''),
            has_have='have' if guests else 'has'))


@user_notifications.register  # type: ignore  # noqa
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


@user_notifications.register  # type: ignore  # noqa
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


@user_notifications.register  # type: ignore  # noqa
def _(receipt: caravan_model.RouteAdvancedReceipt) -> Iterable[str]:
    yield from gen_next_place_message(
        next_place=receipt.next_place,
        is_first=False)


@user_notifications.register  # type: ignore  # noqa
def _(receipt: caravan_model.RouteReversedReceipt) -> Iterable[str]:
    yield '\n'.join(itertools.chain(
        ('**Whoops!** _Backing the caravan up one gym._',),
        gen_next_place_message(
            next_place=receipt.next_place,
            is_first=False)))


def gen_next_place_message(next_place: Optional[places.Place], is_first: bool):
    if next_place:
        yield (
            f'{"First" if is_first else "Next"} up: **{next_place.name}**\n'
            f':map: {next_place.maps_link}')
    else:
        yield 'No more gyms! _Try adding new gyms with `!add` or `!append`._'
