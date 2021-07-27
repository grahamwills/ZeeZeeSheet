from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, OrderedDict, Tuple

from colour import Color

import common

BLACK = Color('black')


@dataclass
class Style:
    font: str = None
    align: str = None
    size: float = None
    color: Color = None
    background: Color = None
    borderColor: Color = None
    borderWidth: float = 0.5

    def has_border(self):
        return self.borderColor is not None and self.borderWidth > 0


class ElementType(Enum):
    TEXT = 0
    CHECKBOX = 1
    DIVIDER = 2
    SPACER = 3


@dataclass
class Element:
    which: ElementType
    value: str = None
    style: str = None
    modifiers: str = None

    def __str__(self):
        if self.which == ElementType.CHECKBOX:
            if self.value in {'O', 'o', ' ', '0'}:
                return '☐'
            else:
                return '☒'
        if self.which == ElementType.DIVIDER:
            return '●'
        if self.which == ElementType.SPACER:
            return '⋯'

        has_style = self.style and self.style != 'default'

        if has_style and self.modifiers:
            return "<%s|%s-%s>" % (self.value, self.style, self.modifiers)
        elif has_style or self.modifiers:
            return "<%s|%s>" % (self.value, (self.modifiers or self.style))
        else:
            return self.value

    def replace_style(self, style: str):
        return Element(which=self.which, value=self.value, style=style, modifiers=self.modifiers)


@dataclass
class Run:
    items: List[Element] = field(default_factory=list)

    def __str__(self):
        return " ".join(str(e) for e in self.items)

    def add(self, txt, style, modifiers):
        # Search for all the special codes
        parts = re.split(r'[ \t]*(\||--|\[[XO ]?])[ \t]*', txt)
        for p in parts:
            p = p.strip()
            if p == '|':
                self.items.append(Element(ElementType.DIVIDER))
            elif p == '--':
                self.items.append(Element(ElementType.SPACER))
            elif p.startswith('[') and p.endswith(']'):
                v = p[1] if len(p) > 2 else 'O'
                self.items.append(Element(ElementType.CHECKBOX, value=v, style=style))
            elif p:
                self.items.append(Element(ElementType.TEXT, value=p, style=style, modifiers=modifiers))

    def divide_by_spacers(self) -> List[Run]:
        divs = [-1] + [i for i, e in enumerate(self.items) if e.which in {ElementType.SPACER, ElementType.DIVIDER}] + [
            len(self.items)]
        return [Run(self.items[divs[i - 1] + 1:divs[i]]) for i in range(1, len(divs))]

    def valid(self):
        return len(self.items) > 0


@dataclass
class Block:
    title: Run = None
    content: List[Run] = field(default_factory=list)
    title_method = 'banner'
    padding: int = 4

    def add_title(self):
        self.title = Run()

    def add_txt_to_title(self, txt: str, style: str, modifiers: str):
        self.title.add(txt, style, modifiers)

    def add_content(self):
        self.content.append(Run())

    def add_txt_to_run(self, txt: str, style: str, modifiers: str):
        self.content[-1].add(txt, style, modifiers)

    def print(self):
        print("  • Block title='%s',padding=%d" % (self.title, self.padding))
        for c in self.content:
            print("     -", c)

    def __str__(self):
        return "Block('%s' with %d runs)'" % (self.title, len(self.content))

    def needs_table(self) -> bool:
        """ If dividers in any run"""
        return any(e.which in {ElementType.SPACER, ElementType.DIVIDER} for run in self.content for e in run.items)

@dataclass
class Section:
    content: List[Block] = field(default_factory=list)
    layout_method: common.Command = None
    padding: int = 4

    def add_block(self, block: Block):
        self.content.append(block)

    def print(self):
        print("  " + str(self))
        for b in self.content:
            b.print()

    def __str__(self):
        return "Section(%d blocks, layout='%s'" % (len(self.content), self.layout_method)


@dataclass
class Sheet:
    content: List[Section] = field(default_factory=list)
    styles: Dict[str, Style] = field(default_factory=OrderedDict)
    layout_method: str = common.parse_directive('stack')
    margin: int = 36
    padding: int = 4


    def print(self):
        print("Sheet margin=%d, padding=%d" % (self.margin, self.padding))
        print("  Styles:")
        for p in self.styles.items():
            print("%16s = %s" % p)
        for p in self.content:
            p.print()

    def __str__(self):
        return "Sheet(%d sections, %d styles" % (len(self.content), len(self.styles))
