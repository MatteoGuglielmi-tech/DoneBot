# DoneBot
`DoneBot` consists in a simple implementation of a Telegram bot capable of asynchronously sending notifications to a Telegram chat based on the status of a background running process being observed.
The scope of this project is to have a tool that notifies the user about the status of a subroutine he's not directly in control of.

> Example of use case
> 
> When working remotely via ssh, it might be helpful having a pop-up notification on your mobile informing you that a long subroutine ended without the need of staring at the monitor for hours (you eyes will thank me).

## What it does
Very trivially, this bot wraps around a command issued via CLI. 
Shortly, the pipeline spawns a subprocess the bot is able to observe. Both in case of success and failure, the user is notified with a proper notification when the subroutine stops.

The only command you can issue to the Bot via Telegram chat is `/clearchat`, this allows to clear :
  - all bot messages in the chat
  - all the local record of the conversation

## Get started
To use the Bot, there are a couple of steps to take:
  1. install the dependencies in `requirements.yml` (Suggested way: `conda env create -f requirements.yml`)
  2. get your `chat_id` -> search for `@userinfobot` in Telegram, start the bot up and copy your id.
  3. create your bot -> look for `@BotFather` in Telegram, start it up and copy the token to access the HTTP API.

  > [!CAUTION]
  > Keep the `chat_id` and `bot_token` for yourself, do not share it with somebody else.

At this point, create a `.env` file in the root folder and fill it with the following sensible information:

>```.env
>BOT_TOKEN=<bot_token_from_@BotFather>
>CHAT_ID=<chat_id_from_@userinfobot>
>```


> [!NOTE]
> The Bot you just created needs to be started manually before running the python script.

## End of the story
Great, now you can receive automatic notifications for a command under observation! Enjoy!

