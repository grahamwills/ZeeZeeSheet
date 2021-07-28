"""Items to be placed on a page"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from reportlab.platypus import Flowable

from common import Margins, Rect
from model import Style
from pdf import PDF



class PlacedContent:
    bounds: Rect
    margins: Optional[Margins]
    draw: Callable[[PDF], None]

    def __init__(self, bounds: Rect, draw: Callable[[PDF], None]):
        self.bounds = bounds.round()
        self.draw = draw


def empty_content(bounds:Rect) -> PlacedContent:
    return PlacedContent(bounds, lambda x: None)


def _draw_multiple(group: Iterable[PlacedContent], pdf: PDF):
    for p in group:
        p.draw(pdf)


def grouped_content(group: Iterable[PlacedContent]) -> PlacedContent:
    bounds = Rect.union(p.bounds for p in group)

    def _draw(pdf):
        for p in group:
            p.draw(pdf)

    return PlacedContent(bounds, _draw)


def flowable_content(flowable: Flowable, bounds: Rect):
    return PlacedContent(bounds, lambda pdf: pdf.draw_flowable(flowable, bounds))


def rect_content(bounds: Rect, style: Style, fill, stroke):
    def _draw(pdf: PDF):
        if fill:
            pdf.fill_rect(bounds, style)
        if stroke:
            pdf.stroke_rect(bounds, style)

    return PlacedContent(bounds, _draw)

