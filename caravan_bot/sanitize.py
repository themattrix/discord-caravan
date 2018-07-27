import re

ROUTE_LINE = re.compile(
    r'^\s*(?:-|\d+[.)]?)\s*(?P<place>.*?)\s*$',
    re.MULTILINE)

NON_PARENS = re.compile(
    r'^(?P<non_parens>.*?)\s*\(.*?\)$',
    re.MULTILINE)

USER_ID_PATTERN = re.compile(
    r'<@(?P<id>\d+)>')


def clean_route(route: str):
    it = ROUTE_LINE.finditer(route)
    it = (m.group('place') for m in it)
    it = (m.strip('\'"“‟‘‛”’"❛❜❝❞') for m in it)
    it = (NON_PARENS.sub(r'\g<non_parens>', m) for m in it)
    yield from it


def gen_user_ids(content: str):
    it = USER_ID_PATTERN.finditer(content)
    it = (i.group('id') for i in it)
    it = (int(i) for i in it)
    yield from it
