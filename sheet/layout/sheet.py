from __future__ import annotations
from typing import List, Tuple, Union

from common import  Margins, Rect, configured_logger
from layout.block import BlockLayout
from model import Block, Section, Sheet
from pdf import PDF
from render import PlacedContent, empty_content

LOGGER = configured_logger(__name__)


class BlockPlacement:
    target: Block
    context: PDF

    # Placed
    placed_content: PlacedContent

    def __init__(self, target: Block, context: PDF):
        self.context = context
        self.padding = target.padding
        self.target = target
        self.children = []

    def __str__(self):
        return "§ content=%s" % self.target

    def place(self, bounds: Rect) -> Rect:
        layout = BlockLayout(self.target, bounds, self.context)
        self.placed_content = layout.layout()
        content_bounds = self.placed_content.bounds
        LOGGER.info("Placed %s: %s", self.target, content_bounds)
        return content_bounds

    def draw(self):
        if self.placed_content:
            self.placed_content.draw(self.context)
        for c in self.children:
            c.draw()

class SectionPlacement:
    target: Union[Section, Sheet]
    children: List
    padding: int

    def __init__(self, target: Section, children:List):
        self.target = target
        self.children = children

    def __str__(self):
        return "%s(%d children)" % (type(self.target).__name__, len(self.children))

    def place(self, bounds: Rect) -> Rect:
        self.placed_bounds = bounds
        # Stack everything vertically
        available = bounds
        for child in self.children:
            sub_area = child.place(available)
            available = Rect(top=sub_area.bottom + self.target.padding,
                             left=available.left, right=available.right, bottom=available.bottom)
        rect = Rect(top=bounds.top, left=bounds.left, right=bounds.right, bottom=available.top)
        self.placed_content = empty_content(rect)

        LOGGER.info("Placed %s: %s", self, self.placed_bounds)
        return self.placed_content.bounds if self.placed_content else None

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