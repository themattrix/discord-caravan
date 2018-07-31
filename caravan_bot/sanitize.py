import dataclasses
import re
import string

ROUTE_LINE = re.compile(
    r'^\s*(?:-|\d+[.)]?)\s*(?P<place>.*?)\s*$',
    re.MULTILINE)

NON_PARENS = re.compile(
    r'^(?P<non_parens>.*?)\s*\(.*?\)$')

USER_ID_PATTERN = re.compile(
    r'<@(?P<id>\d+)>')

# A particular route node has been visited if it has strike-through.
HAS_VISITED = re.compile(
    r'^~~.*~~$')

# Strip whitespace and quotes from around place names.
STRIP = '\'"“‟‘‛”’"❛❜❝❞' + string.whitespace


@dataclasses.dataclass
class RouteNode:
    name: str
    visited: bool


def clean_route(route: str):
    it = ROUTE_LINE.finditer(route)
    it = (m.group('place') for m in it)
    it = (NON_PARENS.sub(r'\g<non_parens>', m) for m in it)
    it = (m.strip(STRIP) for m in it)
    it = (RouteNode(name=m, visited=bool(HAS_VISITED.match(m))) for m in it)
    yield from it


def gen_user_ids(content: str):
    it = USER_ID_PATTERN.finditer(content)
    it = (i.group('id') for i in it)
    it = (int(i) for i in it)
    yield from it
