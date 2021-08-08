""" Defines an item placed to be drawn """
from __future__ import annotations

import abc
import math
from typing import Iterable, NamedTuple

from reportlab.platypus import Flowable, Paragraph
from reportlab.platypus.paragraph import _SplitFrag, _SplitWord

from model import Style
from sheet import common
from sheet.common import Rect
from sheet.pdf import PDF

LOGGER = common.configured_logger(__name__)


class PlacementError(NamedTuple):
    """
        How good the placement is

        Fields
        ------

        surplus_width
            Unused area (negative means it did not fit)
        surplus_height
            Unused area (negative means it did not fit)
        bad_breaks
            Line breaks in bad places, like within a word
        ok_breaks
            Number of line breaks


    """
    surplus_width: int = 0
    surplus_height: int = 0
    ok_breaks: float = 0
    bad_breaks: float = 0


_NO_ERROR = PlacementError()


class PlacedContent(abc.ABC):
    """
        Abstract class for something that has been laid out on the page

        Fields
        ------

        pdf
            The canvas to draw into
        required
            Required bounds -- where we wanted to fit
        actual
            The actual bounds that we were placed into

    """
    pdf: PDF
    requested: Rect
    actual: Rect
    _error: PlacementError

    def __init__(self, requested: Rect, actual: Rect, pdf: PDF) -> None:
        self.actual = actual
        self.requested = requested
        self.pdf = pdf

    def draw(self):
        """ Item placed on screen"""
        raise NotImplementedError()

    def error(self) -> PlacementError:
        return self._error

    def _set_error(self, bad_breaks=0, ok_breaks=0):
        self._error = PlacementError(
                surplus_width=math.floor(self.requested.width - self.actual.width),
                surplus_height=math.floor(self.requested.height - self.actual.height),
                bad_breaks=bad_breaks, ok_breaks=ok_breaks
        )


class PlacedFlowableContent(PlacedContent):
    """
        Abstract class for something that has been laid out on the page

        Fields
        ------

        flowable
            The placed flowable item
        required
            Required bounds -- where we wanted to fit
        bounds
            The actual bounds that we were placed into

    """

    flowable: Flowable

    def __init__(self, flowable: Flowable, requested: Rect, pdf: PDF):
        super().__init__(requested, requested, pdf)
        self.flowable = flowable

        flowable.wrapOn(pdf, requested.width, requested.height)

        if isinstance(flowable, Paragraph):
            self._init_paragraph(flowable)
        else:
            raise ValueError("Cannot handle flowable of type '%s'", type(flowable).__name__)

    def draw(self):
        self.pdf.draw_flowable(self.flowable, self.actual)

    def _init_paragraph(self, p: Paragraph):
        frags = p.blPara

        if frags.kind == 0:
            unused = max(entry[0] for entry in frags.lines)
            bad_breaks = sum(isinstance(c, _SplitWord) for entry in frags.lines for c in entry[1])
            ok_breaks = len(frags.lines) - 1 - bad_breaks
            width = p.width - unused
            LOGGER.debug("Fragments = " + " | ".join(str(c) + ":" + type(c).__name__
                                                     for entry in frags.lines for c in entry[1]))
        elif frags.kind == 1:
            unused = max(entry.extraSpace for entry in frags.lines)
            width = p.width - unused
            bad_breaks = sum(type(frag) == _SplitFrag for frag in p.frags)
            specified_breaks = sum(item.lineBreak for item in frags.lines)
            ok_breaks = len(frags.lines) - 1 - bad_breaks - specified_breaks
            LOGGER.debug("Fragments = " + " | ".join((c[1][1] + ":" + type(c).__name__) for c in p.frags))
        else:
            raise NotImplementedError()

        self.actual = self.requested.resize(width=math.ceil(width), height=math.ceil(p.height))
        self._set_error(bad_breaks=bad_breaks, ok_breaks=ok_breaks)


class PlacedRectContent(PlacedContent):
    style: Style
    stroke: bool
    fill: bool
    rounded: int

    def __init__(self, bounds: Rect, style: Style, pdf: PDF, fill: bool = False, stroke: bool = True, rounded=0):
        super().__init__(bounds, bounds, pdf)
        self.style = style
        self.stroke = stroke
        self.fill = fill
        self.rounded = rounded
        self._error = _NO_ERROR

    def draw(self):
        if self.fill:
            self.pdf.fill_rect(self.actual, self.style, self.rounded)

        if self.stroke:
            self.pdf.stroke_rect(self.actual, self.style, self.rounded)


class PlacedGroupContent(PlacedContent):
    group: Iterable[PlacedContent]

    def __init__(self, requested: Rect, group: Iterable[PlacedContent], pdf: PDF):
        actual = Rect.union(p.actual for p in group)
        super().__init__(requested, actual, pdf)
        self.group = group

        sum_bad = sum(p.error().bad_breaks for p in group)
        sum_ok = sum(p.error().ok_breaks for p in group)
        self._set_error(bad_breaks=sum_bad, ok_breaks=sum_ok)

    def draw(self):
        for p in self.group:
            p.draw()
