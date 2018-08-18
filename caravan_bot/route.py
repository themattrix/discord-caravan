import dataclasses

from typing import Iterable, Tuple

from . import caravan_model
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

    # Ensure single-node routes start with a dash. just like multi-node routes.
    content = '- ' + content.lstrip('- ')

    unknown_place_names = []

    def gen_stops(route_nodes: Iterable[sanitize.RouteNode]):
        for node in route_nodes:
            try:
                yield caravan_model.CaravanStop(
                    place=all_places.get(name=node.name, fuzzy=fuzzy),
                    visited=node.visited,
                    skip_reason=node.skip_reason)
            except places.PlaceNotFoundException:
                unknown_place_names.append(node.name)

    stops = tuple(gen_stops(sanitize.clean_route(content)))

    if unknown_place_names:
        raise UnknownPlaceNames(tuple(sorted(unknown_place_names)))

    return stops
