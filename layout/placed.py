""" Defines an item placed to be drawn """
from __future__ import annotations

import abc
import math
from copy import copy
from typing import List

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.pdfgen.pathobject import PDFPathObject
from reportlab.platypus import Image

from structure import Style
from util import Rect, configured_logger
from .flowables import Paragraph, Table
from .pdf import DrawMethod, PDF, line_info

LOGGER = configured_logger(__name__)


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
        page_break_before
            Only used for top-level sections, True => page break before this

    """
    pdf: PDF
    requested: Rect
    actual: Rect

    unused_width: int
    ok_breaks: float
    bad_breaks: float
    internal_variance: float
    page_break_before: bool

    def __init__(self, requested: Rect, actual: Rect, pdf: PDF) -> None:
        self.actual = actual
        self.requested = requested
        self.pdf = pdf

        self.ok_breaks = 0
        self.bad_breaks = 0
        self.internal_variance = 0
        self.unused_width = self._unused_requested_width()
        self.page_break_before = False

    def draw(self):
        """ Item placed on screen"""
        raise NotImplementedError()

    def move(self, dx=0, dy=0) -> PlacedContent:
        self.actual = self.actual.move(dx=dx, dy=dy)
        self.requested = self.requested.move(dx=dx, dy=dy)
        return self

    def styled(self, style: Style):
        return self.pdf.using_style(style)

    def error_from_variance(self, multiplier: float):
        """ Internal variance in free space"""
        return multiplier * self.internal_variance

    def error_from_breaks(self, multiplier_bad: float, multiplier_good: float):
        """ Line breaks and word breaks"""
        return multiplier_bad * self.bad_breaks + multiplier_good * self.ok_breaks

    def error_from_size(self, multiplier_bad: float, multiplier_good: float):
        """ Fit to the allocated space"""
        if self.unused_width < 0:
            return -self.unused_width * multiplier_bad
        else:
            return self.unused_width * multiplier_good

    def _unused_requested_width(self):
        return self.requested.width - self.actual.width


class PlacedParagraphContent(PlacedContent):
    paragraph: Paragraph

    def __init__(self, paragraph: Paragraph, requested: Rect, pdf: PDF):
        super().__init__(requested, requested, pdf)
        self.paragraph = paragraph

        if not hasattr(paragraph, 'height'):
            paragraph.wrapOn(pdf, requested.width, requested.height)

        bad_breaks, ok_breaks, unused = line_info(paragraph)
        if paragraph.style.alignment == TA_JUSTIFY:
            rect = self.requested.resize(width=math.ceil(self.requested.width), height=math.ceil(paragraph.height))
            self.actual = rect
        else:
            rect1 = self.requested.resize(width=math.ceil(self.requested.width - unused),
                                          height=math.ceil(paragraph.height))
            self.actual = rect1
        self.ok_breaks = ok_breaks
        self.bad_breaks = bad_breaks
        self.unused_width = self._unused_requested_width()

    def draw(self):
        self.pdf.draw_flowable(self.paragraph, self.actual)

    def __str__(self) -> str:
        return "Paragraph(%dx%d)" % (self.actual.width, self.actual.height)


class PlacedImageContent(PlacedContent):

    def __init__(self, image: Image, requested: Rect, style: Style, pdf: PDF):
        super().__init__(requested, requested, pdf)
        self.style = style
        self.image = image
        image.wrapOn(pdf, requested.width, requested.height)
        self.actual = self.requested.resize(width=math.ceil(image.drawWidth), height=math.ceil(image.drawHeight))
        self.unused_width = self._unused_requested_width()

        # Count being smaller or larger than desired by a given amount as equivalent to a wrapping break

        xdiff = abs(image.imageWidth - self.actual.width)
        self.ok_breaks = xdiff / 10

    def draw(self):
        with self.styled(self.style) as pdf:
            pdf.draw_flowable(self.image, self.actual)

    def __str__(self) -> str:
        return "Image(%dx%d)" % (self.actual.width, self.actual.height)


class PlacedTableContent(PlacedContent):
    table: Table

    def __init__(self, table: Table, requested: Rect, pdf: PDF):
        super().__init__(requested, requested, pdf)
        self.table = table

        if hasattr(table, 'offset'):
            LOGGER.debug("Redundant wrapping call for %s in %s", type(table).__name__, requested)
        table.wrapOn(pdf, requested.width, requested.height)

        self.actual = self.requested.resize(width=table.width, height=table.height)
        sum_bad, sum_ok, unused = table.calculate_issues()
        self.ok_breaks = sum_ok
        self.bad_breaks = sum_bad
        self.internal_variance = round(max(unused) - min(unused))
        self.unused_width = max(int(sum(unused)), self._unused_requested_width())

    def draw(self):
        self.pdf.draw_flowable(self.table, self.actual)

    def move(self, dx=0, dy=0) -> PlacedTableContent:
        super().move(dx, dy)
        return self

    def __str__(self) -> str:
        return "Table(%dx%d)" % (self.actual.width, self.actual.height)


class PlacedRectContent(PlacedContent):

    def __init__(self, bounds: Rect, style: Style, method: DrawMethod, pdf: PDF, rounded=0):
        super().__init__(bounds, bounds, pdf)
        self.method = method
        self.style = style
        self.rounded = rounded

    def draw(self):
        with self.styled(self.style) as pdf:
            pdf.draw_rect(self.actual, self.method, rounded=self.rounded)

    def __str__(self) -> str:
        return "Rect(%s)" % str(self.actual)


class PlacedPathContent(PlacedContent):

    def __init__(self, path: PDFPathObject, bounds: Rect, style: Style, method: DrawMethod, pdf: PDF):
        super().__init__(bounds, bounds, pdf)
        self.method = method
        self.style = style
        self.path = path

    def draw(self):
        with self.styled(self.style) as pdf:
            pdf.draw_path(self.path, self.requested.left, self.requested.top, self.method)

    def __str__(self) -> str:
        return "Path(%s)" % str(self.path)


class PlacedClipContent(PlacedContent):

    def __init__(self, path: PDFPathObject, bounds: Rect, pdf: PDF):
        super().__init__(bounds, bounds, pdf)
        self.path = path

    def draw(self):
        x = self.requested.left
        y = self.pdf.page_height - self.requested.bottom
        self.pdf.translate(x, y)
        self.pdf.clipPath(self.path, stroke=0, fill=0)
        self.pdf.translate(-x, -y)

    def __str__(self) -> str:
        return "Clip(%s)" % str(self.path)


class ErrorContent(PlacedRectContent):

    def __init__(self, bounds: Rect, pdf: PDF):
        super().__init__(bounds, Style('err'), PDF.FILL, pdf)

    def draw(self):
        super().draw()

    def error_from_size(self, multiplier_bad: float, multiplier_good: float):
        return 1e9 - self.actual.width * self.actual.height


class PlacedGroupContent(PlacedContent):

    def __init__(self, children: List[PlacedContent], requested: Rect):
        self.group = [p for p in children if p] if children else []
        if not self.group:
            return

        actual = Rect.union(p.actual for p in self.group)
        super().__init__(requested, actual, self.group[0].pdf)

        self.ok_breaks = sum(item.ok_breaks for item in self.group)
        self.bad_breaks = sum(item.bad_breaks for item in self.group)

        # If not enough room, that's all that matters
        if self.requested.width < self.actual.width:
            self.unused_width = self.requested.width - self.actual.width
        else:
            self.unused_width = calculate_unused_width_for_group(self.group, self.requested)

    def draw(self):
        self.pdf.saveState()
        if self.pdf.debug:
            self.pdf.setFillColorRGB(0, 0, 1, 0.05)
            self.pdf.setStrokeColorRGB(0, 0, 1, 0.05)
            self.pdf.setLineWidth(2)
            self.pdf.rect(self.actual.left, self.pdf.page_height - self.actual.bottom,
                          self.actual.width, self.actual.height, fill=1, stroke=1)
        for p in self.group:
            p.draw()
        self.pdf.restoreState()

    def move(self, dx=0, dy=0) -> PlacedGroupContent:
        super().move(dx, dy)
        for p in self.group:
            p.move(dx, dy)
        return self

    def __getitem__(self, item):
        return self.group[item]

    def __str__(self, depth: int = 1) -> str:
        if depth:
            content = ", ".join(
                    c.__str__(depth - 1) if isinstance(c, PlacedGroupContent) else str(c) for c in self.group)
            return "Group(%dx%d: %s)" % (self.actual.width, self.actual.height, content)
        else:
            return "Group(%dx%d: ...)" % (self.actual.width, self.actual.height)

    def __len__(self):
        return len(self.group)

    def __copy__(self):
        # Create a new instance and copy the __dict__ items in
        cls = self.__class__
        pgc = cls.__new__(cls)
        pgc.__dict__.update(self.__dict__)

        # Deep copy the group
        pgc.group = [copy(child) for child in self.group]
        return pgc


def _unused_horizontal_strip(group: List[PlacedContent], bounds: Rect):
    """ Unused space, assuming items horizontally laid out, more or less"""
    ox = bounds.left
    # Create an array of bytes that indicate spaces is used
    used = bytearray(bounds.width)
    for g in group:
        d = g.unused_width
        left = g.requested.left + d // 2
        right = g.requested.right - d + d // 2
        for i in range(int(left - ox), int(right - ox)):
            used[i] = 1
    return bounds.width - sum(used)


def calculate_unused_width_for_group(group: List[PlacedContent], bounds: Rect) -> int:
    # Sort vertically by tops
    items = sorted(group, key=lambda x: x.requested.top)

    unused = bounds.width

    # Scan down the items
    idx = 0
    while idx < len(items):

        # Accumulate all the items that overlap the current one
        across = [items[idx]]
        lower = items[idx].requested.bottom
        idx += 1
        while idx < len(items) and items[idx].requested.top < lower:
            across.append(items[idx])
            idx += 1
        unused = min(unused, _unused_horizontal_strip(items, bounds))

    return unused
