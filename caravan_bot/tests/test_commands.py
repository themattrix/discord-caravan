import dataclasses

from unittest import mock

import pytest

from .. import commands


# noinspection PyTypeChecker
@pytest.mark.parametrize('msg,expected_cmd,expected_args', (
    ('!help', 'help', ''),
    ('!HELP', 'help', ''),
    ('  !!!!!   HeLp', 'help', ''),
    ('  !!!!!   HeLp    \troute\t   ', 'help', 'route'),
    ('!route \n - gym 1\n - gym 2', 'route', '- gym 1\n - gym 2'),
    ('!route\n- gym 1\n- gym 2', 'route', '- gym 1\n- gym 2'),
    ('!route - gym 1\n- gym 2', 'route', '- gym 1\n- gym 2'),
))
def test_valid_command_message_from_message(
        msg: str,
        expected_cmd: str,
        expected_args: str):

    with valid_commands(expected_cmd):
        message = FakeMessage(msg)
        cmd_msg = commands.CommandMessage.from_message(message)
        assert cmd_msg.message == message
        assert cmd_msg.name == expected_cmd
        assert cmd_msg.args == expected_args


#
# Test Helpers
#

@dataclasses.dataclass
class FakeMessage:
    content: str


def valid_commands(*names):
    return mock.patch.object(
        commands, 'commands', {c: None for c in names})
