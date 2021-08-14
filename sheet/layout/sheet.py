from __future__ import annotations

import functools
from copy import copy
from typing import List, Union

from sheet import common
from sheet.common import Margins, Rect, configured_logger
from sheet.layout.block import layout_block
from sheet.layout.section import stack_in_columns
from sheet.model import Block, Section, Sheet
from sheet.pdf import PDF
from sheet.placement.placed import PlacedContent, PlacedGroupContent

LOGGER = configured_logger(__name__)


@functools.lru_cache
def make_block_layout(target: Block, width: int, pdf: PDF) -> PlacedContent:
    rect = Rect(left=0, top=0, width=width, height=1000)
    return layout_block(target, rect, pdf)


class BlockPlacement:
    target: Block
    pdf: PDF

    # Placed
    placed: PlacedContent

    def __init__(self, target: Block, context: PDF):
        self.pdf = context
        self.padding = target.padding
        self.target = target

    def __str__(self):
        return "§ content=%s" % self.target

    def place(self, bounds: Rect) -> PlacedContent:
        base = copy(make_block_layout(self.target, bounds.width, self.pdf))
        base.move(dx=bounds.left - base.actual.left, dy=bounds.top - base.actual.top)
        # base.requested = bounds
        self.placed = base
        return base

    def draw(self):
        self.placed.draw()

    def __call__(self, bounds: Rect) -> PlacedContent:
        return self.place(bounds)


class _SectionPlacement:
    target: Union[Section, Sheet]
    children: List
    padding: int
    placed: PlacedContent

    def __init__(self, target: Section, children: List):
        self.target = target
        self.children = children
        self.method = choose_method(target.layout_method)

    def __str__(self):
        return "%s(%d children)" % (type(self.target).__name__, len(self.children))

    def place(self, bounds: Rect) -> PlacedContent:
        self.placed = self.method(bounds, self.children, self.target.padding)
        LOGGER.info("Placed %s: %s", self, self.placed)
        if hasattr(make_block_layout, 'cache_info'):
            LOGGER.debug("Cache info = %s", make_block_layout.cache_info())
            make_block_layout.cache_clear()
        return self.placed

    def draw(self):
        self.placed.draw()


def choose_method(method: common.Command):
    if method.command == 'stack':
        return functools.partial(stack_in_columns, **method.options)
    else:
        raise ValueError("unknown layout method for section: '%s'" % method.command)


def make_placement(target: Union[Block, Section, Sheet], pdf: PDF):
    if isinstance(target, Block):
        return BlockPlacement(target, pdf)
    else:
        children = [make_placement(item, pdf) for item in target.content]
        return _SectionPlacement(target, children)


def analyze_placement(p: PlacedContent, depth=0):
    print('..' * depth, p)
    print('..' * depth, "  PLACE -> bad=%s, ok=%s, unused=%s, var=%s" %
          (p.bad_breaks, p.ok_breaks, p.unused_width, p.internal_variance))
    try:
        for c in p.group:
            analyze_placement(c, depth + 1)
    except:
        pass


def place_section(bounds: Rect, section: Section, pdf: PDF) -> PlacedContent:
    children = [BlockPlacement(block, pdf) for block in section.content]
    placed = stack_in_columns(bounds, children, section.padding, **section.layout_method.options)
    LOGGER.info("Placed %s", section)
    if hasattr(make_block_layout, 'cache_info'):
        LOGGER.debug("Cache info = %s", make_block_layout.cache_info())
        make_block_layout.cache_clear()
    return placed



def place_sheet(sheet: Sheet, bounds: Rect, pdf: PDF) -> PlacedGroupContent:
    children = [functools.partial(place_section, section=section, pdf=pdf) for section in sheet.content]
    return stack_in_columns(bounds, children, sheet.padding)


def draw_sheet(sheet: Sheet, sections: List[PlacedContent], pdf):
    page_index = 1
    margin = sheet.margin
    cumulative_offset = 0
    for section in sections:
        section_bounds = section.actual
        if section_bounds.bottom > cumulative_offset + sheet.pagesize[1] - margin:
            pdf.showPage()
            page_index += 1
            dy = section_bounds.top - margin
            pdf.translate(dx=0, dy=dy)
            cumulative_offset += dy
        section.draw()

    pdf.showPage()
    pdf.save()


def layout_sheet(sheet: Sheet, pdf: PDF):
    outer = Rect(left=0, top=0, right=sheet.pagesize[0], bottom=sheet.pagesize[1]) - Margins.all_equal(sheet.margin)
    top = place_sheet(sheet, outer, pdf)
    draw_sheet(sheet, top.group, pdf)
    # analyze_placement(top)
