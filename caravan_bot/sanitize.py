import dataclasses
import re
import string

from typing import Match, Optional, Iterable

ROUTE_LINE = re.compile(
    r'^\s*'
    r'(?:-|\d+[.)]?)\s*'
    r'(?P<strikethrough>(?:~~)?)'
    r'(?P<place>.*?)'
    r'(?P=strikethrough)\s*'
    r'(?:\(.*?\)\s*)?'
    r'(?P<skipped>—\s*_?skipped(?::\s*"(?P<skip_reason>.*?)")?_?\s*)?'
    r'$',
    re.MULTILINE | re.IGNORECASE)

USER_ID_PATTERN = re.compile(
    r'<@!?(?P<id>\d+)>')

QUOTES_AND_WHITESPACE = '\'"“‟‘‛”’"❛❜❝❞' + string.whitespace


def clean_route(route: str) -> Iterable['RouteNode']:
    matches = ROUTE_LINE.finditer(route)
    nodes = (RouteNode.from_match(m) for m in matches)
    named_nodes = (n for n in nodes if n.name)
    yield from named_nodes


@dataclasses.dataclass
class RouteNode:
    name: str
    visited: bool
    skip_reason: Optional[str]

    @classmethod
    def from_match(cls, match: Match) -> 'RouteNode':
        place = match.group('place').strip(QUOTES_AND_WHITESPACE)
        visited = bool(match.group('strikethrough'))
        skipped = match.group('skipped') is not None
        skip_reason = match.group('skip_reason') or ('' if skipped else None)
        return cls(name=place, visited=visited, skip_reason=skip_reason)


def gen_user_ids(content: str) -> Iterable[int]:
    matches = USER_ID_PATTERN.finditer(content)
    id_strings = (m.group('id') for m in matches)
    ids = (int(i) for i in id_strings)
    yield from ids
