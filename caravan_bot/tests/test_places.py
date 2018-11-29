from .. import places


def test_alias_matching():
    all_places = places.Places.from_dict(raw_places={
        'City Clock': {
            'location': '0,0',
            'aliases': [
                'town center clock',
                'tall clock']},
        'Angel Statue': {
            'location': '1,0',
            'aliases': [
                'weeping angel',
                "don't blink"]},
    })

    assert frozenset(all_places.get_fuzzy(
        fuzzy_name='clock',
        score_cutoff=60,
        soft_limit=3
    )) == frozenset((
        places.FuzzyPlace(certainty=.9, place=places.Place(
            name='City Clock', location='0,0')),
    ))

    assert frozenset(all_places.get_fuzzy(
        fuzzy_name='weeping angel',
        score_cutoff=60,
        soft_limit=3
    )) == frozenset((
        places.FuzzyPlace(certainty=1., place=places.Place(
            name='Angel Statue', location='1,0')),
    ))


def test_score_cutoff():
    place_names = (
        'aaaaaaaaaa',
        'baaaaaaaaa',
        'bbaaaaaaaa',
        'bbbaaaaaaa',
        'bbbbaaaaaa',
        'bbbbbaaaaa',
        'bbbbbbaaaa',
        'bbbbbbbaaa',
        'bbbbbbbbaa',
        'bbbbbbbbba',
        'bbbbbbbbbb',
    )

    all_places = places.Places.from_dict(raw_places={
        name: {'location': '0,0'} for name in place_names
    })

    for cutoff in range(11):
        assert frozenset(f.place.name for f in all_places.get_fuzzy(
            fuzzy_name='aaaaaaaaaa',
            score_cutoff=cutoff * 10,
            soft_limit=len(place_names)
        )) == frozenset(place_names[:11 - cutoff])


def test_exceeding_soft_limit():
    all_places = places.Places.from_dict(raw_places={
        'City Clock': {'location': '0,0'},
        'Other Clock Tower': {'location': '9,9'},
        'Angel Statue': {'location': '1,0'},
        'First Church': {'location': '1,1'},
        'Second Church': {'location': '1,2'},
        'Third Church': {'location': '1,3'},
        'Fourth Church': {'location': '1,4'},
        'Fifth Church': {'location': '1,5'},
        'Sixth Church': {'location': '1,6'},
        'Church of the Seventh': {'location': '1,7'},
    })

    # Although the soft limit is 3, the fuzzy matcher will continue to yield
    # results until the score drops. In this case, all churches match "church"
    # with a 90% accuracy, so all churches are returned. Each one is equally
    # likely to be the correct match.
    assert frozenset(all_places.get_fuzzy(
        fuzzy_name='Church',
        score_cutoff=0,
        soft_limit=3)
    ) == frozenset((
        places.FuzzyPlace(certainty=.9, place=places.Place(
            name='First Church', location='1,1')),
        places.FuzzyPlace(certainty=.9, place=places.Place(
            name='Second Church', location='1,2')),
        places.FuzzyPlace(certainty=.9, place=places.Place(
            name='Third Church', location='1,3')),
        places.FuzzyPlace(certainty=.9, place=places.Place(
            name='Fourth Church', location='1,4')),
        places.FuzzyPlace(certainty=.9, place=places.Place(
            name='Fifth Church', location='1,5')),
        places.FuzzyPlace(certainty=.9, place=places.Place(
            name='Sixth Church', location='1,6')),
        places.FuzzyPlace(certainty=.9, place=places.Place(
            name='Church of the Seventh', location='1,7')),
    ))
