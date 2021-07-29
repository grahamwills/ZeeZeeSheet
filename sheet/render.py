"""Items to be placed on a page"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from reportlab.platypus import Flowable, ParaFrag, ParaLines, Paragraph, Table, Image
from reportlab.platypus.paragraph import FragLine, _SplitWordEnd

from common import Rect
from model import Style
from pdf import PDF


@dataclass
class PlacedContent:
    bounds: Rect
    issues: int

    def __init__(self, bounds: Rect, issues: int):
        self.issues = issues
        self.bounds = bounds.round()

    def draw(self, pdf: PDF):
        pass


def _count_wraps(f):
    if isinstance(f, Table):
        flat_list = [item for row in f._cellvalues for item in row]
        return sum(_count_wraps(f) for f in flat_list)
    elif isinstance(f, (Image,str)):
        return 0
    elif isinstance(f, Paragraph):
        lines = f.blPara.lines
        if len(lines) < 2:
            return 0
        last = lines[-1]
        if isinstance(last, ParaLines):
            w = last.words[-1].text
        else:
            w = last[-1][-1]

        prev = lines[-2]
        if isinstance(prev, FragLine):
            v = prev.words[-1].text
        elif isinstance(prev, ParaLines):
                v = prev.words[-1].text
        else:
            v = prev[-1][-1]
        if isinstance(w, _SplitWordEnd):
            # print(v, w)
            return 1
        return 0
    else:
        try:
            return _count_wraps(f[0])
        except:
            return 0


class PlacedFlowableContent(PlacedContent):
    flowable: Flowable

    def __init__(self, flowable: Flowable, bounds: Rect):
        issues = _count_wraps(flowable)
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
