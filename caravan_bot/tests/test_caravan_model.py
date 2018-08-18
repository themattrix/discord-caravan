import pytest

from .. import caravan_model


@pytest.mark.parametrize('a,b,expected_result', (
    ('', '', ''),
    ('a', 'b', '-a\n+b'),
    ('ab', 'bc', '-a\n b\n+c'),
    ('abcdef', 'b', '-a\n b\n-c\n-d\n-e\n-f'),
    ('e', 'abcdef', '+a\n+b\n+c\n+d\n e\n+f'),
))
def test_line_diff(a, b, expected_result):
    assert caravan_model.line_diff(a, b) == expected_result
