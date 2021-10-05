from typing import Dict, List, Sequence, Tuple

import reportlab
from colour import Color
from reportlab.platypus import Flowable

from structure import Element, ElementType, Run, Style
from util import configured_logger
from .pdf import PDF, _CHECKED_BOX, _UNCHECKED_BOX, line_info, make_paragraph_style

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
        pStyle = make_paragraph_style(style.align, style.font, style.size, leading, style.opacity, style.color.rgb)

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


def _element_to_html(e: Element, pdf: PDF, base_style: Style):
    if e.which == ElementType.TEXT or e.which == ElementType.SYMBOL:
        txt = e.value
    else:
        txt = str(e)

    style = e.style

    if style.italic:
        txt = '<i>' + txt + '</i>'
    if style.bold:
        txt = '<b>' + txt + '</b>'

    if style.size and style.size != base_style.size:
        size = " size='%d'" % style.size
    else:
        size = ''

    if style.font and style.font != base_style.font:
        face = " face='%s'" % style.font
    else:
        face = ''

    if style.color and (style.color != base_style.color or style.opacity != base_style.opacity):
        opacity = style.opacity if style.opacity is not None else 1.0
        color = " color='rgba(%d, %d, %d, %1.2f)'" % (
            round(255 * style.color.get_red()),
            round(255 * style.color.get_green()),
            round(255 * style.color.get_blue()),
            opacity
        )
    else:
        color = ''

    if e.which == ElementType.CHECKBOX:
        target = _UNCHECKED_BOX if e.value in {'O', 'o', ' ', '0'} else _CHECKED_BOX
        return "<img height=%d width=%d src='%s'/>" % (style.size, style.size, target)
    if e.which != ElementType.TEXT:
        face = " face='Symbola'"
    if face or size or color:
        return "<font %s%s%s>%s</font>" % (face, size, color, txt)
    else:
        return txt
