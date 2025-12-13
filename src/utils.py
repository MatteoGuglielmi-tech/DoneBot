import json
from typing import Any
from pathlib import Path

from dotenv import dotenv_values


def UNUSED(var: Any) -> None:
    _ = var
    del _


def get_env_variables() -> dict[str, str]:
    return dotenv_values()


def load_config(pth: str|Path) -> dict[str,Any]:
    with open(file=pth, mode="r", encoding="utf-8") as json_file:
        return json.load(json_file)


def format_duration(seconds: float) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    days, hours = divmod(int(minutes), 24)

    return f"{days}d {hours:02d}:{minutes:02d}:{secs:05.2f}"

