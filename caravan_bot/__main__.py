import asyncio
import os

import discord


class MyClient(discord.Client):
    async def on_ready(self):
        print(f'Logged in as "{self.user.name}" ({self.user.id})')

    async def on_message(self, message):
        # don't respond to ourselves
        if message.author == self.user:
            return

        if message.content.startswith('!test'):
            counter = 0
            tmp = await message.channel.send('Calculating messages...')
            async for msg in message.channel.history(limit=100):
                if msg.author == message.author:
                    counter += 1
            await tmp.edit(content=f'You have {counter} messages.')

        elif message.content.startswith('!sleep'):
            with message.channel.typing():
                await asyncio.sleep(5.0)
                await message.channel.send('Done sleeping.')


if __name__ == '__main__':
    client = MyClient()
    client.run(os.environ['DISCORD_BOT_TOKEN'])
