from __future__ import annotations

import warnings
from collections import OrderedDict
from copy import copy
from dataclasses import dataclass
from typing import Optional

from colour import Color


@dataclass
class Style:
    inherit: str = None

    color: Color = None
    opacity: float = None

    background: Color = None
    borderColor: Color = None
    borderWidth: float = None

    font: str = None
    size: float = None
    bold: bool = None
    italic: bool = None

    align: str = None

    def has_border(self):
        return self.borderColor is not None and self.borderWidth > 0

    def modify_using(self, style: Style) -> Style:
        return self.modify(**style.__dict__)

    def modify(self, **kwargs) -> Style:
        result = copy(self)
        for k, v in kwargs.items():
            if v is not None:
                setattr(result, k, v)
        return result

    def with_fontsize(self, multiplier=None, size=None) -> Style:
        s = copy(self)
        if size is not None:
            s.size = size
        if multiplier is not None:
            s.size = s.size * multiplier
        return s


DEFAULT = Style(inherit='<none>', color=Color('black'),
                borderWidth=0.5, borderColor=Color('black'), font='Gotham', size=9, align='fill')

_MAPPINGS = {
    'parent':     'inherit',
    'foreground': 'color',
    'fg':         'color',
    'fontsize':   'size',
    'family':     'font',
    'face':       'font',
    'border':     'borderColor',
    'width':      'borderWidth'
}


class Stylesheet():
    items: OrderedDict[str, Style]

    def __init__(self):
        super().__init__()
        self.items = OrderedDict([('default', DEFAULT)])
        self.define('_banner', align='left', size=10, color='white', background='navy', border='navy')
        self.define('_emphasis', italic=True)
        self.define('_strong', bold=True)

    def define(self, name, **kwargs) -> None:
        if name in self:
            s = self.items[name]
        else:
            s = self.items[name] = Style()

        for k, value in kwargs.items():
            if hasattr(Style, k):
                key = k
            elif hasattr(Style, k.lower()):
                key = k.lower
            elif k.lower() in _MAPPINGS:
                key = _MAPPINGS[k.lower()]
            else:
                warnings.warn("Unknown style key '%s'" % k)
                continue
            try:
                if key in {'color', 'background', 'borderColor'}:
                    setattr(s, key, Color(value))
                elif key in {'size', 'borderWidth', 'opacity'}:
                    setattr(s, key, float(value))
                elif key in {'bold', 'italic'}:
                    setattr(s, key, bool(value))
                else:
                    setattr(s, key, value)
            except ValueError:
                warnings.warn("Could not convert value '%s' to a value assignable to '%s'" % (value, k))

    def __getitem__(self, txt) -> Optional[Style]:
        if txt is None:
            return None
        name = txt.split(':')
        if name[0] == 'default':
            return self.items['default']
        elif name[0] in self.items:
            style = self.items[name[0]]
            if len(name) > 1:
                base = self[name[1]]
                return base.modify_using(style)
            else:
                inherited = self[style.inherit or 'default']
                return inherited.modify_using(style)
        else:
            warnings.warn("Undefined style '%s' -- using default style" % txt)
            return self.items['default']

    def __len__(self):
        return len(self.items)

    def __contains__(self, item):
        return item in self.items
