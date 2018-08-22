import dataclasses
import functools

from typing import Dict

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
def test_route():
    c = Caravan()

    def p(name: str):
        return places.Place(name=name, location=f'location({name})')

    def set_and_validate(new_route, expected_receipt):
        actual_receipt = c.model.set_route(new_route=new_route)
        assert actual_receipt == expected_receipt
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
            appended=None))

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
            appended=None))

    with pytest.raises(cm.RouteNotUpdated):
        c.model.set_route(new_route=(p('b'), p('c'), p('d')))

    with pytest.raises(cm.EmptyRouteException):
        c.model.set_route(new_route=())

    with pytest.raises(cm.DuplicatePlacesException) as exc_info:
        c.model.set_route(new_route=(p('a'), p('b'), p('a'), p('b')))

    assert exc_info.value.duplicate_places == frozenset({p('a'), p('b')})


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


@dataclasses.dataclass(frozen=True)
class FakeUser:
    name: str

    @property
    def id(self):
        return self.name

    @property
    def display_name(self):
        return self.name


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
