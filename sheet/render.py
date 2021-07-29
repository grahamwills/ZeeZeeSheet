"""Items to be placed on a page"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from reportlab.platypus import Flowable

from common import Rect
from model import Style
from pdf import PDF


@dataclass
class PlacedContent:
    bounds: Rect

    def __init__(self, bounds: Rect):
        self.bounds = bounds.round()

    def draw(self, pdf: PDF):
        pass


class PlacedFlowableContent(PlacedContent):
    flowable: Flowable

    def __init__(self, flowable: Flowable, bounds: Rect):
        self.flowable = flowable
        super().__init__(bounds)

    def draw(self, pdf: PDF):
        pdf.draw_flowable(self.flowable, self.bounds)

class PlacedRectContent(PlacedContent):
    flowable: Flowable

    def __init__(self, bounds: Rect, style: Style, fill:bool, stroke:bool):
        super().__init__(bounds)
        self.stroke = stroke
        self.fill = fill
        self.style = style

    def draw(self, pdf: PDF):
        if self.fill:
            pdf.fill_rect(self.bounds, self.style)

        if self.stroke:
            pdf.stroke_rect(self.bounds, self.style)

class PlacedGroupContent(PlacedContent):
    group: Iterable[PlacedContent]

    def __init__(self, group: Iterable[PlacedContent]):
        super().__init__(Rect.union(p.bounds for p in group))
        self.group = group

    def draw(self, pdf: PDF):
        for p in self.group:
            p.draw(pdf)
