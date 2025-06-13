from typing import Any

from dotenv import dotenv_values


def UNUSED(var: Any) -> None:
    _ = var
    del _


def get_env_variables(pth: str = "") -> dict[str, str]:
    # ==== LOAD CONFIG ====
    return dotenv_values() if not pth else dotenv_values(pth)
