""" Defines an item placed to be drawn """
from __future__ import annotations

import abc
import math
from copy import copy
from typing import List

from colour import Color
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import Flowable, Image, Paragraph, Table
from reportlab.platypus.paragraph import _SplitFrag, _SplitWord

from sheet import common
from sheet.common import Rect
from sheet.model import Style
from sheet.pdf import PDF

LOGGER = common.configured_logger(__name__)

_DEBUG_RECT_STYLE = Style(background=Color('lightGray'))


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

    unused_width: int
    ok_breaks: float
    bad_breaks: float
    internal_variance: float

    def __init__(self, requested: Rect, actual: Rect, pdf: PDF) -> None:
        self.actual = actual
        self.requested = requested
        self.pdf = pdf

        self.ok_breaks = 0
        self.bad_breaks = 0
        self.internal_variance = 0
        self.unused_width = self._unused_requested_width()

    def draw(self):
        """ Item placed on screen"""
        raise NotImplementedError()

    def move(self, dx=0, dy=0):
        old = self.actual
        self.actual = self.actual.move(dx=dx, dy=dy)
        self.requested = self.requested.move(dx=dx, dy=dy)

    def error_from_variance(self, multiplier: float):
        """ Internal variance in free space"""
        return multiplier * self.internal_variance

    def error_from_breaks(self, multiplier_bad: float, multiplier_good: float):
        """ Line breaks and word breaks"""
        return multiplier_bad * self.bad_breaks + multiplier_good * self.ok_breaks

    def error_from_size(self, multiplier_bad: float, multiplier_good: float):
        """ Fit to the allocated sapce"""
        extra = self.requested.width - self.actual.width
        if extra < 0:
            return -extra * multiplier_bad
        else:
            return max(extra, self.unused_width) * multiplier_good

    def _unused_requested_width(self):
        return max(0, self.requested.width - self.actual.width)


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
        self.unused_width = self._unused_requested_width()

    def _init_table(self, table: Table):
        sum_bad, sum_ok, unused = table_info(table)
        self.actual = self.requested.resize(width=table._width, height=table._height)
        self.ok_breaks = sum_ok
        self.bad_breaks = sum_bad
        self.internal_variance = round(max(unused) - min(unused))
        self.unused_width = max(int(sum(unused)), self._unused_requested_width())

    def _init_paragraph(self, p: Paragraph):
        bad_breaks, ok_breaks, unused = line_info(p)
        if p.style.alignment == TA_JUSTIFY or p.style.alignment == TA_CENTER:
            self.actual = self.requested.resize(width=math.ceil(self.requested.width), height=math.ceil(p.height))
        else:
            self.actual = self.requested.resize(width=math.ceil(self.requested.width - unused),
                                                height=math.ceil(p.height))
        self.ok_breaks = ok_breaks
        self.bad_breaks = bad_breaks
        self.unused_width = self._unused_requested_width()

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

    def draw(self):
        if self.fill:
            self.pdf.fill_rect(self.actual, self.style, self.rounded)

        if self.stroke:
            self.pdf.stroke_rect(self.actual, self.style, self.rounded)

    def __str__(self) -> str:
        return "Rect(%s)" % str(self.actual)


class ErrorContent(PlacedRectContent):

    def __init__(self, bounds: Rect, pdf: PDF):
        super().__init__(bounds, Style(background=Color('red')), pdf, True, True, 0)

    def draw(self):
        super().draw()

    def error_from_size(self, multiplier_bad: float, multiplier_good: float):
        return 1e9 - self.actual.width * self.actual.height


class PlacedGroupContent(PlacedContent):
    group: [PlacedContent]

    def __init__(self, group: List[PlacedContent], requested: Rect, actual=None):
        LOGGER.debug("Creating Placed Content for %d items in %s", len(group), requested)
        actual = actual or Rect.union(p.actual for p in group)
        super().__init__(requested, actual, group[0].pdf)
        self.group = group
        self._set_placements()

    def _set_placements(self):
        # Sort left to right
        items = sorted(self.group, key=lambda x: x.requested.left + x.actual.left * 0.0001)
        self.unused_width = 0

        # We will scan across the space, keeping track of unused space as we go
        left, right, unused = -1, 0, 0
        for item in items:
            self.ok_breaks += item.ok_breaks
            self.bad_breaks += item.bad_breaks

            a = item.requested.left
            b = item.requested.right

            # If there is a clear gap, add that overlap space in and close the gap
            if a > right:
                unused += a - right
                right = a

            # Add in the unused amount in proportion to non-overlapped item
            overlap_fraction = (right - a) / (right - left)
            self.unused_width += (1 - overlap_fraction) * unused

            # Update the scan to this item
            left, right, unused = a, b, item.unused_width

        # Handle any left overs
        self.unused_width = round(self.unused_width + (self.requested.right - right) + unused)

    def draw(self):
        if self.pdf.debug:
            self.pdf.saveState()
            self.pdf.setFillColorRGB(0, 0, 1, 0.05)
            self.pdf.setStrokeColorRGB(0, 0, 1, 0.05)
            self.pdf.setLineWidth(2)
            self.pdf.rect(self.actual.left, self.pdf.page_height - self.actual.bottom,
                          self.actual.width, self.actual.height, fill=1, stroke=1)
            self.pdf.restoreState()
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


def table_info(table):
    """ Calculate breaks and unused space """
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
            bad_breaks, ok_breaks, unused = line_info(cell[0])
            sum_bad += bad_breaks
            sum_ok += ok_breaks
        elif isinstance(cell[0], Table):
            tbad, tok, tunused = table_info(cell[0])
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


def line_info(p):
    """ Calculate line break info for a paragraph"""
    frags = p.blPara
    if frags.kind == 0:
        unused = min(entry[0] for entry in frags.lines)
        bad_breaks = sum(type(c) == _SplitWord for entry in frags.lines for c in entry[1])
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
