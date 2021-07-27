""" Contains basic functionality used everywhere """
from __future__ import annotations

import logging
import logging.config
import os
from collections import namedtuple
from pathlib import Path
from typing import Any, Dict, NamedTuple

import yaml
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas


class Directive(Dict):
    name: str

    def __init__(self, text: str):
        parts = text.split()
        self.name = parts[0].strip().lower()
        pairs = {tuple(p.split("=")) for p in parts[1:]}
        super().__init__(pairs)

class Margins(NamedTuple):
    left: int
    right: int
    top: int
    bottom: int

    def horizontal(self) -> int:
        return self.left + self.right

    def vertical(self) -> int:
        return self.top + self.bottom

    def __str__(self):
        return "[l=%d, r=%d, t=%d, b=%d]" % self

    @classmethod
    def simple(cls, size: int) -> Margins:
        return Margins(size, size, size, size)



class Rect(namedtuple('Rect', 'left right top bottom width height')):

    @classmethod
    def union(cls, *args):
        all = list(args[0]) if len(args) == 1 else list(args)
        u = all[0]
        for r in all[1:]:
            u = Rect(left=min(r.left, u.left), top=min(r.top, u.top),
                     right=max(r.right, u.right), bottom=max(r.bottom, u.bottom))
        return u

    def __new__(cls, left=None, right=None, top=None, bottom=None, width=None, height=None):
        left, right, width = _consistent(left, right, width, "left, right, width")
        top, bottom, height = _consistent(top, bottom, height, "top, bottom, height")
        return super().__new__(cls, left, right, top, bottom, width, height)

    def __add__(self, off: Margins) -> Rect:
        return Rect(left=self.left - off.left,
                    right=self.right + off.right,
                    top=self.top - off.top,
                    bottom=self.bottom + off.bottom,
                    )

    def __sub__(self, off: Margins) -> Rect:
        return Rect(left=self.left + off.left,
                    right=self.right - off.right,
                    top=self.top + off.top,
                    bottom=self.bottom - off.bottom,
                    )

    def __str__(self):
        return "[l=%d, r=%d, t=%d, b=%d]" % (self.left, self.right, self.top, self.bottom)

    def valid(self) -> bool:
        return self.left <= self.right and self.top <= self.bottom

    def move(self, *, dx=0, dy=0) -> Rect:
        return Rect(left=self.left + dx, top=self.top + dy, width=self.width, height=self.height)

    def resize(self, *, width=None, height=None) -> Rect:
        return Rect(left=self.left, top=self.top,
                    width=self.width if width is None else width,
                    height=self.height if height is None else height)

def _consistent(low, high, size, description):
    n = (low is None) + (high is None) + (size is None)
    if n == 0 and low + size != high:
        raise ValueError("Inconsistent specification of three arguments: " + description)
    if n > 1:
        raise ValueError("Must specify at least two arguments of: " + description)
    if low is None:
        return high - size, high, size
    if high is None:
        return low, low + size, size
    if size is None:
        return low, high, high - low


# LOGGING #######################################################################################################

_logging_initialized = False


def _initialize_logging():
    path = Path(__file__).parent.joinpath('resources/logging.yaml')
    if os.path.exists(path):
        with open(path, 'rt') as f:
            try:
                config = yaml.safe_load(f.read())

                # Modify to set the console log level
                console_log_level = os.environ.get("CONSOLE_LOG_LEVEL", None)
                if console_log_level:
                    config['handlers']['console']['level'] = console_log_level

                # Ensure the log file directory exists
                log_file = Path(config['handlers']['file']['filename'])
                os.makedirs(log_file.parent, exist_ok=True)

                logging.config.dictConfig(config)
                return
            except Exception as e:
                print(e)
                print('Error in Logging Configuration. Using default configs')
    else:
        print('Failed to load configuration file. Using default configs')
    logging.basicConfig(level=logging.INFO)


def configured_logger(name: str):
    global _logging_initialized
    if not _logging_initialized:
        _initialize_logging()
        _logging_initialized = True
    return logging.getLogger(name)
