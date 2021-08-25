from typing import Dict, List, Sequence, Tuple

import reportlab
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable
from reportlab.platypus.paragraph import _SplitFrag, _SplitWord

from sheet import common
from sheet.pdf import PDF

LOGGER = common.configured_logger(__name__)


class Table(Flowable):
    cells: Sequence[Sequence[Flowable]]
    offset: Dict[Flowable, Tuple[int, int]]

    def __init__(self, cells: Sequence[Sequence[Flowable]], padding: int, colWidths, pdf: PDF):
        """ Note that the columnwidths do NOT inlcude the padding, which is extra"""
        super().__init__()
        self.pdf = pdf
        self.colWidths = colWidths
        self.cells = cells
        self.padding = padding
        self.ncols = max(len(row) for row in cells)
        self.total_column_width = sum(colWidths)
        self.total_width = self.total_column_width + (self.ncols - 1) * self.padding

        if self.total_column_width < 10 * self.ncols:
            raise ValueError(
                "Table too small to be created (width=%s, cols=%d)" % (self.total_column_width, self.ncols))

    def _place_row(self, row, top, availHeight):
        heights = []
        x = 0
        for i, cell in enumerate(row):
            columnWidth = self.colWidths[i] if cell != row[-1] else self.total_width - x
            w, h = cell.wrapOn(self.pdf, columnWidth, availHeight)
            self.offset[cell] = (x, top)
            heights.append(h)
            x = x + columnWidth + self.padding

        row_height = max(heights)

        # Adjust to align at the tops
        for cell, height in zip(row, heights):
            x, y = self.offset[cell]
            self.offset[cell] = x, y - height + row_height

        return row_height

    def wrap(self, availWidth, availHeight):
        self.offset = dict()
        y = 0
        for row in reversed(self.cells):
            row_height = self._place_row(row, y, availHeight - y)
            y += row_height + self.padding

        self.width = availWidth
        self.height = y - self.padding
        return self.width, self.height

    def draw(self):
        for row in self.cells:
            for cell in row:
                p = self.offset[cell]
                cell.drawOn(self.canv, p[0], p[1])

    def calculate_issues(self, width) -> Tuple[int, int, List[int]]:
        """ Calculate breaks and unused space """
        min_unused = [width] * self.ncols
        sum_bad = 0
        sum_ok = 0

        for row in self.cells:
            for idx, cell in enumerate(row):
                # The last cell goes to the end of the row
                if cell == row[-1]:
                    end = self.ncols
                else:
                    end = idx + 1

                try:
                    tbad, tok, tunused = cell.calculate_issues(width)
                    sum_bad += tbad
                    sum_ok += tok
                    unused = sum(tunused)
                except:
                    bad_breaks, ok_breaks, unused = line_info(cell)
                    sum_bad += bad_breaks
                    sum_ok += ok_breaks

                # Divide unused up evenly across columns
                unused /= end - idx
                for i in range(idx, end):
                    min_unused[i] = min(min_unused[i], unused)

        return sum_bad, sum_ok, min_unused


class Paragraph(reportlab.platypus.Paragraph):
    def __init__(self, items, style: ParagraphStyle, pdf: PDF):
        super().__init__(items, style)
        leading = pdf.leading_for(style)
        descent = pdf.descender(style)
        self.v_offset = style.fontSize * 1.2 - leading + descent / 2
        self._showBoundary = pdf.debug

    def drawOn(self, pdf: PDF, x, y, _sW=0):
        pdf.translate(0, self.v_offset)
        super().drawOn(pdf, x, y, _sW)
        pdf.translate(0, -self.v_offset)


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
