import os
import random
import re
from dataclasses import dataclass
from os import PathLike
from pathlib import Path, PurePath
from textwrap import wrap
from typing import TextIO, Union, Dict, List, Final
from unicodedata import east_asian_width


HEREDOC_PATTERN = re.compile(
    r'\$.* = <<["\']?(.*)["\']?;?(?P<the_cow>[\w\W]*)\1'
)
PERL_STRING_ASSIGNMENT = re.compile(
    r'(?:^|\n)(\$.+) = "(.+)";'
)


@dataclass
class Option:
    eyes: str = 'oo'
    tongue: str = '  '


COW_PATH = os.getenv("COWPATH")
COW_PEN: Final[Path] = (
    Path(COW_PATH)
    if COW_PATH is not None else
    (Path(__file__) / '..' / 'cows').resolve()
)

COW_OPTIONS = {
    'b': Option(eyes='=='),
    'd': Option(eyes='XX', tongue='U '),
    'g': Option(eyes='$$'),
    'p': Option(eyes='@@'),
    's': Option(eyes='**', tongue='U '),
    't': Option(eyes='--'),
    'w': Option(eyes='OO'),
    'y': Option(eyes='..'),
}


@dataclass
class Bubble:
    stem: str = '\\'
    l: str = '<'
    r: str = '>'
    tl: str = '/'
    tr: str = '\\'
    ml: str = '|'
    mr: str = '|'
    bl: str = '\\'
    br: str = '/'


THOUGHT_OPTIONS = {
    'cowsay': Bubble('\\', '<', '>', '/', '\\', '|', '|', '\\', '/'),
    'cowthink': Bubble('o', '(', ')', '(', ')', '(', ')', '(', ')'),
}

ESCAPES = {
    r'\@': '@',
    r'\$': '$',
    r'\\': '\\',
}
 
def cowsay_handler(env, args):
    print(args)

    # the_cow = get_cow(cow) if cowfile is None else cowfile
    # cow_ops = COW_OPTIONS.get(preset, Option(eyes=eyes, tongue=tongue))
    # thought_ops = THOUGHT_OPTIONS['cowsay']
    # return build_cow(message, the_cow, cow_ops, thought_ops, width, wrap_text)

