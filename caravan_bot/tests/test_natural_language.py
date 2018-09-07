import pytest

from .. import natural_language


@pytest.mark.parametrize('seq,expected_result', (
    ((), ''),
    (('one',), 'one'),
    (('one', 'two'), 'one and two'),
    (('one', 'two', 'three'), 'one, two, and three'),
    (('one', 'two', 'three', 'four'), 'one, two, three, and four'),
))
def test_join(seq, expected_result):
    assert natural_language.join(seq) == expected_result


@pytest.mark.parametrize('word,collection,expected_result', (
    ('leader', '', 'leaders'),
    ('leader', '1', 'leader'),
    ('leader', '12', 'leaders'),
    ('leader', -1, 'leaders'),
    ('leader', 0, 'leaders'),
    ('leader', 1, 'leader'),
    ('leader', 2, 'leaders'),
))
def test_pluralize(word, collection, expected_result):
    assert natural_language.pluralize(
        word=word,
        collection=collection
    ) == expected_result
