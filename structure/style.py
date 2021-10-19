from __future__ import annotations

import warnings
from collections import OrderedDict
from copy import copy
from dataclasses import dataclass, field
from typing import Collection, Dict

from colour import Color


@dataclass
class Style:
    name: str
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

    roughness: float = None
    teeth: float = None
    rounded: float = None

    align: str = None

    sub_styles: Dict[str, Style] = field(default_factory=OrderedDict)

    def has_border(self):
        return self.borderColor is not None and self.borderWidth > 0

    def clone_using(self, style: Style) -> Style:
        return self.clone(**style.__dict__)

    def clone(self, **kwargs) -> Style:
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)

        # Ensure we do not share the sub_style dictionary
        result.sub_styles = copy(self.sub_styles)
        result.name += "*"

        for k, v in kwargs.items():
            if v is not None and k not in {'name', 'sub_styles', 'inherit'}:
                setattr(result, k, v)
        return result

    def with_fontsize(self, multiplier=None, size=None) -> Style:
        if size is not None:
            return self.clone(size=size)
        else:
            return self.clone(size=self.size * multiplier)

    def __repr__(self):
        def useful(v): return v is not None and (v or not isinstance(v, Collection))

        return 'Style(' + ", ".join('%s=%s' % (k, v) for k, v in self.__dict__.items() if useful(v)) + ')'

    def sub_style(self, name):
        return self.clone_using(self.sub_styles[name])


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

BOLD = Style('bold', inherit='---', bold=True)
ITALIC = Style('italic', inherit='---', italic=True)

DEFAULT = Style('default', inherit='---', color=Color('black'), borderWidth=0.5, font='Gotham', size=9,
                align='fill', sub_styles={'strong': BOLD, 'emphasis': ITALIC})


class Stylesheet:
    def __init__(self):
        super().__init__()
        self.items = OrderedDict([('default', DEFAULT.clone()), ('bold', BOLD.clone()), ('italic', ITALIC.clone())])
        self.define('default-title', inherit='default', align='left', size=10, color='white', background='navy',
                    border='navy')
        self.define('default-section', inherit='default')
        self.define('default-page', inherit='default')

    def define(self, name, **kwargs) -> None:
        if name in self:
            s = self.items[name]
        else:
            s = self.items[name] = Style(name)

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
                elif key in {'size', 'borderWidth', 'opacity', 'roughness', 'teeth', 'rounded'}:
                    setattr(s, key, float(value))
                elif key in {'bold', 'italic'}:
                    setattr(s, key, bool(value))
                else:
                    setattr(s, key, value)
            except ValueError:
                warnings.warn("Could not convert value '%s' to a value assignable to '%s'" % (value, k))

    def __getitem__(self, name) -> Style:
        if name in self.items:
            style = self.items[name]
            if style.inherit != '---':
                inherited = self[style.inherit or 'default']
                style = inherited.clone_using(style)
        else:
            warnings.warn("Undefined style '%s' -- using default style" % name)
            style = self.items['default']
        return style.clone()

    def __len__(self):
        return len(self.items)

    def __contains__(self, item):
        return item in self.items
