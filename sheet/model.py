from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from colour import Color
from reportlab.lib.pagesizes import letter
from reportlab.lib.rl_accel import unicode2T1
from reportlab.lib.units import cm, inch, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import Font

from sheet import common
from style import Stylesheet

BLACK = Color('black')

HELVETICA: Font = pdfmetrics.getFont('Helvetica')


class ElementType(Enum):
    TEXT = 0
    SYMBOL = 1
    CHECKBOX = 2
    DIVIDER = 3
    SPACER = 4


@dataclass
class Element:
    which: ElementType
    value: str = None
    style: str = None

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

        if has_style:
            return "<%s|%s>" % (self.value, self.style)
        else:
            return self.value

    def replace_style(self, style: str):
        return Element(which=self.which, value=self.value, style=style)


@dataclass
class Run:
    items: List[Element] = field(default_factory=list)

    def __str__(self):
        return " ".join(str(e) for e in self.items)

    def add(self, txt, style) -> Run:
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
                self.items.append(Element(ElementType.TEXT, value=p, style=style))
        return self

    def valid(self):
        return len(self.items) > 0

    def base_style(self) -> Optional[str]:
        #  Lazy, just use the first
        for item in self.items:
            if item.style:
                return item.style
        return None

    def fixup(self):
        self.items = _ensure_representable(self.items)


@dataclass
class Block:
    title: Optional[Run] = None
    content: List[Run] = field(default_factory=list)
    image: Dict[str, str] = field(default_factory=dict)
    block_method: common.Directive = common.parse_directive('default')
    title_method: common.Directive = common.parse_directive('banner')
    margin: int = 4
    padding: int = 2

    def add_title(self):
        self.title = Run()

    def add_content(self):
        self.content.append(Run())

    def print(self):
        print("  • Block title='%s',padding=%d" % (self.title, self.padding))
        for c in self.content:
            print("     -", c)
        if self.image:
            print("     - Image('%s')" % self.image['uri'])

    def __str__(self):
        if self.image:
            return "Block('%s' with image '%s')" % (self.title, self.image['uri'])
        else:
            return "Block('%s' with %d runs)" % (self.title, len(self.content))

    def needs_table(self) -> bool:
        """ If dividers in any run"""
        return any(e.which in {ElementType.SPACER, ElementType.DIVIDER} for run in self.content for e in run.items)

    def __hash__(self):
        return id(self)

    def fixup(self, parent: Section):
        if self.title:
            self.title.fixup()
        if self.content:
            for r in self.content:
                r.fixup()
        elif not self.image:
            if self.title:
                # Move the title to the content
                self.content = [self.title]
                self.title = None
            else:
                # Nothing is defined so kill this
                parent.content.remove(self)

    def base_style(self) -> Optional[str]:
        #  Lazy, just use the first
        for item in self.content:
            s = item.base_style()
            if s:
                return s
        return None

    def __len__(self):
        return len(self.content)

    def __getitem__(self, item):
        return self.content[item]


@dataclass
class Section:
    content: List[Block] = field(default_factory=list)
    layout_method: common.Directive = common.parse_directive("banner style=_banner")
    padding: int = 4

    def add_block(self, block: Block):
        self.content.append(block)

    def print(self):
        print("  " + str(self))
        for b in self.content:
            b.print()

    def __str__(self):
        return "Section(%d blocks, layout='%s')" % (len(self.content), self.layout_method)

    def fixup(self, parent: Sheet):
        for c in self.content:
            c.fixup(self)
        if not self.content:
            parent.content.remove(self)

    def __len__(self):
        return len(self.content)

    def __getitem__(self, item):
        return self.content[item]


def _to_size(txt: str) -> int:
    if txt.endswith('in'):
        return round(float(txt[:-2]) * inch)
    if txt.endswith('mm'):
        return round(float(txt[:-2]) * mm)
    if txt.endswith('cm'):
        return round(float(txt[:-2]) * cm)
    if txt.endswith('px') or txt.endswith('pt'):
        return round(float(txt[:-2]))
    return int(txt)


@dataclass
class Sheet:
    content: List[Section] = field(default_factory=list)
    stylesheet: Stylesheet = field(default_factory=Stylesheet)
    layout_method: str = common.parse_directive('stack')
    pagesize: (int, int) = letter
    margin: int = 36
    padding: int = 8

    def __str__(self):
        return "Sheet(%d sections, %d styles)" % (len(self.content), len(self.stylesheet))

    def fixup(self):
        for c in self.content:
            c.fixup(self)

    def apply_styles(self, margin=None, padding=None, size=None):
        if margin:
            self.margin = _to_size(margin)
        if padding:
            self.padding = _to_size(padding)
        if size:
            pair = size.split('x')
            self.pagesize = (_to_size(pair[0]), _to_size(pair[1]))

    def __len__(self):
        return len(self.content)

    def __getitem__(self, item):
        return self.content[item]


def _exists_in_helvetica(text):
    """ If it is not substituted, it exists """
    return unicode2T1(text, [HELVETICA])[0][0] == HELVETICA


def _ensure_representable(items: List[Element]) -> List[Element]:
    result = []
    for item in items:
        if item.which == ElementType.TEXT:
            run_start = 0
            for i, c in enumerate(item.value):
                # If helvetica doesn't support it, call it special
                if not _exists_in_helvetica(c):
                    if i > run_start:
                        result.append(Element(ElementType.TEXT, item.value[run_start:i], item.style))
                    result.append(Element(ElementType.SYMBOL, c, item.style))
                    run_start = i + 1
            if len(item.value) > run_start:
                result.append(Element(ElementType.TEXT, item.value[run_start:], item.style))
        else:
            result.append(item)

    return result
