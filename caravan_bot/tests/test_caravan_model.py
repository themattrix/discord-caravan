import collections
import dataclasses
import functools

from typing import Dict, DefaultDict

import pytest

from .. import caravan_model as cm
from .. import places


# noinspection PyArgumentList
def test_leadership():
    c = Caravan()

    def set_and_validate(leaders, expected_receipt, expected_members):
        actual_receipt = c.model.set_leaders(leaders=leaders)
        assert actual_receipt == expected_receipt
        assert c.model.leaders == expected_receipt.new_leaders
        assert c.model.members == expected_members

    set_and_validate(
        leaders={c.users.elliot, c.users.angela},
        expected_receipt=cm.LeaderUpdateReceipt(
            channel=c.model.channel,
            leaders_added={c.users.elliot: 0, c.users.angela: 0},
            leaders_removed={},
            old_leaders=frozenset(),
            new_leaders=frozenset({c.users.elliot, c.users.angela})),
        expected_members={c.users.elliot: 0, c.users.angela: 0})

    set_and_validate(
        leaders={c.users.elliot},
        expected_receipt=cm.LeaderUpdateReceipt(
            channel=c.model.channel,
            leaders_added={},
            leaders_removed={c.users.angela: 0},
            old_leaders=frozenset({c.users.elliot, c.users.angela}),
            new_leaders=frozenset({c.users.elliot})),
        # angela retains her membership
        expected_members={c.users.elliot: 0, c.users.angela: 0})

    set_and_validate(
        leaders={c.users.angela, c.users.tyrell},
        expected_receipt=cm.LeaderUpdateReceipt(
            channel=c.model.channel,
            leaders_added={c.users.angela: 0, c.users.tyrell: 0},
            leaders_removed={c.users.elliot: 0},
            old_leaders=frozenset({c.users.elliot}),
            new_leaders=frozenset({c.users.angela, c.users.tyrell})),
        # elliot retains his membership
        expected_members={
            c.users.elliot: 0, c.users.angela: 0, c.users.tyrell: 0})

    with pytest.raises(cm.LeadersNotUpdated):
        c.model.set_leaders(leaders=(
            c.users.angela,
            c.users.tyrell,
        ))

    set_and_validate(
        leaders=(),
        expected_receipt=cm.LeaderUpdateReceipt(
            channel=c.model.channel,
            leaders_added={},
            leaders_removed={c.users.angela: 0, c.users.tyrell: 0},
            old_leaders=frozenset({c.users.angela, c.users.tyrell}),
            new_leaders=frozenset()),
        # angela and tyrell retain their memberships
        expected_members={
            c.users.elliot: 0, c.users.angela: 0, c.users.tyrell: 0})

    with pytest.raises(cm.LeadersNotUpdated):
        c.model.set_leaders(leaders=())


# noinspection PyArgumentList
def test_route_set():
    c = Caravan()

    def p(name: str):
        return places.Place(name=name, location=f'location({name})')

    def set_and_validate(new_route, expected_receipt, expect_reordered):
        actual_receipt = c.model.set_route(new_route=new_route)
        assert actual_receipt == expected_receipt
        assert actual_receipt.is_reorder_only == expect_reordered
        assert tuple(s.place for s in c.model.route) == new_route

    set_and_validate(
        new_route=(p('a'), p('b'), p('c')),
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('a'), p('b'), p('c')}),
            places_removed=frozenset(),
            old_route=(),
            new_route=(p('a'), p('b'), p('c')),
            mode=c.model.mode,
            next_place=p('a'),
            appended=None),
        expect_reordered=False)

    set_and_validate(
        new_route=(p('b'), p('c'), p('d')),
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('d')}),
            places_removed=frozenset({p('a')}),
            old_route=(p('a'), p('b'), p('c')),
            new_route=(p('b'), p('c'), p('d')),
            mode=c.model.mode,
            next_place=p('b'),
            appended=None),
        expect_reordered=False)

    set_and_validate(
        new_route=(p('c'), p('d'), p('b')),
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset(),
            places_removed=frozenset(),
            old_route=(p('b'), p('c'), p('d')),
            new_route=(p('c'), p('d'), p('b')),
            mode=c.model.mode,
            next_place=p('c'),
            appended=None),
        expect_reordered=True)

    with pytest.raises(cm.RouteNotUpdated):
        c.model.set_route(new_route=(p('c'), p('d'), p('b')))

    with pytest.raises(cm.EmptyRouteException):
        c.model.set_route(new_route=())

    with pytest.raises(cm.DuplicatePlacesException) as exc_info:
        c.model.set_route(new_route=(p('a'), p('b'), p('a'), p('b')))
    assert exc_info.value.duplicate_places == frozenset({p('a'), p('b')})


# noinspection PyArgumentList
def test_route_add_and_remove():
    c = Caravan()

    def p(name: str):
        return places.Place(name=name, location=f'location({name})')

    def add_and_validate(route_slice, append, expected_receipt):
        actual_receipt = c.model.add_stops(
            route_slice=route_slice, append=append)
        assert actual_receipt == expected_receipt
        assert (
            tuple(s.place for s in c.model.route) ==
            expected_receipt.new_route)

    def remove_and_validate(places_iter, expected_receipt):
        actual_receipt = c.model.remove_stops(places_iter=places_iter)
        assert actual_receipt == expected_receipt
        assert (
            tuple(s.place for s in c.model.route) ==
            expected_receipt.new_route)

    add_and_validate(
        route_slice=(p('a'), p('b')),
        append=False,
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('a'), p('b')}),
            places_removed=frozenset(),
            old_route=(),
            new_route=(p('a'), p('b')),
            mode=cm.CaravanMode.PLANNING,
            next_place=p('a'),
            appended=True))

    add_and_validate(
        route_slice=(p('c'),),
        append=False,
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('c')}),
            places_removed=frozenset(),
            old_route=(p('a'), p('b')),
            new_route=(p('c'), p('a'), p('b')),
            mode=cm.CaravanMode.PLANNING,
            next_place=p('c'),
            appended=False))

    add_and_validate(
        route_slice=(p('d'),),
        append=True,
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('d')}),
            places_removed=frozenset(),
            old_route=(p('c'), p('a'), p('b')),
            new_route=(p('c'), p('a'), p('b'), p('d')),
            mode=cm.CaravanMode.PLANNING,
            next_place=p('c'),
            appended=True))

    c.model.start()
    c.model.advance()  # c

    add_and_validate(
        route_slice=(p('e'), p('f')),
        append=False,
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('e'), p('f')}),
            places_removed=frozenset(),
            old_route=(p('c'), p('a'), p('b'), p('d')),
            new_route=(p('c'), p('e'), p('f'), p('a'), p('b'), p('d')),
            mode=cm.CaravanMode.ACTIVE,
            next_place=p('e'),
            appended=False))

    c.model.advance()  # e
    c.model.advance()  # f
    c.model.advance()  # a
    c.model.advance()  # b

    add_and_validate(
        route_slice=(p('g'),),
        append=False,
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('g')}),
            places_removed=frozenset(),
            old_route=(p('c'), p('e'), p('f'), p('a'), p('b'), p('d')),
            new_route=(p('c'), p('e'), p('f'), p('a'), p('b'), p('g'), p('d')),
            mode=cm.CaravanMode.ACTIVE,
            next_place=p('g'),
            appended=False))

    remove_and_validate(
        places_iter=(p('a'), p('b'), p('e'), p('f')),
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset(),
            places_removed=frozenset({p('a'), p('b'), p('e'), p('f')}),
            old_route=(p('c'), p('e'), p('f'), p('a'), p('b'), p('g'), p('d')),
            new_route=(p('c'), p('g'), p('d')),
            mode=cm.CaravanMode.ACTIVE,
            next_place=p('g'),
            appended=None))

    c.model.advance()  # g

    add_and_validate(
        route_slice=(p('h'),),
        append=False,
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('h')}),
            places_removed=frozenset(),
            old_route=(p('c'), p('g'), p('d')),
            new_route=(p('c'), p('g'), p('h'), p('d')),
            mode=cm.CaravanMode.ACTIVE,
            next_place=p('h'),
            appended=False))

    add_and_validate(
        route_slice=(p('i'),),
        append=True,
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('i')}),
            places_removed=frozenset(),
            old_route=(p('c'), p('g'), p('h'), p('d')),
            new_route=(p('c'), p('g'), p('h'), p('d'), p('i')),
            mode=cm.CaravanMode.ACTIVE,
            next_place=p('h'),
            appended=True))

    c.model.advance()  # h
    c.model.advance()  # d
    c.model.advance()  # i

    add_and_validate(
        route_slice=(p('j'),),
        append=False,
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset({p('j')}),
            places_removed=frozenset(),
            old_route=(p('c'), p('g'), p('h'), p('d'), p('i')),
            new_route=(p('c'), p('g'), p('h'), p('d'), p('i'), p('j')),
            mode=cm.CaravanMode.ACTIVE,
            next_place=p('j'),
            appended=True))

    c.model.advance()  # j

    remove_and_validate(
        places_iter=(p('c'), p('h'), p('i')),
        expected_receipt=cm.RouteUpdateReceipt(
            channel=c.model.channel,
            places_added=frozenset(),
            places_removed=frozenset({p('c'), p('h'), p('i')}),
            old_route=(p('c'), p('g'), p('h'), p('d'), p('i'), p('j')),
            new_route=(p('g'), p('d'), p('j')),
            mode=cm.CaravanMode.ACTIVE,
            next_place=None,
            appended=None))

    with pytest.raises(cm.EmptyRouteException):
        c.model.add_stops(route_slice=(), append=True)

    with pytest.raises(cm.DuplicatePlacesException) as exc_info:
        c.model.add_stops(route_slice=(p('d'), p('k')), append=True)
    assert exc_info.value.duplicate_places == frozenset({p('d')})

    with pytest.raises(cm.DuplicatePlacesException) as exc_info:
        c.model.add_stops(route_slice=(p('k'), p('k')), append=True)
    assert exc_info.value.duplicate_places == frozenset({p('k')})

    with pytest.raises(cm.DuplicatePlacesException) as exc_info:
        c.model.add_stops(route_slice=(p('d'), p('k'), p('k')), append=True)
    assert exc_info.value.duplicate_places == frozenset({p('d'), p('k')})

    with pytest.raises(cm.RouteNotUpdated):
        c.model.remove_stops(places_iter=())

    with pytest.raises(cm.MissingPlacesException) as exc_info:
        c.model.remove_stops(places_iter=(p('a'), p('b'), p('d')))
    assert exc_info.value.missing_places == frozenset({p('a'), p('b')})


# noinspection PyArgumentList
def test_route_advance():
    c = Caravan()

    def p(name: str):
        return places.Place(name=name, location=f'location({name})')

    def advance_and_validate(skip_reason, expected_receipt, expected_route):
        actual_receipt = c.model.advance(skip_reason=skip_reason)
        assert actual_receipt == expected_receipt
        assert c.model.route == expected_route

    with pytest.raises(cm.RouteNotActive):
        c.model.advance()

    c.model.start()

    with pytest.raises(cm.RouteExhausted):
        c.model.advance()

    c.model.set_route(new_route=(p('a'), p('b'), p('c')))

    assert c.model.route == (
        cm.CaravanStop(place=p('a'), visited=False, skip_reason=None),
        cm.CaravanStop(place=p('b'), visited=False, skip_reason=None),
        cm.CaravanStop(place=p('c'), visited=False, skip_reason=None),
    )

    advance_and_validate(
        skip_reason=None,
        expected_receipt=cm.RouteAdvancedReceipt(
            channel=c.model.channel,
            next_place=p('b')),
        expected_route=(
            cm.CaravanStop(place=p('a'), visited=True, skip_reason=None),
            cm.CaravanStop(place=p('b'), visited=False, skip_reason=None),
            cm.CaravanStop(place=p('c'), visited=False, skip_reason=None),
        ))

    c.model.stop()

    with pytest.raises(cm.RouteNotActive):
        c.model.advance()

    c.model.start()

    advance_and_validate(
        skip_reason='',
        expected_receipt=cm.RouteAdvancedReceipt(
            channel=c.model.channel,
            next_place=p('c')),
        expected_route=(
            cm.CaravanStop(place=p('a'), visited=True, skip_reason=None),
            cm.CaravanStop(place=p('b'), visited=True, skip_reason=''),
            cm.CaravanStop(place=p('c'), visited=False, skip_reason=None),
        ))

    advance_and_validate(
        skip_reason='reason',
        expected_receipt=cm.RouteAdvancedReceipt(
            channel=c.model.channel,
            next_place=None),
        expected_route=(
            cm.CaravanStop(place=p('a'), visited=True, skip_reason=None),
            cm.CaravanStop(place=p('b'), visited=True, skip_reason=''),
            cm.CaravanStop(place=p('c'), visited=True, skip_reason='reason'),
        ))

    with pytest.raises(cm.RouteExhausted):
        c.model.advance()

    c.model.stop()

    with pytest.raises(cm.RouteNotActive):
        c.model.advance()

    c.model.reset()

    with pytest.raises(cm.RouteNotActive):
        c.model.advance()

    c.model.start()

    advance_and_validate(
        skip_reason='eh',
        expected_receipt=cm.RouteAdvancedReceipt(
            channel=c.model.channel,
            next_place=p('b')),
        expected_route=(
            cm.CaravanStop(place=p('a'), visited=True, skip_reason='eh'),
            cm.CaravanStop(place=p('b'), visited=False, skip_reason=None),
            cm.CaravanStop(place=p('c'), visited=False, skip_reason=None),
        ))


# noinspection PyArgumentList
def test_mode_change():
    c = Caravan()

    def p(name: str):
        return places.Place(name=name, location=f'location({name})')

    assert c.model.mode == cm.CaravanMode.PLANNING

    with pytest.raises(cm.ModeNotUpdated):
        c.model.stop()

    with pytest.raises(cm.ModeNotUpdated):
        c.model.reset()

    assert c.model.start() == cm.ModeUpdateReceipt(
        channel=c.model.channel,
        old_mode=cm.CaravanMode.PLANNING,
        new_mode=cm.CaravanMode.ACTIVE,
        next_place=None,
        caravan_statistics=None)
    assert c.model.mode == cm.CaravanMode.ACTIVE

    with pytest.raises(cm.ModeNotUpdated):
        c.model.start()

    assert c.model.stop() == cm.ModeUpdateReceipt(
        channel=c.model.channel,
        old_mode=cm.CaravanMode.ACTIVE,
        new_mode=cm.CaravanMode.COMPLETED,
        next_place=None,
        caravan_statistics=cm.CaravanStatistics(
            visited=0,
            skipped=0,
            remaining=0))
    assert c.model.mode == cm.CaravanMode.COMPLETED

    with pytest.raises(cm.ModeNotUpdated):
        c.model.stop()

    assert c.model.start() == cm.ModeUpdateReceipt(
        channel=c.model.channel,
        old_mode=cm.CaravanMode.COMPLETED,
        new_mode=cm.CaravanMode.ACTIVE,
        next_place=None,
        caravan_statistics=None)
    assert c.model.mode == cm.CaravanMode.ACTIVE

    assert c.model.stop() == cm.ModeUpdateReceipt(
        channel=c.model.channel,
        old_mode=cm.CaravanMode.ACTIVE,
        new_mode=cm.CaravanMode.COMPLETED,
        next_place=None,
        caravan_statistics=cm.CaravanStatistics(
            visited=0,
            skipped=0,
            remaining=0))
    assert c.model.mode == cm.CaravanMode.COMPLETED

    assert c.model.reset() == cm.ModeUpdateReceipt(
        channel=c.model.channel,
        old_mode=cm.CaravanMode.COMPLETED,
        new_mode=cm.CaravanMode.PLANNING,
        next_place=None,
        caravan_statistics=None)
    assert c.model.mode == cm.CaravanMode.PLANNING

    with pytest.raises(cm.ModeNotUpdated):
        c.model.stop()

    c.model.set_route(new_route=(p('a'), p('b'), p('c')))

    assert c.model.start() == cm.ModeUpdateReceipt(
        channel=c.model.channel,
        old_mode=cm.CaravanMode.PLANNING,
        new_mode=cm.CaravanMode.ACTIVE,
        next_place=p('a'),
        caravan_statistics=None)
    assert c.model.mode == cm.CaravanMode.ACTIVE

    c.model.advance()
    c.model.advance(skip_reason='')
    c.model.advance(skip_reason='eh')

    assert c.model.reset() == cm.ModeUpdateReceipt(
        channel=c.model.channel,
        old_mode=cm.CaravanMode.ACTIVE,
        new_mode=cm.CaravanMode.PLANNING,
        next_place=None,
        caravan_statistics=None)
    assert c.model.mode == cm.CaravanMode.PLANNING

    assert c.model.start() == cm.ModeUpdateReceipt(
        channel=c.model.channel,
        old_mode=cm.CaravanMode.PLANNING,
        new_mode=cm.CaravanMode.ACTIVE,
        next_place=p('a'),
        caravan_statistics=None)
    assert c.model.mode == cm.CaravanMode.ACTIVE

    def stop_and_validate(expected_next, expected_stats):
        # noinspection PyArgumentList
        assert c.model.stop() == cm.ModeUpdateReceipt(
            channel=c.model.channel,
            old_mode=cm.CaravanMode.ACTIVE,
            new_mode=cm.CaravanMode.COMPLETED,
            next_place=expected_next,
            caravan_statistics=expected_stats)
        assert c.model.mode == cm.CaravanMode.COMPLETED

    stop_and_validate(
        expected_next=p('a'),
        expected_stats=cm.CaravanStatistics(
            visited=0,
            skipped=0,
            remaining=3))

    c.model.start()
    c.model.advance()
    stop_and_validate(
        expected_next=p('b'),
        expected_stats=cm.CaravanStatistics(
            visited=1,
            skipped=0,
            remaining=2))

    c.model.start()
    c.model.advance(skip_reason='')
    stop_and_validate(
        expected_next=p('c'),
        expected_stats=cm.CaravanStatistics(
            visited=1,
            skipped=1,
            remaining=1))

    c.model.start()
    c.model.advance(skip_reason='eh')
    stop_and_validate(
        expected_next=None,
        expected_stats=cm.CaravanStatistics(
            visited=1,
            skipped=2,
            remaining=0))


# noinspection PyArgumentList
def test_membership():
    c = Caravan()

    def join_and_validate(member, guests, expected_receipt, expected_members):
        actual_receipt = c.model.member_join(user=member, guests=guests)
        assert actual_receipt == expected_receipt
        assert c.model.members == expected_members

    def leave_and_validate(
            member, left_server, expected_receipt, expected_members):
        actual_receipt = c.model.member_leave(
            user=member, left_server=left_server)
        assert actual_receipt == expected_receipt
        assert c.model.members == expected_members

    join_and_validate(
        member=c.users.elliot,
        guests=0,
        expected_receipt=cm.MemberJoinReceipt(
            channel=c.model.channel,
            user=c.users.elliot,
            guests=0,
            guests_delta=0,
            is_new_user=True),
        expected_members={
            c.users.elliot: 0,
        })

    with pytest.raises(cm.MembersNotUpdated):
        c.model.member_join(user=c.users.elliot, guests=0)

    join_and_validate(
        member=c.users.elliot,
        guests=2,
        expected_receipt=cm.MemberJoinReceipt(
            channel=c.model.channel,
            user=c.users.elliot,
            guests=2,
            guests_delta=2,
            is_new_user=False),
        expected_members={
            c.users.elliot: 2,
        })

    with pytest.raises(cm.MembersNotUpdated):
        c.model.member_join(user=c.users.elliot, guests=2)

    join_and_validate(
        member=c.users.angela,
        guests=4,
        expected_receipt=cm.MemberJoinReceipt(
            channel=c.model.channel,
            user=c.users.angela,
            guests=4,
            guests_delta=4,
            is_new_user=True),
        expected_members={
            c.users.elliot: 2,
            c.users.angela: 4,
        })

    join_and_validate(
        member=c.users.angela,
        guests=1,
        expected_receipt=cm.MemberJoinReceipt(
            channel=c.model.channel,
            user=c.users.angela,
            guests=1,
            guests_delta=-3,
            is_new_user=False),
        expected_members={
            c.users.elliot: 2,
            c.users.angela: 1,
        })

    with pytest.raises(cm.TooManyGuests):
        c.model.member_join(
            user=c.users.elliot,
            guests=cm.MAX_REASONABLE_GUESTS + 1)

    leave_and_validate(
        member=c.users.elliot,
        left_server=False,
        expected_receipt=cm.MemberLeaveReceipt(
            channel=c.model.channel,
            user=c.users.elliot,
            guests=2,
            guests_delta=-2,
            was_leader=False,
            left_server=False),
        expected_members={
            c.users.angela: 1,
        })

    with pytest.raises(cm.MembersNotUpdated):
        c.model.member_leave(c.users.elliot, left_server=False)

    c.model.set_leaders(leaders=(c.users.angela,))

    leave_and_validate(
        member=c.users.angela,
        left_server=True,
        expected_receipt=cm.MemberLeaveReceipt(
            channel=c.model.channel,
            user=c.users.angela,
            guests=1,
            guests_delta=-1,
            was_leader=True,
            left_server=True),
        expected_members={})


def test_gen_roles():
    c = Caravan()

    c.users.admin.permissions[c.model.channel].administrator = True
    c.model.set_leaders((c.users.leader,))
    c.model.member_join(user=c.users.member, guests=0)

    assert frozenset(c.model.gen_roles(c.users.admin)) == frozenset((
        cm.Role.ADMIN,
        cm.Role.ANYONE,
    ))

    assert frozenset(c.model.gen_roles(c.users.leader)) == frozenset((
        cm.Role.LEADER,
        cm.Role.MEMBER,
        cm.Role.ANYONE,
    ))

    assert frozenset(c.model.gen_roles(c.users.member)) == frozenset((
        cm.Role.MEMBER,
        cm.Role.ANYONE,
    ))

    assert frozenset(c.model.gen_roles(c.users.anyone)) == frozenset((
        cm.Role.ANYONE,
    ))


@pytest.mark.parametrize('a,b,expected_result', (
    ('', '', ''),
    ('a', 'b', '-a\n+b'),
    ('ab', 'bc', '-a\n b\n+c'),
    ('abcdef', 'b', '-a\n b\n-c\n-d\n-e\n-f'),
    ('e', 'abcdef', '+a\n+b\n+c\n+d\n e\n+f'),
))
def test_line_diff(a, b, expected_result):
    assert cm.line_diff(a, b) == expected_result


#
# Helpers
#

@dataclasses.dataclass(frozen=True)
class FakeChannel:
    name: str
    guild: 'FakeGuild'


@dataclasses.dataclass(frozen=True)
class FakeGuild:
    name: str


@dataclasses.dataclass
class FakePermissions:
    administrator: bool = False


@dataclasses.dataclass(frozen=True)
class FakeUser:
    name: str
    permissions: DefaultDict[FakeChannel, FakePermissions] = dataclasses.field(  # type: ignore  # noqa
        default_factory=functools.partial(
            collections.defaultdict, FakePermissions),
        compare=False, hash=None)

    @property
    def id(self):
        return self.name

    @property
    def display_name(self):
        return self.name

    @property
    def _user(self):
        return self

    def permissions_in(self, channel: FakeChannel):
        return self.permissions[channel]


@dataclasses.dataclass
class Users:
    users: Dict[str, FakeUser] = dataclasses.field(default_factory=dict)

    def __getattr__(self, item):
        if item not in self.users:
            self.users[item] = FakeUser(name=item)
        return self.users[item]


@dataclasses.dataclass
class Caravan:
    users: Users = dataclasses.field(
        init=False, repr=False, hash=False, compare=False,
        default_factory=Users)
    model: cm.CaravanModel = dataclasses.field(
        default_factory=functools.partial(
            cm.CaravanModel, channel=FakeChannel(
                name='caravan',
                guild=FakeGuild('guild'))))
