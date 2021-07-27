from __future__ import annotations
from typing import List, Tuple, Union

import common
from common import  Margins, Rect, configured_logger
from layout.block import BlockLayout
from model import Block, Section, Sheet
from pdf import PDF
from render import PlacedContent, empty_content

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

    def place(self, bounds: Rect) -> Rect:
        layout = BlockLayout(self.target, bounds, self.pdf)
        self.placed = layout.layout()
        LOGGER.info("Placed %s: %s", self.target, self.placed.bounds)
        return self.placed.bounds

    def draw(self):
        self.placed.draw(self.pdf)


def stack_vertically(bounds, children, padding):
    # Stack everything vertically
    available = bounds
    for child in children:
        sub_area = child.place(available)
        available = Rect(top=sub_area.bottom + padding,
                         left=available.left, right=available.right, bottom=available.bottom)
    return Rect(top=bounds.top, left=bounds.left, right=bounds.right, bottom=available.top)


def choose_method(method: common.Command):
    if method.command == 'stack':
        return stack_vertically
    else:
        raise ValueError("unknown layout method for section: '%s'" % method.command)


class SectionPlacement:
    target: Union[Section, Sheet]
    children: List
    padding: int

    def __init__(self, target: Section, children:List):
        self.target = target
        self.children = children
        self.method = choose_method(target.layout_method)

    def __str__(self):
        return "%s(%d children)" % (type(self.target).__name__, len(self.children))

    def place(self, bounds: Rect) -> Rect:
        rect = self.method(bounds, self.children, self.target.padding)
        LOGGER.info("Placed %s: %s", self, rect)
        return rect

    def draw(self):
        for c in self.children:
            c.draw()

def make_placement(target:Union[Block, Section, Sheet], pdf: PDF):
    if isinstance(target, Block):
        return BlockPlacement(target, pdf)
    else:
        children = [make_placement(item, pdf) for item in target.content]
        return SectionPlacement(target, children)


def layout_sheet(sheet:Sheet, pdf:PDF):
    outer = Rect(left=0, top=0, right=pdf.page_width, bottom=pdf.page_height) - Margins.all_equal(sheet.margin)
    placement = make_placement(sheet, pdf)
    placement.place(outer)
    placement.draw()