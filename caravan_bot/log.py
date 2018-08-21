import logging

import discord

log = logging.getLogger('caravan')


def channel_log(channel: discord.TextChannel, level, msg):
    log.log(
        level=getattr(logging, level.upper()),
        msg=f'[{channel.guild.name}/{channel.name}] {msg}')
