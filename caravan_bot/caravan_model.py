import collections
import contextlib
import dataclasses
import difflib
import enum
import itertools
import re

from typing import Dict, FrozenSet, Iterable, Optional, Tuple

import discord

from .log import log
from .roles import Role
from . import places


PlacesIter = Iterable[places.Place]
Places = FrozenSet[places.Place]

RouteIter = Iterable[places.Place]
Route = Tuple[places.Place, ...]

CaravanRouteIter = Iterable['CaravanStop']
CaravanRoute = Tuple['CaravanStop', ...]


class LeadersNotUpdated(Exception):
    """Raised if the leaders were expected to be updated but were not."""


@dataclasses.dataclass(frozen=True)
class UpdateReceipt:
    channel: discord.TextChannel

    def log(self, message):
        log.info(f'[{self.channel.name}/{self.channel.guild.name}] {message}')


@dataclasses.dataclass(frozen=True)
class LeaderUpdateReceipt(UpdateReceipt):
    leaders_added: Dict[discord.Member, int]
    leaders_removed: Dict[discord.Member, int]
    old_leaders: FrozenSet[discord.Member]
    new_leaders: FrozenSet[discord.Member]

    def __post_init__(self):
        self.log('Leaders changed:\n' + line_diff(
            (format_member(u) for u in sorted_users(self.old_leaders)),
            (format_member(u) for u in sorted_users(self.new_leaders))))


MAX_REASONABLE_GUESTS = 10


@dataclasses.dataclass(frozen=True)
class TooManyGuests(Exception):
    """Raised if an unreasonable number of guests were specified."""
    guests: int
    max_guests: int


class MembersNotUpdated(Exception):
    """Raised if the members were expected to be updated but was not."""


@dataclasses.dataclass(frozen=True)
class MemberUpdateReceipt(UpdateReceipt):
    user: discord.Member
    guests: int
    guests_delta: int


@dataclasses.dataclass(frozen=True)
class MemberJoinReceipt(MemberUpdateReceipt):
    is_new_user: bool

    def __post_init__(self):
        self.log(
            '{status} member @{member} has {what} {delta}'.format(
                status='New' if self.is_new_user else 'Existing',
                member=self.user.display_name,
                what='joined' if self.is_new_user else 'updated guest count',
                delta=f'(guest delta: {self.guests_delta:+})'))


@dataclasses.dataclass(frozen=True)
class MemberLeaveReceipt(MemberUpdateReceipt):
    was_leader: bool
    left_server: bool

    def __post_init__(self):
        self.log(
            'Existing {title} @{member} has {what} {delta}'.format(
                title='leader' if self.was_leader else 'member',
                member=self.user.display_name,
                what='left the server' if self.left_server else 'left',
                delta=f'(guest delta: {self.guests_delta:+})'))


class CaravanMode(enum.Enum):
    PLANNING = 0
    ACTIVE = 1
    COMPLETED = 2


class ModeNotUpdated(Exception):
    """Raised if the mode was expected to be updated but was not."""


@dataclasses.dataclass(frozen=True)
class ModeUpdateReceipt(UpdateReceipt):
    old_mode: CaravanMode
    new_mode: CaravanMode
    next_place: Optional[places.Place] = None
    caravan_statistics: Optional['CaravanStatistics'] = None

    def __post_init__(self):
        self.log(
            f'Mode changed from {self.old_mode.name} to {self.new_mode.name}')


class EmptyRouteException(Exception):
    """Raised if the given route is empty."""


class DuplicatePlacesException(Exception):
    """Raised when the given route contains the same place multiple times."""

    def __init__(self, duplicate_places: PlacesIter) -> None:
        self.duplicate_places = frozenset(duplicate_places)


class MissingPlacesException(Exception):
    """Raised when some given places are not contained in the route."""

    def __init__(self, missing_places: PlacesIter) -> None:
        self.missing_places = frozenset(missing_places)


class RouteNotUpdated(Exception):
    """Raised if the route was expected to be updated but was not."""


@dataclasses.dataclass(frozen=True)
class RouteUpdateReceipt(UpdateReceipt):
    places_added: Places
    places_removed: Places
    old_route: Route
    new_route: Route
    mode: CaravanMode
    next_place: Optional[places.Place] = None
    appended: Optional[bool] = None  # only set on add/append

    @property
    def is_reorder_only(self) -> bool:
        return not self.places_added and not self.places_removed

    def __post_init__(self):
        self.log(
            f'Route changed ('
            f'+{len(self.places_added)} '
            f'-{len(self.places_removed)}):\n' + line_diff(
                format_route(self.old_route),
                format_route(self.new_route)))
        if self.mode == CaravanMode.ACTIVE and self.next_place is not None:
            self.log(f'Next up: {format_place(self.next_place)}')


class RouteNotActive(Exception):
    """Raised if the caravan needs to be active but was not."""


class RouteExhausted(Exception):
    """
    Raised if the caravan could not be advanced because the route is
    exhausted.
    """


@dataclasses.dataclass(frozen=True)
class RouteAdvancedReceipt(UpdateReceipt):
    next_place: Optional[places.Place] = None

    def __post_init__(self):
        if self.next_place:
            self.log(
                f'Route advanced; next place: {self.next_place.name} '
                f'({self.next_place.location})')
        else:
            self.log(f'Route advanced; no more stops.')


# noinspection PyArgumentList
@dataclasses.dataclass
class CaravanModel:
    """
    Maintains the caravan state. Responds to state changes with update
    receipts. Raises exceptions when requested state changes are not made.
    """
    channel: discord.TextChannel
    leaders: FrozenSet[discord.Member] = frozenset()
    members: Dict[discord.Member, int] = dataclasses.field(
        default_factory=dict)
    route: CaravanRoute = ()
    mode: CaravanMode = CaravanMode.PLANNING

    def gen_roles(self, member: discord.Member) -> Iterable[Role]:
        """Yields the user's roles in this caravan."""
        yield Role.ANYONE
        if member in self.members:
            yield Role.MEMBER
        if member in self.leaders:
            yield Role.LEADER
        if member.permissions_in(self.channel).administrator:
            yield Role.ADMIN

    @property
    def total_members(self):
        """Returns the number of members plus guests."""
        return len(self.members) + sum(self.members.values())

    def set_leaders(
            self,
            leaders: Iterable[discord.Member]
    ) -> LeaderUpdateReceipt:
        """
        Delegate a new set of caravan leaders.

        New leaders which were not already caravan members are
        automatically added as members. Existing members deleted as
        leaders are simply "upgraded" to leaders, while retaining their
        guest counts.

        Removed leaders are still retained as caravan members.

        Returns a `LeaderUpdateReceipt` if the supplied leaders were
        different than the existing leaders. Raises a
        `LeadersNotUpdated` exception otherwise.
        """
        leaders = frozenset(leaders)

        if leaders == self.leaders:
            raise LeadersNotUpdated()

        receipt = LeaderUpdateReceipt(
            channel=self.channel,
            old_leaders=self.leaders,
            new_leaders=leaders,
            leaders_added={
                u: self.members.get(u, 0) for u in leaders - self.leaders},
            leaders_removed={
                u: self.members[u] for u in self.leaders - leaders})

        for user in receipt.leaders_added:
            self.members[user] = self.members.get(user, 0)

        self.leaders = leaders

        return receipt

    def set_route(self, new_route: RouteIter) -> RouteUpdateReceipt:
        """
        Replace the existing route (if any) with the given one.

        Returns a `RouteUpdateReceipt` if the route changes.
        Raises an `EmptyRouteException` if the supplied route contains
        no places.
        Raises a `DuplicatePlacesException` if the supplied route
        contains duplicates.
        Raises a `RouteNotUpdated` exception if the route requires no
        change.
        """
        new_route = tuple(new_route)

        # Ensure that the new route contains at least one place.
        if not new_route:
            raise EmptyRouteException()

        old_route = tuple(s.place for s in self.route)

        # Ensure that the new route contains no duplicates.
        ensure_unique_places(new_route)

        # Ensure that the new route differs from the old route.
        if new_route == old_route:
            raise RouteNotUpdated()

        old_places = frozenset(old_route)
        new_places = frozenset(new_route)

        old_stops = {s.place: s for s in self.route}

        # Assign a new caravan route, keeping the existing stop properties
        # where possible.
        self.route = tuple(
            old_stops.get(p, CaravanStop(p)) for p in new_route)

        return RouteUpdateReceipt(
            channel=self.channel,
            places_added=new_places - old_places,
            places_removed=old_places - new_places,
            old_route=old_route,
            new_route=new_route,
            mode=self.mode,
            next_place=next_unvisited_place(self.route))

    def add_stops(
            self,
            route_slice: RouteIter,
            append: bool
    ) -> RouteUpdateReceipt:
        """
        Add stops to the route. If `append` is `True`, the stops are
        appended to the end of the route. Otherwise, they're inserted
        after the last visited stop.

        Returns a `RouteUpdateReceipt` if the route changes.
        Raises an `EmptyRouteException` if the supplied route contains
        no places.
        Raises a `DuplicatePlacesException` if the supplied route
        contains duplicates or duplicates existing stops.
        """
        route_slice = tuple(route_slice)

        # Ensure that the new route contains at least one place.
        if not route_slice:
            raise EmptyRouteException()

        old_route = tuple(s.place for s in self.route)

        # Ensure that the new route contains no duplicates with itself or with
        # the existing route.
        ensure_unique_places(old_route, route_slice)

        insert_at = (
            len(self.route) if append else
            first_unvisited_index(self.route))

        appended = insert_at >= len(self.route)

        self.route = (
            self.route[:insert_at] +
            tuple(CaravanStop(p) for p in route_slice) +
            self.route[insert_at:])

        return RouteUpdateReceipt(
            channel=self.channel,
            places_added=frozenset(route_slice),
            places_removed=frozenset(),
            old_route=old_route,
            new_route=tuple(s.place for s in self.route),
            mode=self.mode,
            next_place=next_unvisited_place(self.route),
            appended=appended)

    def remove_stops(self, places_iter: PlacesIter) -> RouteUpdateReceipt:
        """
        Remove the given stops from the route.

        Returns a `RouteUpdateReceipt` if all given stops were removed.
        Raises a `RouteNotUpdated` exception if no places were given.
        Raises a `MissingPlacesException` if at least one of the places
        wasn't present in the existing route.
        """
        to_remove = frozenset(places_iter)

        if not to_remove:
            raise RouteNotUpdated()

        missing_places = (
            frozenset(to_remove) - frozenset(s.place for s in self.route))

        if missing_places:
            raise MissingPlacesException(missing_places=missing_places)

        old_route = self.route
        self.route = tuple(s for s in self.route if s.place not in to_remove)

        return RouteUpdateReceipt(
            channel=self.channel,
            places_added=frozenset(),
            places_removed=to_remove,
            old_route=tuple(s.place for s in old_route),
            new_route=tuple(s.place for s in self.route),
            mode=self.mode,
            next_place=next_unvisited_place(self.route))

    def start(self) -> ModeUpdateReceipt:
        """
        Put the caravan into ACTIVE mode.

        Returns a `ModeUpdateReceipt` if the mode was changed.
        Raises a `ModeNotUpdated` exception if the caravan is already
        ACTIVE.
        """
        return self.__change_mode(CaravanMode.ACTIVE)

    def stop(self) -> ModeUpdateReceipt:
        """
        Put the caravan into COMPLETED mode.

        Returns a `ModeUpdateReceipt` if the mode was changed.
        Raises a `ModeNotUpdated` exception if the caravan is already
        COMPLETED.
        """
        return self.__change_mode(CaravanMode.COMPLETED)

    def reset(self) -> ModeUpdateReceipt:
        """
        Put the caravan into PLANNING mode and sets each stop to be
        unvisited.

        Returns a `ModeUpdateReceipt` if the mode was changed.
        Raises a `ModeNotUpdated` exception if the caravan is already
        in PLANNING mode.
        """
        receipt = self.__change_mode(CaravanMode.PLANNING)
        self.route = tuple(s.reset() for s in self.route)
        return receipt

    def advance(
            self,
            skip_reason: Optional[str] = None
    ) -> RouteAdvancedReceipt:
        """
        Advance the caravan to the next stop, optionally marking the
        current one as skipped.

        Returns a `RouteAdvancedReceipt` if the caravan could be
        advanced.
        Raises a `RouteNotActive` exception if the route is not active.
        Raises a `RouteExhausted` exception if the route could not be
        advanced because it's been exhausted.
        """
        if self.mode != CaravanMode.ACTIVE:
            raise RouteNotActive()

        next_place = next_unvisited_place(self.route)

        if next_place is None:
            raise RouteExhausted()

        self.route = tuple(
            (s.visit(skip_reason=skip_reason) if s.place == next_place else s)
            for s in self.route)

        return RouteAdvancedReceipt(
            channel=self.channel,
            next_place=next_unvisited_place(self.route))

    def member_join(
            self,
            user: discord.Member,
            guests: int = 0
    ) -> MemberJoinReceipt:
        """
        Join a user to the caravan, optionally with guests.

        Returns a `MemberUpdateReceipt` if the member was added, or the
        guest count was updated for that member.
        Raises a `TooManyGuests` exception if the number of guests is
        unreasonably high.
        Raises a `MembersNotUpdated` exception if the member is already
        registered with the same amount of guests.
        """
        if guests > MAX_REASONABLE_GUESTS:
            raise TooManyGuests(
                guests=guests,
                max_guests=MAX_REASONABLE_GUESTS)

        with contextlib.suppress(KeyError):
            if self.members[user] == guests:
                raise MembersNotUpdated()

        receipt = MemberJoinReceipt(
            channel=self.channel,
            user=user,
            guests=guests,
            is_new_user=user not in self.members,
            guests_delta=guests - self.members.get(user, 0))

        self.members[user] = guests

        return receipt

    def member_leave(
            self,
            user: discord.Member,
            left_server: bool,
    ) -> MemberLeaveReceipt:
        """
        Leave the caravan with whatever guests the member had invited.

        Leaders who leave are automatically un-registered as leaders.

        Returns a `MemberUpdateReceipt` if the member was removed.
        Raises a `MembersNotUpdated` if the user is not a member.
        """
        try:
            guests = self.members.pop(user)
        except KeyError:
            raise MembersNotUpdated()

        receipt = MemberLeaveReceipt(
            channel=self.channel,
            user=user,
            guests=guests,
            guests_delta=-guests,
            was_leader=user in self.leaders,
            left_server=left_server)

        self.leaders -= frozenset({user})

        return receipt

    def __change_mode(self, mode: CaravanMode) -> ModeUpdateReceipt:
        """
        Puts the caravan into the given mode if it isn't already.

        Returns a `ModeUpdateReceipt` if the mode was changed.
        Raises a `ModeNotUpdated` if the mode did not change.
        """
        if self.mode == mode:
            raise ModeNotUpdated()  # already in the correct mode

        if self.mode == CaravanMode.PLANNING and mode == CaravanMode.COMPLETED:
            raise ModeNotUpdated()  # can't go from planning to completed

        receipt = ModeUpdateReceipt(
            channel=self.channel,
            old_mode=self.mode,
            new_mode=mode,
            next_place=next_unvisited_place(self.route),
            caravan_statistics=(
                CaravanStatistics.from_route(self.route)
                if mode == CaravanMode.COMPLETED else None))

        self.mode = mode

        return receipt


@dataclasses.dataclass(frozen=True)
class CaravanStop:
    place: places.Place
    visited: bool = False
    skip_reason: Optional[str] = None

    def reset(self) -> 'CaravanStop':
        return self.__class__(place=self.place)

    def visit(self, skip_reason: Optional[str] = None) -> 'CaravanStop':
        return self.__class__(
            place=self.place,
            visited=True,
            skip_reason=skip_reason)


@dataclasses.dataclass(frozen=True)
class CaravanStatistics:
    visited: int
    skipped: int
    remaining: int

    @classmethod
    def from_route(cls, route: CaravanRouteIter):
        visited, skipped, remaining = 0, 0, 0

        for s in route:
            if s.visited and s.skip_reason is None:
                visited += 1
            elif s.visited:
                skipped += 1
            else:
                remaining += 1

        return cls(visited=visited, skipped=skipped, remaining=remaining)


#
# Helper Functions
#

def ensure_unique_places(*place_iters):
    duplicate_places = tuple(
        p for p, count
        in collections.Counter(itertools.chain(*place_iters)).items()
        if count > 1)

    if duplicate_places:
        raise DuplicatePlacesException(duplicate_places)


def first_unvisited_index(caravan_route: CaravanRouteIter) -> int:
    i = 0
    for i, s in enumerate(caravan_route):
        if not s.visited:
            return i
    return i + 1


def next_unvisited_place(route: CaravanRouteIter):
    with contextlib.suppress(StopIteration):
        return next(s.place for s in route if not s.visited)


#
# Logging Helper Functions
#

def format_member(user: discord.Member, guests: int = 0) -> str:
    return f'@{user.display_name}' + ('' if guests == 0 else f' +{guests}')


def sorted_users(users: Iterable[discord.Member]) -> Iterable[discord.Member]:
    return sorted(users, key=lambda u: u.id)


def format_place(place: places.Place) -> str:
    return f'{place.name} 📍{place.location}'


def format_route(route: RouteIter) -> Iterable[str]:
    yield from (format_place(p) for p in route)


IS_METADATA_LINE = re.compile(r'^(?:\+{3}|-{3}|@{2})')


def line_diff(a: Iterable[str], b: Iterable[str]) -> str:
    a, b = tuple(a), tuple(b)

    diff_lines = difflib.unified_diff(
        a=a, b=b, fromfile='a', tofile='b', n=max(len(a), len(b)))
    diff_lines = (i.rstrip() for i in diff_lines)
    diff_lines = (i for i in diff_lines if not IS_METADATA_LINE.match(i))

    return '\n'.join(diff_lines)
