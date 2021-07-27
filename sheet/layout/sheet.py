from __future__ import annotations
from typing import Tuple, Union

from common import Context, Margins, Rect, configured_logger
from layout.block import BlockLayout
from model import Block, Section, Sheet
from render import EmptyPlacedContent, PlacedContent

LOGGER = configured_logger(__name__)


class Placement:
    context: Context
    target: Union[Sheet, Section, Block]
    children: Tuple[Placement]
    content_method: str
    border_method: str

    # Placed
    placed_content: PlacedContent

    def __init__(self, target: Union[Sheet, Section, Block], context: Context):
        self.context = context
        self.padding = target.padding
        self.target = target
        if isinstance(target, Block):
            self.content_method = target.renderers[1]
            if target.title:
                self.border_method = target.renderers[0]
            else:
                self.border_method = 'none'
            self.children = tuple()
        else:
            self.children = tuple(Placement(item, context) for item in target.content)
            self.content_method = 'none'
            self.border_method = 'none'

    def __str__(self):
        if self.children:
            return "§ items=%d" % len(self.children)
        else:
            return "§ content=%s" % self.target

    def place(self, bounds: Rect) -> Rect:
        self.placed_bounds = bounds
        if self.children:
            # Stack everything vertically
            available = bounds
            for child in self.children:
                sub_area = child.place(available)
                available = Rect(top=sub_area.bottom + self.target.padding,
                                 left=available.left, right=available.right, bottom=available.bottom)
            rect = Rect(top=bounds.top, left=bounds.left, right=bounds.right, bottom=available.top)
            self.placed_content = EmptyPlacedContent(rect)
        else:
            layout = BlockLayout(self.target, bounds, self.context)
            layout.set_methods(self.border_method, self.content_method)
            self.placed_content = layout.layout()

        LOGGER.info("Placed %s: %s", self.target, self.placed_bounds)
        return self.placed_content.bounds

    def set_placed_bounds(self, bounds: Rect):
        self.placed_bounds = bounds

    def draw(self):
        if self.placed_content:
            self.placed_content.draw(self.context.canvas, debug=self.context.debug)
        for c in self.children:
            c.draw()


def dump(placed: Placement, indent=0):
    if not placed.children:
        print("  " * indent + str(placed.target))
    else:
        print("  " * indent + str(placed))
        for i in placed.children:
            dump(i, indent + 1)


def layout_sheet(sheet:Sheet, context:Context):
    M = sheet.margin
    outer = Rect(left=0, top=0, right=context.page_width, bottom=context.page_height) - Margins(M, M, M, M)
    placement = Placement(sheet, context)
    placement.place(outer)
    placement.draw()