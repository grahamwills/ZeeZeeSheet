from __future__ import annotations

import functools
from typing import List, Union

import common
from common import Margins, Rect, configured_logger
from layout.block import BlockLayout
from layout.section import stack_in_columns
from model import Block, Section, Sheet
from pdf import PDF
from render import PlacedContent

LOGGER = configured_logger(__name__)


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
        layout = BlockLayout(self.target, bounds, self.pdf)
        self.placed = layout.layout()
        return self.placed

    def draw(self):
        self.placed.draw(self.pdf)


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
        return self.placed

    def draw(self):
        for c in self.children:
            c.draw()

    def draw_sheet(self, pdf):
        page_index = 1
        margin = self.target.margin
        cumulative_offset = 0
        for c in self.children:
            child_bounds = c.placed.bounds
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
