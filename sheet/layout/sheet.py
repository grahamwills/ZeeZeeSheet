from __future__ import annotations
from typing import List, Tuple, Union

from common import  Margins, Rect, configured_logger
from layout.block import BlockLayout
from model import Block, Section, Sheet
from pdf import PDF
from render import PlacedContent, empty_content

LOGGER = configured_logger(__name__)


class BlockPlacement:
    context: PDF
    target: Block
    content_method: str
    border_method: str

    # Placed
    placed_content: PlacedContent

    def __init__(self, target: Block, context: PDF):
        self.context = context
        self.padding = target.padding
        self.target = target
        self.content_method = target.renderers[1]
        if target.title:
            self.border_method = target.renderers[0]
        else:
            self.border_method = 'none'
        self.children = []

    def __str__(self):
        return "§ content=%s" % self.target

    def place(self, bounds: Rect) -> Rect:
        self.placed_bounds = bounds
        layout = BlockLayout(self.target, bounds, self.context)
        layout.set_methods(self.border_method, self.content_method)
        self.placed_content = layout.layout()
        LOGGER.info("Placed %s: %s", self.target, self.placed_bounds)
        return self.placed_content.bounds if self.placed_content else None

    def set_placed_bounds(self, bounds: Rect):
        self.placed_bounds = bounds

    def draw(self):
        if self.placed_content:
            self.placed_content.draw(self.context)
        for c in self.children:
            c.draw()

class SectionPlacement:
    children: List[BlockPlacement]
    padding: int

    def __init__(self, target: Section, context: PDF):
        self.padding = target.padding
        self.children = [BlockPlacement(item, context) for item in target.content]

    def __str__(self):
        return "§ blocks=%d" % len(self.children)

    def place(self, bounds: Rect) -> Rect:
        self.placed_bounds = bounds
        # Stack everything vertically
        available = bounds
        for child in self.children:
            sub_area = child.place(available)
            available = Rect(top=sub_area.bottom + self.padding,
                             left=available.left, right=available.right, bottom=available.bottom)
        rect = Rect(top=bounds.top, left=bounds.left, right=bounds.right, bottom=available.top)
        self.placed_content = empty_content(rect)

        LOGGER.info("Placed Section: %s", self.placed_bounds)
        return self.placed_content.bounds if self.placed_content else None

    def set_placed_bounds(self, bounds: Rect):
        self.placed_bounds = bounds

    def draw(self):
        for c in self.children:
            c.draw()

class SheetPlacement:
    children: List[SectionPlacement]
    padding: int

    def __init__(self, target: Sheet, context: PDF):
        self.padding = target.padding
        self.children = [SectionPlacement(item, context) for item in target.content]

    def __str__(self):
        return "Sheet sections=%d" % len(self.children)

    def place(self, bounds: Rect) -> Rect:
        self.placed_bounds = bounds
        # Stack everything vertically
        available = bounds
        for child in self.children:
            sub_area = child.place(available)
            available = Rect(top=sub_area.bottom + self.padding,
                             left=available.left, right=available.right, bottom=available.bottom)
        rect = Rect(top=bounds.top, left=bounds.left, right=bounds.right, bottom=available.top)
        self.placed_content = empty_content(rect)

        LOGGER.info("Placed Sheet: %s", self.placed_bounds)
        return self.placed_content.bounds if self.placed_content else None

    def set_placed_bounds(self, bounds: Rect):
        self.placed_bounds = bounds

    def draw(self):
        for c in self.children:
            c.draw()




def layout_sheet(sheet:Sheet, context:PDF):
    outer = Rect(left=0, top=0, right=context.page_width, bottom=context.page_height) - Margins.all_equal(sheet.margin)
    placement = SheetPlacement(sheet, context)
    placement.place(outer)
    placement.draw()