import dataclasses
import re

from typing import Callable, Dict, FrozenSet, Iterable, Tuple, Optional, List

import discord
import fuzzywuzzy.process

from .roles import Role


commands = {}  # type: Dict[str, Command]
unique_commands = []  # type: List[Command]


@dataclasses.dataclass(frozen=True)
class Command:
    names: Tuple[str, ...]
    description: str
    usage: str
    allowed_roles: FrozenSet[Role]
    preferred: str
    handler: Callable


def register(
        *cmds,
        description: str,
        usage: str = '!{cmd}',
        allowed_roles: Iterable[Role] = (Role.ANYONE,),
        preferred: Optional[str] = None):

    preferred = preferred or cmds[0]

    def decorator(fn):
        cmd = Command(
            names=tuple(cmds),
            description=description,
            usage=usage.replace('{cmd}', preferred),
            allowed_roles=frozenset(allowed_roles),
            preferred=preferred,
            handler=fn)
        unique_commands.append(cmd)
        for c in cmds:
            commands[c] = cmd
        return fn
    return decorator


COMMAND_PATTERN = re.compile(
    r'^\s*!+[ \t]*(?P<command>\w+)\b(?:[ \t]*(?P<args>.*))?',
    re.DOTALL)


class NotACommand(Exception):
    """Raised if the given message does not look like a command."""


class NoSuchCommand(Exception):
    """
    Raised if the command does not exist. Perhaps it was meant for a
    different bot.
    """


@dataclasses.dataclass(frozen=True)
class CommandSuggestion(Exception):
    """
    Raised if the command is nearly a real one.
    """
    given_command: str
    suggested_command: str
    score: int


@dataclasses.dataclass(frozen=True)
class CommandMessage:
    message: discord.Message
    name: str
    args: str

    @classmethod
    def from_message(cls, message: discord.Message):
        match = COMMAND_PATTERN.search(message.content.strip())
        if not match:
            raise NotACommand()

        return cls(
            message=message,
            name=get_command_name(match.group('command').casefold()),
            args=(match.group('args') or '').strip())


def get_command_name(name: str) -> str:
    if name in commands:
        return name

    best_match, score, *_ = fuzzywuzzy.process.extractOne(
        query=name,
        choices=commands.keys())

    if score < 75:
        raise NoSuchCommand()

    raise CommandSuggestion(
        given_command=name,
        suggested_command=best_match,
        score=score)
