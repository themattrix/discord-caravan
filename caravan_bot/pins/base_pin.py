import abc

import discord


class BasePin(abc.ABC):
    def __init__(self):
        self.message = None

    @property
    @abc.abstractmethod
    def content_and_embed(self):
        pass

    async def ensure_post(self, channel: discord.TextChannel):
        if not self.message:
            self.message = await channel.send(**self.content_and_embed)

    async def ensure_pin(self):
        if not self.message.pinned:
            await pin_message(self.message)

    async def flush(self):
        await self.message.edit(**self.content_and_embed)


async def pin_message(message):
    # noinspection PyProtectedMember
    await message.channel._state.http.pin_message(
        channel_id=message.channel.id,
        message_id=message.id)
