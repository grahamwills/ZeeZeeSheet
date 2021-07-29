"""Items to be placed on a page"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from reportlab.platypus import Flowable, Image, Paragraph, Table
from reportlab.platypus.paragraph import _SplitWordEnd

from common import Rect
from model import Style
from pdf import PDF


@dataclass
class PlacedContent:
    bounds: Rect
    issues: int

    def __init__(self, bounds: Rect, issues: int=0):
        self.issues = issues
        self.bounds = bounds.round()

    def draw(self, pdf: PDF):
        pass


def _count_split_words(item):
    if isinstance(item, Tuple):
        return sum(isinstance(i, _SplitWordEnd) for i in item[1])
    else:
        return 0


def _count_wraps(f, any_wrap_bad=False):
    if isinstance(f, Table):
        rows = f._cellvalues
        flat_list = [item for row in rows for item in row]

        # For a single row table, any wrapping is bad
        single_line_table = len(rows) == 1
        return sum(_count_wraps(f, single_line_table) for f in flat_list)
    elif isinstance(f, (Image, str)):
        return 0
    elif isinstance(f, Paragraph):
        lines = f.blPara.lines
        if len(lines) < 2:
            return 0

        split_words = sum(_count_split_words(line) for line in lines)
        return split_words * 10 + int(any_wrap_bad)
    else:
        return _count_wraps(f[0], any_wrap_bad)


class PlacedFlowableContent(PlacedContent):
    flowable: Flowable

    def __init__(self, flowable: Flowable, bounds: Rect):
        try:
            issues = _count_wraps(flowable)
        except:
            issues = 100
        super().__init__(bounds, issues)
        self.flowable = flowable

    def draw(self, pdf: PDF):
        pdf.draw_flowable(self.flowable, self.bounds)


class PlacedRectContent(PlacedContent):
    flowable: Flowable

    def __init__(self, bounds: Rect, style: Style, fill: bool, stroke: bool):
        super().__init__(bounds, 0)
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
        unioned_bounds = Rect.union(p.bounds for p in group)
        unioned_issues = sum(p.issues for p in group)
        super().__init__(unioned_bounds, unioned_issues)
        self.group = group

    def draw(self, pdf: PDF):
        for p in self.group:
            p.draw(pdf)
