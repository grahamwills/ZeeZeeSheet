""" Contains basic functionality used everywhere """
from __future__ import annotations

import logging
import logging.config
import math
import os
from collections import namedtuple
from pathlib import Path
from typing import Dict, NamedTuple

import yaml

def _simplify(txt):
    txt = txt.strip()
    if not txt:
        return txt
    if txt[0] == '"' and txt[-1] == '"' or txt[0] == "'" and txt[-1] == "'":
        return txt[1:-1]
    else:
        return txt


def parse_options(items) -> Dict[str, str]:
    if isinstance(items, str):
        items = items.strip().split()
    options = dict()
    for o in items:
        pair = o.split('=')
        key = _simplify(pair[0])
        if len(pair) == 1:
            options[key] = 'True'
        else:
            options[key] = _simplify(pair[1])
    return options


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
    def balanced(cls, size: int) -> Margins:
        return Margins(size, size, size, size)


class Point(NamedTuple):
    x: float
    y: float

    def __add__(self, other) -> Point:
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other) -> Point:
        return Point(self.x - other.x, self.y - other.y)

    def __abs__(self) -> float:
        return (self.x ** 2 + self.y ** 2) ** 0.5

    def __neg__(self) -> Point:
        return Point(-self.x, -self.y)

    def __mul__(self, m) -> Point:
        return Point(m * self.x, m * self.y)

    def __truediv__(self, m) -> Point:
        return Point(self.x / m, self.y / m)

    def __floordiv__(self, m) -> Point:
        return Point(self.x // m, self.y // m)

    def __rmul__(self, m) -> Point:
        return Point(m * self.x, m * self.y)

    def __eq__(self, other) -> bool:
        return self.x == other.x and self.y == other.y

    def __hash__(self) -> int:
        return hash(self.x) + 17 * hash(self.y)

    def __round__(self, n=None):
        return Point(round(self.x, n), round(self.y, n))

    def to_polar(self) -> (float, float):
        """ returns θ, d """
        return math.atan2(self.y, self.x), abs(self)

    @classmethod
    def from_polar(cls, θ, d) -> Point:
        return Point(d * math.cos(θ), d * math.sin(θ))


class Extent(NamedTuple):
    x: float
    y: float


class Rect(namedtuple('Rect', 'left right top bottom')):

    @classmethod
    def make(cls, left=None, right=None, top=None, bottom=None, width=None, height=None):
        if right is None:
            right = left + width
        elif left is None:
            left = right - width
        if bottom is None:
            bottom = top + height
        elif top is None:
            top = bottom - height
        return cls(round(left), round(right), round(top), round(bottom))

    @classmethod
    def union(cls, *args):
        mix = list(args[0]) if len(args) == 1 else list(args)
        u = mix[0]
        for r in mix[1:]:
            u = Rect.make(left=min(r.left, u.left), top=min(r.top, u.top),
                          right=max(r.right, u.right), bottom=max(r.bottom, u.bottom))
        return u

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def center(self) -> Point:
        return Point((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    @property
    def extent(self) -> Extent:
        return Extent(self.width, self.height)

    def __add__(self, off: Margins) -> Rect:
        return Rect(self.left - off.left, self.right + off.right,
                    self.top - off.top, self.bottom + off.bottom)

    def __sub__(self, off: Margins) -> Rect:
        return Rect(self.left + off.left, self.right - off.right,
                    self.top + off.top, self.bottom - off.bottom)

    def __str__(self):
        return "[l=%d r=%d t=%d b=%d]" % (self.left, self.right, self.top, self.bottom)

    def move(self, *, dx=0, dy=0) -> Rect:
        return Rect(self.left + dx, self.right + dx, self.top + dy, self.bottom + dy)

    def resize(self, *, width=None, height=None) -> Rect:
        return Rect(self.left, self.right if width is None else self.left + width,
                    self.top, self.bottom if height is None else self.top + height)

    def make_column(self, *, width: int = None, left: int = None, right: int = None) -> Rect:
        if not width:
            return Rect(left, right, self.top, self.bottom)
        if not left:
            return Rect(right - width, right, self.top, self.bottom)
        return Rect(left, left + width, self.top, self.bottom)


def _consistent(low, high, size, description):
    n = (low is None) + (high is None) + (size is None)
    if n == 0 and low + size != high:
        raise ValueError("Inconsistent specification of three arguments: " + description)
    if n > 1:
        raise ValueError("Must specify at least two arguments of: " + description)
    if low is None:
        return round(high) - round(size), round(high), round(size)
    if high is None:
        return round(low), round(low) + round(size), round(size)
    if size is None:
        return round(low), round(high), round(high) - round(low)


# LOGGING #######################################################################################################

_logging_initialized = False
FINE = 8


def _initialize_logging():
    logging.FINE = FINE
    logging.addLevelName(FINE, "FINE")

    def fine(self, message, *args, **kws):
        if self.isEnabledFor(FINE):
            self._log(FINE, message, args, **kws)

    logging.Logger.fine = fine

    path = Path(__file__).parent.parent.joinpath('resources','logging.yaml')
    if os.path.exists(path):
        with open(path, 'rt') as f:
            try:
                config = yaml.safe_load(f.read())

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


def configured_logger(name: str):
    global _logging_initialized
    if not _logging_initialized:
        _initialize_logging()
        _logging_initialized = True
    return logging.getLogger(name)
