import dataclasses

from typing import Tuple, List  # noqa

from . import caravan_model
from . import place_graph
from . import places
from . import sanitize


@dataclasses.dataclass(frozen=True)
class UnknownPlaceNames(Exception):
    """Raised if the route is given with unknown place names."""
    unknown_names: Tuple[str, ...]


def get_caravan_route(
        content: str,
        all_places: places.Places,
        fuzzy: bool) -> caravan_model.CaravanRoute:

    # Ensure single-node routes start with a dash; just like multi-node routes.
    content = '- ' + content.lstrip('- ')

    # Normalize the route into an iterable of place names.
    sanitized_route_iter = sanitize.clean_route(content)
    unknown_place_names = []  # type: List[str]

    def ensure_places_are_known():
        if unknown_place_names:
            raise UnknownPlaceNames(tuple(sorted(unknown_place_names)))

    if fuzzy:
        def gen_graph():
            for node in sanitized_route_iter:
                try:
                    yield tuple(all_places.get_fuzzy(fuzzy_name=node.name))
                except places.PlaceNotFoundException:
                    unknown_place_names.append(node.name)

        graph = tuple(gen_graph())
        ensure_places_are_known()

        stops = tuple(
            caravan_model.CaravanStop(place=place)
            for place in place_graph.shortest_path(graph=graph))
    else:
        def gen_stops():
            for node in sanitized_route_iter:
                try:
                    yield caravan_model.CaravanStop(
                        place=all_places.get_exact(name=node.name),
                        visited=node.visited,
                        skip_reason=node.skip_reason)
                except places.PlaceNotFoundException:
                    unknown_place_names.append(node.name)

        stops = tuple(gen_stops())
        ensure_places_are_known()

    return stops
