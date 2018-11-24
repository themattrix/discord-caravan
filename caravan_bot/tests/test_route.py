import logging

from .. import caravan_model
from .. import places
from .. import route


def test_simple_exact_route(caplog):
    caplog.set_level(logging.DEBUG)

    actual_route = route.get_caravan_route(
        content=(
            '- ~~a~~\n'
            '- ~~b~~ — skipped: "no parking"\n'
            '- ~~d~~ — skipped\n'
            '- e\n'),
        all_places=places.Places.from_dict(raw_places={
            'a': {'location': '0,0'},
            'b': {'location': '1,0'},
            'c': {'location': '1,1'},
            'd': {'location': '2,1'},
            'e': {'location': '2,2'},
        }),
        fuzzy=False)

    assert actual_route == (
        caravan_model.CaravanStop(
            place=places.Place(name='a', location='0,0'),
            visited=True,
            skip_reason=None),
        caravan_model.CaravanStop(
            place=places.Place(name='b', location='1,0'),
            visited=True,
            skip_reason='no parking'),
        caravan_model.CaravanStop(
            place=places.Place(name='d', location='2,1'),
            visited=True,
            skip_reason=''),
        caravan_model.CaravanStop(
            place=places.Place(name='e', location='2,2'),
            visited=False,
            skip_reason=None))


def test_simple_fuzzy_route(caplog):
    caplog.set_level(logging.DEBUG)

    actual_route = route.get_caravan_route(
        content=(
            '- aaaaaaaaab\n'
            '- bbbbbbbbbc\n'
            '- ddddddddde\n'),
        all_places=places.Places.from_dict(raw_places={
            'aaaaaaaaaa': {'location': '0,0'},
            'bbbbbbbbbb': {'location': '1,0'},
            'cccccccccc': {'location': '1,1'},
            'dddddddddd': {'location': '2,1'},
        }),
        fuzzy=True)

    assert tuple(s.place.name for s in actual_route) == (
        'aaaaaaaaaa',
        'bbbbbbbbbb',
        'dddddddddd')


def test_location_aware_fuzzy_route(caplog):
    caplog.set_level(logging.DEBUG)

    actual_route = route.get_caravan_route(
        content=(
            '- clock tower\n'
            '- angel\n'
            '- church\n'),
        all_places=places.Places.from_dict(raw_places={
            'City Clock': {'location': '0,0'},
            'Other Clock Tower': {'location': '10,10'},
            'Angel Statue': {'location': '1,0'},
            'First Church': {'location': '1,1'},
        }),
        fuzzy=True)

    assert tuple(s.place.name for s in actual_route) == (
        'City Clock',
        'Angel Statue',
        'First Church')
