""" Defines an item placed to be drawn """
from __future__ import annotations

import abc
import math
from copy import copy
from typing import List, NamedTuple

from reportlab.platypus import Flowable, Image, Paragraph, Table
from reportlab.platypus.paragraph import _SplitFrag, _SplitWord

from sheet import common
from sheet.common import Rect
from sheet.model import Style
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

    def error(self) -> float:
        return self._error_from_breaks() + self._error_from_size()

    def _set_error(self, bad_breaks=0, ok_breaks=0):
        self._error = PlacementError(
                surplus_width=math.floor(self.requested.width - self.actual.width),
                surplus_height=math.floor(self.requested.height - self.actual.height),
                bad_breaks=bad_breaks, ok_breaks=ok_breaks
        )

    def move(self, dx=0, dy=0):
        old = self.actual
        self.actual = self.actual.move(dx=dx, dy=dy)
        self.requested = self.requested.move(dx=dx, dy=dy)

    def _error_from_breaks(self):
        return self._error.bad_breaks * 100 + self._error.ok_breaks * 10

    def _error_from_size(self):
        extra =  self.requested.width - self.actual.width
        if extra < 0:
            return 100 * extra ** 2
        else:
            return extra ** 2


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
        LOGGER.info("Creating Placed Content for %s in %s", type(flowable).__name__, requested)
        super().__init__(requested, requested, pdf)
        self.flowable = flowable

        flowable.wrapOn(pdf, requested.width, requested.height)

        if isinstance(flowable, Paragraph):
            self._init_paragraph(flowable)
        elif isinstance(flowable, Image):
            self._init_image(flowable)
        elif isinstance(flowable, Table):
            self._init_table(flowable)
        else:
            raise ValueError("Cannot handle flowable of type '%s'", type(flowable).__name__)

    def draw(self):
        self.pdf.draw_flowable(self.flowable, self.actual)

    def _init_image(self, image: Image):
        self.actual = self.requested.resize(width=math.ceil(image.drawWidth), height=math.ceil(image.drawHeight))
        self._set_error()

    def _init_table(self, table: Table):
        sum_bad, sum_ok, unused = _table_info(table)
        self.actual = self.requested.resize(width=table._width - sum(unused), height=table._height)
        self._set_error(bad_breaks=sum_bad, ok_breaks=sum_ok)

    def _init_paragraph(self, p: Paragraph):
        bad_breaks, ok_breaks, unused = _line_info(p)
        self.actual = self.requested.resize(width=math.ceil(self.requested.width - unused), height=math.ceil(p.height))
        self._set_error(bad_breaks=bad_breaks, ok_breaks=ok_breaks)

    def __str__(self) -> str:
        return "Flow(%s:%dx%d)" % (self.flowable.__class__.__name__, self.actual.width, self.actual.height)


class PlacedRectContent(PlacedContent):
    style: Style
    stroke: bool
    fill: bool
    rounded: int

    def __init__(self, bounds: Rect, style: Style, pdf: PDF, fill: bool = False, stroke: bool = True, rounded=0):
        LOGGER.info("Creating Placed Rectangle %s", bounds)
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

    def __str__(self) -> str:
        return "Rect(%s)" % str(self.actual)


class PlacedGroupContent(PlacedContent):
    group: [PlacedContent]

    def __init__(self, group: List[PlacedContent], requested: Rect, actual=None):
        LOGGER.debug("Creating Placed Content for %d items in %s", len(group), requested)
        actual = actual or Rect.union(p.actual for p in group)
        super().__init__(requested, actual, group[0].pdf)
        self.group = group

    def draw(self):
        for p in self.group:
            p.draw()

    def move(self, dx=0, dy=0):
        super().move(dx, dy)
        for p in self.group:
            p.move(dx, dy)

    def __getitem__(self, item):
        return self.group[item]

    def __str__(self, depth: int = 1) -> str:
        if depth:
            content = ", ".join(
                    c.__str__(depth - 1) if isinstance(c, PlacedGroupContent) else str(c) for c in self.group)
            return "Group(%dx%d: %s)" % (self.actual.width, self.actual.height, content)
        else:
            return "Group(%dx%d: ...)" % (self.actual.width, self.actual.height)

    def __copy__(self):
        # Shallow except for the children, whichj need copying
        group = [copy(child) for child in self.group]
        return PlacedGroupContent(group, self.requested, actual=self.actual)

    def _error_from_breaks(self):
        return sum(child._error_from_breaks() for child in self.group)


class EmptyPlacedContent(PlacedContent):

    def __init__(self, requested: Rect, pdf: PDF):
        LOGGER.info("Creating Empty content in %s", requested)
        super().__init__(requested, requested.resize(width=0, height=0), pdf)
        self._set_error()

    def draw(self):
        pass

    def __str__(self) -> str:
        return "Empty"


def _table_info(table):
    cells = table._cellvalues
    ncols = max(len(row) for row in cells)
    min_unused = [table._width] * ncols
    sum_bad = 0
    sum_ok = 0
    try:
        span_map = table._spanRanges
    except:
        indices = [(i, j) for i in range(0, ncols) for j in range(0, len(cells))]
        span_map = dict((i, (i[0], i[1], i[0], i[1])) for i in indices)
    for idx, span in span_map.items():
        cell = cells[idx[1]][idx[0]]
        if not span or not cell:
            continue
        if isinstance(cell[0], Paragraph):
            bad_breaks, ok_breaks, unused = _line_info(cell[0])
            sum_bad += bad_breaks
            sum_ok += ok_breaks
        elif isinstance(cell[0], Table):
            tbad, tok, tunused = _table_info(cell[0])
            sum_bad += tbad
            sum_ok += tok
            unused = sum(tunused)
        else:
            raise ValueError("Unknown item")

        # Divide unused up evenly across columns
        unused /= (1 + span[2] - span[0])
        for i in range(span[0], span[2] + 1):
            min_unused[i] = min(min_unused[i], unused)

    return sum_bad, sum_ok, min_unused


def _line_info(p):
    """ Calculate line break info for a paragraph"""
    frags = p.blPara
    if frags.kind == 0:
        unused = min(entry[0] for entry in frags.lines)
        bad_breaks = sum(isinstance(c, _SplitWord) for entry in frags.lines for c in entry[1])
        ok_breaks = len(frags.lines) - 1 - bad_breaks
        LOGGER.fine("Fragments = " + " | ".join(str(c) + ":" + type(c).__name__
                                                for entry in frags.lines for c in entry[1]))
    elif frags.kind == 1:
        unused = min(entry.extraSpace for entry in frags.lines)
        bad_breaks = sum(type(frag) == _SplitFrag for frag in p.frags)
        specified_breaks = sum(item.lineBreak for item in frags.lines)
        ok_breaks = len(frags.lines) - 1 - bad_breaks - specified_breaks
        LOGGER.fine("Fragments = " + " | ".join((c[1][1] + ":" + type(c).__name__) for c in p.frags))
    else:
        raise NotImplementedError()
    return bad_breaks, ok_breaks, unused
