import logging
from typing import Tuple

import pytest

from .. import place_graph
from .. import places


#
# Test Helpers
#

def p(name='My Place', location='0,0'):
    return places.Place(name=name, location=location)


def fp(place, certainty=1.0):
    return places.FuzzyPlace(certainty=certainty, place=place)


#
# Tests
#

@pytest.mark.parametrize('nodes,expected_result', (
    # No places, empty path.
    ((), ()),

    # One starting place, obvious choice.
    (((fp(p()),),), (p(),)),

    # If multiple starting places are given (but nothing else), the path should
    # simply be the place with the highest certainty.
    (((fp(p('a'), 0.), fp(p('b'), 1.), fp(p('c'), .5)),), (p('b'),)),

    #  a
    #  |
    #  b
    #
    (((fp(p('a', '0,0')),),
      (fp(p('b', '1,1')),),
      ),
     (p('a', '0,0'),
      p('b', '1,1'),
      )),

    # a1  a2  a3
    #     |
    # b1  b2  b3
    #     |
    #     c2
    #
    (((fp(p('a1', '0,0')), fp(p('a2', '1,0')), fp(p('a3', '2,0'))),
      (fp(p('b1', '0,1')), fp(p('b2', '1,1')), fp(p('b3', '2,1'))),
      (fp(p('c2', '1,2')),),
      ),
     (p('a2', '1,0'),
      p('b2', '1,1'),
      p('c2', '1,2'),
      )),

    # a1  a2  a3
    #   \
    # b1  b2  b3
    #       \
    # c1  c2  c3
    #
    (((fp(p('a1', '0,0'), 1.), fp(p('a2', '1,0'), .5), fp(p('a3', '2,0'), .5)),
      (fp(p('b1', '0,1'), .5), fp(p('b2', '1,1'), 1.), fp(p('b3', '2,1'), .5)),
      (fp(p('c1', '0,2'), .5), fp(p('c2', '1,2'), .5), fp(p('c3', '2,2'), 1.)),
      ),
     (p('a1', '0,0'),
      p('b2', '1,1'),
      p('c3', '2,2'),
      )),

    #     a2
    #     |
    # b1  b2  b3
    #     |
    #     c2
    #
    (((fp(p('a2', '1,0'), 1.),),
      (fp(p('b1', '0,1'), .8), fp(p('b2', '1,1'), .7), fp(p('b3', '2,1'), .9)),
      (fp(p('c2', '1,2'), 1.),),
      ),
     (p('a2', '1,0'),
      p('b2', '1,1'),
      p('c2', '1,2'),
      )),

    #     a2
    #       \
    # b1  b2  b3
    #       /
    #     c2
    #
    (((fp(p('a2', '1,0'), 1.),),
      (fp(p('b1', '0,1'), .8), fp(p('b2', '1,1'), 0.), fp(p('b3', '2,1'), .9)),
      (fp(p('c2', '1,2'), 1.),),
      ),
     (p('a2', '1,0'),
      p('b3', '2,1'),
      p('c2', '1,2'),
      )),

    # a
    # b
    # c a
    #
    (((fp(p('a', '0,0')),),
      (fp(p('b', '0,1')),),
      (fp(p('c', '0,2')), fp(p('a', '0,0')),),
      ),
     (p('a', '0,0'),
      p('b', '0,1'),
      p('c', '0,2'),
      )),

    # a1 b1 c1
    # a2 b2 c2
    # a2 b2 c2
    #
    (((fp(p('a', '0,0'), .7), fp(p('b', '0,1'), .5), fp(p('c', '0,2'), 1.)),
      (fp(p('a', '0,0'), .6), fp(p('b', '0,1'), .4), fp(p('c', '0,2'), 1.)),
      (fp(p('a', '0,0'), .5), fp(p('b', '0,1'), .5), fp(p('c', '0,2'), 1.)),
      ),
     (p('a', '0,0'),
      p('c', '0,2'),
      p('b', '0,1'),
      )),

    # a
    # a b c
    # a b
    #
    (((fp(p('a', '0,0')),),
      (fp(p('a', '0,0')), fp(p('b', '0,1')), fp(p('c', '0,2'))),
      (fp(p('a', '0,0')), fp(p('b', '0,1'))),
      ),
     (p('a', '0,0'),
      p('c', '0,2'),
      p('b', '0,1'),
      )),
))
def test_shortest_path(
        caplog,
        nodes: Tuple[place_graph.FuzzyPlaces, ...],
        expected_result: place_graph.Path):

    caplog.set_level(logging.DEBUG)

    assert place_graph.shortest_path(nodes) == expected_result


@pytest.mark.parametrize('nodes', (
    # a
    # a
    #
    ((fp(p('a', '0,0')),),
     (fp(p('a', '0,0')),),),

    # a
    # a a
    #
    ((fp(p('a', '0,0')),),
     (fp(p('a', '0,0')), fp(p('a', '0,0'))),),

    # a
    # b
    # a
    #
    ((fp(p('a', '0,0'), 0.9),),
     (fp(p('b', '0,1'), 1.0),),
     (fp(p('a', '0,0'), 1.0),)),

    # a
    # b a
    # a b
    #
    ((fp(p('a', '0,0')),),
     (fp(p('b', '0,1')), fp(p('a', '0,0'))),
     (fp(p('a', '0,0')), fp(p('b', '0,1')))),
))
def test_no_path_through_graph(
        caplog,
        nodes: Tuple[place_graph.FuzzyPlaces, ...]):

    caplog.set_level(logging.DEBUG)

    with pytest.raises(place_graph.NoPathThroughGraph):
        place_graph.shortest_path(nodes)
