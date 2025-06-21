import ast
import logging
import os
import sys


class CustomFormatter(logging.Formatter):
    """Logging colored formatter, adapted from https://stackoverflow.com/a/56944256/3638629"""

    """
    \001b[ Escape code, this is always the same
    1 = Style, 1 for normal, 0 = bold, 2 = underline, 3 = negative1, 4 = negative2.
    32 = Text colour, 32 for bright green.
    40m = Background colour, 40 is for black.
    """

    blue = "\u001b[38;5;69m"
    purple = "\u001b[38;5;189m"
    yellow = "\u001b[38;5;220m"
    red = "\u001b[38;5;160m"
    green = "\u001b[38;5;34m"
    bold_red = "\u001b[1m\u001b[38;5;1m"
    reset = "\u001b[0m"

    fmt = "[%(asctime)s | %(filename)s->%(funcName)s():%(lineno)s] %(levelname)s: %(message)s"
    # fmt = '| %(levelname)s | %(asctime)s | %(filename)s, lnb = %(lineno)d -> "%(message)s"'

    FORMATS = {
        logging.DEBUG: blue + fmt + reset,
        logging.INFO: purple + fmt + reset,
        logging.WARNING: yellow + fmt + reset,
        logging.ERROR: red + fmt + reset,
        logging.CRITICAL: bold_red + fmt + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


# ==== EXPORTER GLOBAL VARIABLES ====
# File handler config
try:
    os.mkdir("./misc")
except FileExistsError:
    pass

if os.path.isfile(path="./misc/app.log"):
    path = "./misc/app.log"
    filename, _ = os.path.splitext(p=path)

fh = logging.FileHandler(filename="./misc/app.log", mode="w", encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(
    fmt=logging.Formatter(
        fmt="[%(asctime)s | %(filename)s->%(funcName)s():%(lineno)s] %(levelname)s: %(message)s"
    )
)
# --------------------------------------

# Stream handler config
sh = logging.StreamHandler()
sh.setLevel(logging.DEBUG)
sh.setFormatter(CustomFormatter())
# --------------------------------------

# Logger config
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(sh)
logger.addHandler(fh)


class Formatter:
    def extract_fstring_vars(self, fmt: str) -> list[str]:
        try:
            parsed: ast.Expression = ast.parse(source=f"f'''{fmt}'''", mode="eval")
            return sorted(
                {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}
            )
        except SyntaxError:
            return []

    def extract_format_vars(self, fmt: str) -> list[str]:
        import string

        formatter = string.Formatter()
        names = set()
        for _, field_name, *_ in formatter.parse(fmt):
            if field_name:
                base_name = field_name.split(".")[0]
                names.add(base_name)
        return sorted(names)

    def safe_fprint(self, fmt: str, mode: str = "fstring", **kwargs: str) -> None:
        assert mode in {"fstring", "format"}

        used_vars: list[str] = (
            self.extract_fstring_vars(fmt=fmt)
            if mode == "fstring"
            else self.extract_format_vars(fmt=fmt)
        )
        provided_vars: list[str] = list(kwargs.keys())

        # sanity checks
        sanity_check: list[str] = list(set(provided_vars) - set(used_vars))
        if sanity_check:
            logger.warning(f"Dumping following provided variables: {sanity_check}")

        sanity_check = [var for var in used_vars if var not in kwargs]
        if sanity_check:
            raise KeyError(
                f"Not all variables in fmt have been specified: {sanity_check}"
            )

        output: str = ""
        # formatting
        if mode == "fstring":
            output = eval(f"f'''{fmt}'''", {}, kwargs)
        elif mode == "format":
            output = fmt.format(**kwargs)

        sys.stdout.write("\r" + output)
        sys.stdout.flush()
