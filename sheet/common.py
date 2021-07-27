""" Contains basic functionality used everywhere """
from __future__ import annotations

import logging
import logging.config
import os
from collections import namedtuple
from dataclasses import dataclass
from numbers import Number
from pathlib import Path
from typing import Any, Dict, NamedTuple

import yaml
from reportlab.pdfgen.canvas import Canvas


class Directive(Dict):
    name: str

    def __init__(self, text: str):
        parts = text.split()
        self.name = parts[0].strip().lower()
        pairs = {tuple(p.split("=")) for p in parts[1:]}
        super().__init__(pairs)


@dataclass
class Context():
    canvas: Canvas
    page_width: int
    page_height: int
    styles: Dict[str, Any]
    debug: bool

    def __init__(self, canvas: Canvas, styles: Dict[str, Any], debug: bool = False) -> None:
        self.canvas = canvas
        self.page_width = int(canvas._pagesize[0])
        self.page_height = int(canvas._pagesize[1])
        self.styles = styles
        self.content_renderer = lambda x: None
        self.border_renderer = lambda x: None
        self.debug = debug


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


def _make_consistent(low, high, size, description):
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
        left, right, width = _make_consistent(left, right, width, "left, right, width")
        top, bottom, height = _make_consistent(top, bottom, height, "top, bottom, height")
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


_logging_initialized = False


def _initialize_logging():
    path = Path(__file__).parent.joinpath('logging.yaml')
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


class DetailedLocationFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pass

    def format(self, record: logging.LogRecord):
        #  "%(asctime)s | %(name)-24s %(funcName)-20.20s %(lineno)-3d | %(threadName)-12.12s | %(levelname)-8s | %(
        #  message)s"
        ex = ' | ' + super().formatException(record.exc_info) if record.exc_info else ''

        return "%s | %-12s | %-40s | %-8s | %s%s" % (
            self.formatTime(record),
            record.threadName,
            self.trunc(record.funcName, record.lineno, record.name, 40),
            record.levelname,
            record.getMessage(),
            ex
        )

    def join(self, name, funcName, lineno):
        txt = name + '.' + funcName + ':' + str(lineno)
        return txt, len(txt)

    def trunc(self, funcName, lineno, name, N):
        s, n = self.join(name, funcName, lineno)
        if n <= N:
            return s
        return '\u2026' + s[n - N + 1:]


def pretty(item, max_items=4, max_len=30) -> str:
    """ return a prettified string of anything"""

    if isinstance(item, Number):
        if 1000 <= abs(item) < 1e7:
            return (str(round(item)))
        return "{:.4g}".format(item)

    if isinstance(item, dict):
        return '{' + ", ".join(["%s:%s" % (pretty(p[0]), pretty(p[1])) for p in item.items()]) + "}"

    if isinstance(item, list):
        start = ", ".join(pretty(p) for p in item[:max_items])
        if len(item) > max_items:
            return "[%s, …]" % start
        else:
            return "[%s]" % start

    if isinstance(item, Path):
        return pretty(item.name)

    txt = str(item)
    if len(txt) > max_len:
        txt = txt[:max_len - 1] + '…'

    if isinstance(item, str) and ' ' in item:
        txt = "'" + txt + "'"

    return txt
