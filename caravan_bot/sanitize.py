import re

ROUTE_LINE = re.compile(
    r'^\s*(?:-|\d+[.)]?)\s*(?P<place>.*?)\s*$',
    re.MULTILINE)

NON_PARENS = re.compile(
    r'^(?P<non_parens>.*?)\s*\(.*?\)$',
    re.MULTILINE)


def clean_route(route: str):
    i = ROUTE_LINE.finditer(route)
    i = (m.group('place') for m in i)
    i = (m.strip('\'"“‟‘‛”’"❛❜❝❞') for m in i)
    i = (NON_PARENS.sub(r'\g<non_parens>', m) for m in i)
    yield from i
