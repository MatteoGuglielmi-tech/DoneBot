# DoneBot
`DoneBot` consists in a simple implementation of a Telegram bot capable of asynchronously sending notifications to a Telegram chat based on the status of a background running process.  
The scope of this project is to have a tool that notifies the user about the status of a subroutine he's not directly in control of.

> Example of use case
> 
> When working remotely via ssh, it might be helpful having a pop-up notification on your mobile informing you that a long subroutine ended without the need of staring at the monitor for hours (your eyes will thank me).

## What it does
Very trivially, this bot wraps around a command issued via CLI.  
Shortly, the pipeline spawns a subprocess the bot is able to observe. Both in case of success and failure, the user is notified with a proper notification when the subroutine stops.

The commands you can issue to the Bot via Telegram chat are:
  - `/clearchat`, this allows to clear:
    - all user messages in the chat (to fully clear the convo, you need to `long press the chat > delete > clear history chat`)
    - all the conversation record (either SQLite or PostgreSQL)
  - `/stats`: this allows analyse usage statistics

## Get started
To use the Bot, there are a couple of steps to take:
  1. install the dependencies in `pixi.toml` (Suggested way: clone the repository, install [pixi](https://pixi.prefix.dev/latest/) and run `cd DoneBot && pixi install`)
  2. get your `chat_id` -> search for `@userinfobot` in Telegram, start the bot up and copy your id.
  3. create your bot -> look for `@BotFather` in Telegram, start it up and copy the token to access the HTTP API.

  > [!CAUTION]
  > Keep the `chat_id` and `bot_token` for yourself, do not share it with somebody else.

By default, SQLite is used and no additional configuration is needed. If you want to use a PostgreSQL DB, you need to pass `--use_postgres` via CLI and you need to configure it.  
I personally use [Supabase](https://supabase.com). From the landing page, you can start your own project, select Python as programming language (for this project) and follow the indications for a correct configuration.

At this point, create a `.env` file in the root folder with DB (PostgreSQL only) and bot sensitive information:

>```.env
>BOT_TOKEN=<bot_token_from_@BotFather>
>CHAT_ID=<chat_id_from_@userinfobot>
># follow db configuration guide for the correct fields to add in the following
>```


> [!NOTE]
> The Bot needs to be manually started before running the python script.

## End of the story
Great, now you can receive automatic notifications for a command under observation! Enjoy!
