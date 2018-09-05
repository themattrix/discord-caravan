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
