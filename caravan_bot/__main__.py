"""Discord Caravan Bot

Usage:
  caravan_bot --gyms=JSON [--server-filter=REGEX] [--channel-filter=REGEX]
  caravan_bot (-h | --help)
  caravan_bot --version

Options:
  -h --help                 Show this screen.
  --version                 Show version.
  --gyms=JSON               JSON file containing gyms names, coordinates, and
                            optional aliases.
  --server-filter=REGEX     Restrict bot to servers matching this pattern
                            [default: .*].
  --channel-filter=REGEX    Restrict bot to channels matching this pattern
                            [default: .*caravan.*].
"""

import os
import logging
import pathlib
import re
import sys

from .log import log
from . import client
from . import places

import docopt


def main():
    args = docopt.docopt(__doc__, version='1.0.0')

    try:
        server_re = re.compile(args['--server-filter'], re.IGNORECASE)
        channel_re = re.compile(args['--channel-filter'], re.IGNORECASE)
    except re.error as e:
        log.critical(
            f'The provided regular expression is invalid: {e}')
        return 1

    try:
        client.CaravanClient(
            gyms=places.Places.from_json(pathlib.Path(args['--gyms'])),
            server_re=server_re,
            channel_re=channel_re,
        ).run(
            os.environ['DISCORD_BOT_TOKEN']
        )
    except KeyError as e:
        log.critical(
            f'The following environment variable must be set: {e.args[0]}')
        return 2
    else:
        return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
