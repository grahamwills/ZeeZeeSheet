from __future__ import annotations

import functools
from copy import copy, deepcopy
from typing import List, Union

from placement.placed import PlacedContent
from sheet import common
from sheet.common import Margins, Rect, configured_logger
from sheet.layout.block import layout_block
from sheet.layout.section import stack_in_columns
from sheet.model import Block, Section, Sheet
from sheet.pdf import PDF

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


class SectionPlacement:
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
        LOGGER.debug("Cache info = %s", make_block_layout.cache_info())
        return self.placed

    def draw(self):
        for c in self.children:
            c.draw()

    def draw_sheet(self, pdf):
        page_index = 1
        margin = self.target.margin
        cumulative_offset = 0
        for c in self.children:
            child_bounds = c.placed.actual
            if child_bounds.bottom > cumulative_offset + self.target.pagesize[1] - margin:
                pdf.showPage()
                page_index += 1
                dy = child_bounds.top - margin
                pdf.translate(dx=0, dy=dy)
                cumulative_offset += dy
            c.draw()

        pdf.showPage()
        pdf.save()


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
        return SectionPlacement(target, children)


def layout_sheet(sheet: Sheet, pdf: PDF):
    outer = Rect(left=0, top=0, right=sheet.pagesize[0], bottom=sheet.pagesize[1]) - Margins.all_equal(sheet.margin)
    placement = make_placement(sheet, pdf)
    placement.place(outer)
    placement.draw_sheet(pdf)
