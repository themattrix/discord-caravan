import abc
import dataclasses

from typing import Optional, Dict

import discord

from ... import caravan_model


@dataclasses.dataclass  # type: ignore
class BasePin(abc.ABC):
    message: Optional[discord.Message]
    version: str = 'v1'

    @property
    @abc.abstractmethod
    def update_for(self):
        pass

    @abc.abstractmethod
    def content_and_embed(self, model: caravan_model.CaravanModel) -> Dict:
        pass

    async def update(self, receipt, model: caravan_model.CaravanModel):
        if self.message is None:
            return
        if not any(isinstance(receipt, t) for t in self.update_for):
            return
        await self.message.edit(**self.content_and_embed(model))

    async def ensure_post(
            self,
            channel: discord.TextChannel,
            model: caravan_model.CaravanModel):
        if self.message is None:
            self.message = await channel.send(**self.content_and_embed(model))

    async def ensure_pinned(self):
        if self.message is None:
            return
        if not self.message.pinned:
            await pin_message(self.message)


async def pin_message(message):
    # noinspection PyProtectedMember
    await message.channel._state.http.pin_message(
        channel_id=message.channel.id,
        message_id=message.id)
