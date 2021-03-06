import collections
import dataclasses
import functools
import heapq
import itertools
import operator

from typing import (  # noqa
    Callable, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple)

from haversine import haversine

from . import iteration
from . import places
from .log import log


Cost = float
Place = places.Place
FuzzyPlace = places.FuzzyPlace
FuzzyPlaces = Tuple[FuzzyPlace, ...]
Graph = Tuple[FuzzyPlaces, ...]
Path = Tuple[Place, ...]


class NoPathThroughGraph(Exception):
    """Raised if a graph with no solution is presented."""


def shortest_path(graph: Graph) -> Path:
    if not graph:
        return ()

    if len(graph) == 1:
        return max(graph[0], key=lambda p: p.certainty).place,

    @functools.lru_cache(maxsize=None)
    def cached_edge_cost(src: FuzzyPlace, dst: FuzzyPlace) -> Cost:
        return edge_cost(src=src, dst=dst)

    try:
        return min(
            dijkstra(graph=g, cost_calculator=cached_edge_cost)
            for g in gen_unique_graphs(graph)
        ).path
    except ValueError:
        raise NoPathThroughGraph() from None


#
# Implementation Details
#

@dataclasses.dataclass(frozen=True)
class GraphRow:
    index: int
    fuzzies: FuzzyPlaces
    duplicate_places: FrozenSet[Place]

    @property
    def sort_key(self) -> Tuple[int, int]:
        return self.unique_count, len(self.duplicate_places)

    @property
    def unique_count(self) -> int:
        return len(self.place_set - self.duplicate_places)

    @property
    def place_set(self) -> FrozenSet[Place]:
        return frozenset(f.place for f in self.fuzzies)

    @property
    def duplicate_choices(self) -> Tuple[Optional[Place], ...]:
        def gen_result() -> Iterator[Optional[Place]]:
            for fuzzy in self.fuzzies:
                if fuzzy.place in self.duplicate_places:
                    yield fuzzy.place
            if self.unique_count != 0:
                yield None
        return tuple(gen_result())

    def get(self, extra_place: Optional[Place]) -> FuzzyPlaces:
        return tuple(
            fuzzy
            for fuzzy in self.fuzzies
            if fuzzy.place == extra_place
            or fuzzy.place not in self.duplicate_places)


def gen_unique_graphs(graph: Graph, limit: int = 200) -> Iterator[Graph]:
    graph = ((ROOT_PLACE,),) + graph  # type: ignore

    duplicate_places = frozenset(
        place for
        place, count in collections.Counter(
            fuzzy.place
            for group in graph
            for fuzzy in group).items()
        if count > 1)

    if not duplicate_places:
        # No duplicate places in the input graph - use as-is.
        yield graph
        return

    def duplicate_row(index: int, row_fuzzies: FuzzyPlaces) -> GraphRow:
        return GraphRow(
            index=index,
            # Sort each group of fuzzy places from most fuzzy to least fuzzy.
            # This tends to cluster the shorter (i.e., intended) routes closer
            # to the beginning of the generated graphs. We'll exploit this
            # later to
            fuzzies=tuple(sorted(
                row_fuzzies,
                key=lambda f: f.certainty,
                reverse=True)),
            duplicate_places=(
                frozenset(f.place for f in row_fuzzies) & duplicate_places))

    rows = tuple(sorted(
        (duplicate_row(index=index, row_fuzzies=group)
         for index, group in enumerate(graph)),
        key=lambda r: r.sort_key))  # type: Tuple[GraphRow, ...]

    dup_ordering_iter = iteration.unique_product(choices_iter=(
        row.duplicate_choices
        for row in rows))

    # Since the more accurate orderings are given first, we'll slice them off
    # at `limit` (default: 200) to save lots of time.
    dup_ordering_iter = itertools.islice(dup_ordering_iter, limit)

    count = 0
    for count, dup_ordering in enumerate(dup_ordering_iter):
        yield tuple(
            fuzzies
            for _, fuzzies in sorted(
                ((row.index, row.get(extra_place=dup))
                 for row, dup in zip(rows, dup_ordering)),
                key=operator.itemgetter(0)))

    log.info(f'Analyzed {count} potential graph(s).')


@dataclasses.dataclass(frozen=True, order=True)
class FoundPath:
    cost: Cost
    path: Path = dataclasses.field(compare=False)


inf = float('inf')


def dijkstra(
        graph: Graph,
        cost_calculator: Callable[[FuzzyPlace, FuzzyPlace], float]
        ) -> FoundPath:

    def get_neighbor(g: int) -> FuzzyPlaces:
        try:
            return graph[g + 1]
        except IndexError:
            return ()

    neighbors = {
        fuzzy: get_neighbor(g)
        for g, group in enumerate(graph)
        for fuzzy in group
    }  # type: Dict[FuzzyPlace, FuzzyPlaces]

    # Records the cost from the starting node (ROOT_PLACE) to every other
    # place. Initially these costs are all unknown and thus are set to
    # infinity.
    path_costs = {
        fuzzy: inf
        for group in graph
        for fuzzy in group
        if fuzzy != ROOT_PLACE
    }  # type: Dict[FuzzyPlace, float]

    # Each entry in this dictionary points to its lowest cost neighbor. After
    # the entire graph is explored, this is used to reconstruct the shortest
    # path.
    previous = {}  # type: Dict[FuzzyPlace, FuzzyPlace]

    # Priority queue containing the nodes to visit next. Each node is a 3-tuple
    # containing the path cost, an always-incrementing value, and the fuzzy
    # place to visit. The incrementing value is just to break ties in case the
    # path costs are identical between two nodes.
    counter = itertools.count()
    pq = [
        (0, next(counter), ROOT_PLACE)
    ]  # type: List[Tuple[float, int, FuzzyPlace]]

    # Only visit each node once.
    visited = set()  # type: Set[FuzzyPlace]

    while pq:
        path_cost, _, node = heapq.heappop(pq)

        if node in visited:
            continue

        visited.add(node)

        for neighbor in neighbors[node]:
            neighbor_cost = path_cost + cost_calculator(node, neighbor)

            if neighbor_cost < path_costs[neighbor]:
                path_costs[neighbor] = neighbor_cost
                previous[neighbor] = node
                heapq.heappush(pq, (neighbor_cost, next(counter), neighbor))

    dst = min(graph[-1], key=lambda v: path_costs[v])

    def gen_reversed_path() -> Iterator[Place]:
        v = dst
        while v != ROOT_PLACE:
            yield v.place
            v = previous[v]

    return FoundPath(
        cost=path_costs[dst],
        path=tuple(reversed(tuple(gen_reversed_path()))))


ROOT_PLACE = places.FuzzyPlace(
    certainty=1.,
    place=places.Place(name='', location=''))


def edge_cost(src: FuzzyPlace, dst: FuzzyPlace) -> Cost:
    # The cost from or to ROOT_PLACE is always 0.
    if ROOT_PLACE in (src, dst):
        return 0

    # The edge cost should balance the physical (Haversine) distance with the
    # certainty that the place names are correct. A low-cost edge will have
    # both places located close together with highly-certain names.
    certainty = src.certainty * dst.certainty
    return inf if certainty == 0 else (
        haversine(src.place.lat_long, dst.place.lat_long) / certainty)
