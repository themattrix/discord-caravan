# Discord Caravan Bot

A [Discord](https://discordapp.com/) bot 🤖 for managing [Pokémon GO](https://www.pokemongo.com/) raid caravans.

> Status: **not yet useful**


## Usage

    export DISCORD_BOT_TOKEN=YOUR_SECRET_TOKEN
    pipenv run python -m caravan_bot


## Contributing

Create a bot and server for testing:

1. Create a "Caravan" app in discord.
2. In the app, create a "Caravan Bot" bot.
3. Create a personal Discord server just for bot testing.
4. Paste this link into your browser, with your app's client ID in place of `YOUR_CLIENT_ID`:

        https://discordapp.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=268528640&scope=bot

    Authorize the bot to access your bot testing server.


Set up your development environment:

1. Install Python 3.7.
2. Clone this repository (or your own fork of it).
3. Install project dependencies with [pipenv](https://docs.pipenv.org/)

        pipenv install --dev


### Design Goals

- similar interface to [Meowth 2.0](https://github.com/FoglyOgly/Meowth)
- bot state should be stored purely in Discord


### TODO

- [X] skeleton Discord bot project
- [X] at bot startup, pin a welcome message to each caravan channel
- [X] on caravan channel creation, pin a welcome message to the new channel
- [X] in response to posted itinerary, update pinned message with Google Maps route
- [X] in response to posted itinerary, update pinned message with list of stops
- [X] switch pinned message to "embeds" for better formatting
- [X] allow admins to delegate caravan leaders
- [X] restrict route setting to leaders
- [X] introduce caravan modes: allow leaders to start/stop caravan
- [X] allow leaders to advance caravan (`!next` and `!skip [reason]`)
- [X] allow leaders to add a new next stop while in active mode
- [ ] cache pins
- [ ] disallow duplicate stops
- [ ] allow anyone to `!join` the caravan, optionally with guests
- [ ] warn when the attendance nears 20 for any individual gym
- [ ] allow caravan members to restrict their attendance to partial routes
- [ ] when the caravan is active, allow members to signal `!here`
- [ ] allow leaders to `!lobby`
- [ ] allow members to query the `!here` statuses with `!list`
- [ ] allow leaders to register start/stop times
- [ ] notify members one hour prior to the caravan starting of the start time and starting location
- [ ] automatically start/stop the caravan at the expected times
- [ ] Docker Compose runner


### Notes

Each Discord message has a character limit of 2000, which likely means the per-channel "pinned message" will have to be
"pinned messages". They should appear in a logical order when viewing the pins.
