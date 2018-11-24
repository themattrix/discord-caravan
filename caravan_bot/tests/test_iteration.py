import pytest

from .. import iteration


def test_bucket():
    assert iteration.bucket(
        ('', 'a', 'b', 'c', 'd', 'ab', 'bc', 'abc', 'abcd'),
        lambda x: 'a' in x,
        lambda x: 'b' in x,
        lambda x: 'c' in x,
        lambda x: True,
        lambda x: False,
    ) == (
        ('a', 'ab', 'abc', 'abcd'),
        ('b', 'ab', 'bc', 'abc', 'abcd'),
        ('c', 'bc', 'abc', 'abcd'),
        ('', 'a', 'b', 'c', 'd', 'ab', 'bc', 'abc', 'abcd'),
        (),
    )


@pytest.mark.parametrize('choices,expected_result', (
    ((), ()),

    (((0, 1, 2),),
     ((0,), (1,), (2,),)),

    (((0, 1, 2),
      (0, 1, 2),
      (0, 1, 2)),
     ((0, 1, 2), (0, 2, 1),
      (1, 0, 2), (1, 2, 0),
      (2, 0, 1), (2, 1, 0))),

    (((0,),
      (0, 1),
      (0, 1, 2)),
     ((0, 1, 2),)),

    (((0, 1, 2),
      (0, 1),
      (0,)),
     ((2, 1, 0),)),

    (((0,),
      (0, 1),
      (0, 1, 2),
      (0, 1, 2, None),
      (0, 1, 2, None)),
     ((0, 1, 2, None, None),)),

    (((0, 1, 2, None),
      (0, 1, 2, None),
      (0, 1, 2),
      (0, 1),
      (0,)),
     ((None, None, 2, 1, 0),)),

    (((0, 1, 2),
      (0, 1, 2, None),
      (0, 1, None),
      (0,)),
     ((1, 2, None, 0),
      (1, None, None, 0),
      (2, 1, None, 0),
      (2, None, 1, 0),
      (2, None, None, 0))),

    (((None,),),
     ((None,),)),

    (((None, None, None),),
     ((None,), (None,), (None,))),

    (((None,),
      (None,),
      (None,)),
     ((None, None, None),)),

    (((0, 1),
      (),
      (0, 1)),
     ()),
))
def test_unique_product(choices, expected_result):
    assert tuple(iteration.unique_product(choices)) == expected_result
