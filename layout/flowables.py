from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

import reportlab
from colour import Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable
from reportlab.platypus.paragraph import _SplitFrag, _SplitWord

from structure import Run, Style
from util import configured_logger
from .pdf import PDF, _element_to_html

LOGGER = configured_logger(__name__)


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

    def calculate_issues(self) -> Tuple[int, int, List[int]]:
        """ Calculate breaks and unused space """
        min_unused = [self.width] * self.ncols
        sum_bad = 0
        sum_ok = 0

        for row in self.cells:
            for idx, cell in enumerate(row):

                try:
                    tbad, tok, tunused = cell.calculate_issues()
                    sum_bad += tbad
                    sum_ok += tok
                    unused = sum(tunused)
                except:
                    bad_breaks, ok_breaks, unused = line_info(cell)
                    sum_bad += bad_breaks
                    sum_ok += ok_breaks

                # Divide unused up evenly across columns
                if idx < self.ncols - 1 and cell == row[-1]:
                    # The last cell goes to the end of the row
                    unused /= self.ncols - idx
                    for i in range(idx, self.ncols):
                        min_unused[i] = min(min_unused[i], unused)
                else:
                    min_unused[idx] = min(min_unused[idx], unused)

        return sum_bad, sum_ok, min_unused

    def __str__(self):
        contents = " | ".join([str(c) for row in self.cells for c in row][:4])
        if self.ncols * len(self.cells) > 4:
            contents += '| \u2026'
        return "T(%dx%x • %s • %s)" % (self.ncols, len(self.cells), self.colWidths, contents)


class Paragraph(reportlab.platypus.Paragraph):

    def __init__(self, run: Run, style: Style, pdf: PDF):
        self.run = run
        self.pdf = PDF
        leading = pdf.paragraph_leading_for(run)
        pStyle = _make_paragraph_style(style.align, style.font, style.size, leading, style.opacity, style.color.rgb)

        # Add spaces between check boxes and other items
        items = []
        for e in run.items:
            # Strangely, non-breaking space allows breaks to happen between images, whereas simple spaces do not
            if e is not run.items[0] and not e.value[0] in ":;-=":
                items.append('<font size=0>&nbsp;</font> ')
            items.append(_element_to_html(e, pdf, style))

        super().__init__("".join(items), pStyle)
        leading = pdf.leading_for(style)
        descent = pdf.descender(style)
        self.v_offset = style.size * 1.2 - leading + descent / 2

    def drawOn(self, pdf: PDF, x, y, _sW=0):
        if pdf.debug:
            pdf.setStrokeColor(Color('gray'))
            pdf.rect(0, 0, self.width, self.height)

        pdf.translate(0, self.v_offset)
        super().drawOn(pdf, x, y, _sW)
        pdf.translate(0, -self.v_offset)

    def __str__(self):
        txt = str(self.run)
        if len(txt) > 25:
            txt = txt[:24] + '\u2026'
        return "P({0})".format(txt)


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


@lru_cache
def _make_paragraph_style(align, font, size, leading, opacity, rgb):
    alignment = {'left': 0, 'center': 1, 'right': 2, 'fill': 4, 'justify': 4}[align]
    opacity = float(opacity) if opacity is not None else 1.0
    color = reportlab.lib.colors.Color(*rgb, alpha=opacity)
    return ParagraphStyle(name='_tmp', spaceShrinkage=0.1,
                          fontName=font, fontSize=size, leading=leading,
                          allowWidows=0, embeddedHyphenation=1, alignment=alignment,
                          hyphenationMinWordLength=1,
                          textColor=color)
