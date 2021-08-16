from copy import copy
from typing import List, Optional

from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

from placed import PlacedContent, PlacedFlowableContent, PlacedGroupContent, PlacedRectContent
from sheet import common
from sheet.common import Rect
from sheet.model import Block, Element, ElementType, Run
from sheet.optimize import Optimizer, divide_space
from sheet.pdf import PDF
from style import Style

LOGGER = common.configured_logger(__name__)


def _add_run(elements: [Element], row: [], pdf: PDF, align: str):
    if elements:
        para = pdf.make_paragraph(Run(elements), align=align)
        row.append(para)


def make_row_from_run(run: Run, pdf: PDF, width: int) -> [Flowable]:
    items = run.items

    spacer_count = sum(e.which == ElementType.SPACER for e in items)
    divider_count = sum(e.which == ElementType.DIVIDER for e in items)

    if divider_count + spacer_count == 0:
        # just a single line
        return [pdf.make_paragraph(run)]

    # Establish spacing patterns
    if spacer_count < 2:
        alignments = ['left', 'right']
    else:
        alignments = ['left'] * (spacer_count - 1) + ['center', 'right']

    row = []
    start = 0
    spacer_idx = 0
    for i, e in enumerate(items):
        if e.which in {ElementType.SPACER, ElementType.DIVIDER}:
            _add_run(items[start:i], row, pdf, alignments[spacer_idx])
            if e.which == ElementType.SPACER:
                spacer_idx += 1
            start = i + 1

    _add_run(items[start:], row, pdf, alignments[spacer_idx])

    if divider_count == 0:
        # Make a sub-table just for this line
        return [as_table([row], width, pdf, 0)]
    else:
        return row


def one_line_flowable(run: Run, bounds: Rect, padding: int, pdf: PDF):
    if any(e.which == ElementType.SPACER for e in run.items):
        # Make a one-row table
        cells = [make_row_from_run(run, pdf, bounds.width)]
        table = as_table(cells, bounds.width, pdf, padding)
        return PlacedFlowableContent(table, bounds, pdf)
    else:
        # No spacers -- nice and simple
        p = pdf.make_paragraph(run)
        return PlacedFlowableContent(p, bounds, pdf)


def table_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    cells = [make_row_from_run(run, pdf, bounds.width) for run in block.content]
    table = as_table(cells, bounds.width, pdf, block.padding)
    return PlacedFlowableContent(table, bounds, pdf)


class TableColumnsOptimizer(Optimizer):

    def __init__(self, cells: [[]], style: TableStyle, width: int, pdf: PDF) -> None:
        ncols = max(len(row) for row in cells)
        super().__init__(ncols)
        self.cells = cells
        self.style = style
        self.width = width
        self.pdf = pdf

    def make(self, x: [float]) -> Optional[PlacedFlowableContent]:
        LOGGER.debug("Trying table with divisions = %s", x)
        try:
            widths = divide_space(x, self.width, 10, granularity=5)
        except ValueError:
            LOGGER.warn("Too little space to fit table")
            return None
        table = Table(self.cells, style=self.style, colWidths=widths)
        return PlacedFlowableContent(table, Rect(left=0, top=0, width=self.width, height=1000), self.pdf)

    def score(self, placed: PlacedFlowableContent) -> float:
        s = placed.error_from_breaks(100, 5) + placed.error_from_variance(0.1)
        # LOGGER.debug("Score = %1.3f (breaks=%1.3f, var=%1.3f)", s, placed.error_from_breaks(100, 10),
        #              placed.error_from_variance(1))
        return s


def as_table(cells, width: int, pdf: PDF, padding: int):
    commands = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('TOPPADDING', (0, 0), (-1, 0), 0),
        ('LEFTPADDING', (1, 0), (-1, -1), padding),
        ('TOPPADDING', (0, 1), (-1, -1), padding),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]

    ncols = max(len(row) for row in cells)
    if ncols * 10 >= width:
        LOGGER.debug("Cannot fit %d columns into a table of width %d", ncols, width)
    elif ncols > 1:
        # Pad short rows and add spans for them
        for i, row in enumerate(cells):
            n = len(row)
            if n < ncols:
                row.extend([' '] * (ncols - n))
                commands.append(('SPAN', (n - 1, i), (-1, i)))

        optimizer = TableColumnsOptimizer(cells, TableStyle(commands), width, pdf)
        placed, _ = optimizer.run(method='Nelder-Mead')
        if placed:
            return placed.flowable

    return Table(cells, style=(TableStyle(commands)))


def center_text(p: Paragraph, bounds: Rect, pdf: PDF, style: Style) -> Rect:
    p.wrapOn(pdf, bounds.width, bounds.height)
    desc = -p.blPara.descent
    top = bounds.top + (bounds.height - style.size) / 2 - desc / 2
    return Rect(left=bounds.left, top=top, width=bounds.width, height=style.size)


def stats_runs(run: [Element], pdf: PDF) -> List[Paragraph]:
    items = run.items
    row = []
    start = 0
    spacer_idx = 0
    for i, e in enumerate(items):
        if e.which in {ElementType.SPACER, ElementType.DIVIDER}:
            if len(row) == 1:
                multiplier = 1.5
            else:
                multiplier = 1.0
            if items[start:i]:
                row.append(pdf.make_paragraph(Run(items[start:i]), align='center', size_factor=multiplier))
            if e.which == ElementType.SPACER:
                spacer_idx += 1
            start = i + 1

    if len(row) == 1:
        multiplier = 1.5
    else:
        multiplier = 1.0
    if items[start:]:
        para = pdf.make_paragraph(Run(items[start:]), align='center', size_factor=multiplier)
        row.append(para)
    return row


def _frag_width(f, pdf) -> float:
    if hasattr(f, 'width'):
        return f.width
    else:
        return pdf.stringWidth(f.text, f.fontName, f.fontSize)


def _col_width(cells: [[Paragraph]], col: int, pdf: PDF) -> float:
    nCols = max(len(r) for r in cells)
    mx = 1
    for row in cells:
        # Only check for paragraphs and for rows that don't span multiple columns
        if len(row) == nCols and isinstance(row[col], Paragraph):
            p: Paragraph = row[col]
            t = sum(_frag_width(f, pdf) for f in p.frags)
            mx = max(mx, t)
    return mx


def key_values_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    items = [stats_runs(run, pdf) for run in block.content]

    padding = block.padding

    nRows = int(block.block_method.options['rows'])
    box_style = pdf.style(block.block_method.options['style'])
    text_style = pdf.style(block.base_style())
    text_style_1 = copy(text_style)
    text_style_1.size = text_style_1.size * 3 // 2
    H1 = text_style.size + 2 * padding
    W1 = 2 * padding + round(_col_width(items, 0, pdf))

    H2 = text_style_1.size + 2 * padding
    W2 = 4 * padding + round(_col_width(items, 1, pdf))

    try:
        W3 = 4 * padding + round(_col_width(items, 2, pdf))
    except:
        W3 = 0

    rounded = (H2 - H1)

    LOGGER.debug("Key Values Layout for %d items, W1=%d, W2=%d, W3=%d", len(items), W1, W2, W3)

    contents = []

    top = bounds.top
    left = bounds.left
    for i, cell in enumerate(items):
        if contents and i % nRows == 0:
            top = bounds.top
            left += W1 + W2 + W3 + 2 * padding
        r2 = Rect(left=left, top=top, height=H2, width=W2)
        r1 = Rect(left=r2.right, top=top + (H2 - H1) / 2, width=W1 + W3, height=H1)

        # Extend under the other rectangle to hide joins of 'round edges'
        box = r1.move(dx=-H1).resize(width=r1.width + H1)
        contents.append(PlacedRectContent(box, box_style, pdf, True, False, rounded=rounded))
        contents.append(PlacedRectContent(r2, box_style, pdf, True, False, rounded=rounded))

        cell[0].wrapOn(pdf, r1.width, r1.height)
        cell[1].wrapOn(pdf, r2.width, r2.height)
        b1 = center_text(cell[0], r1.resize(width=r1.width - W3), pdf, text_style)
        b2 = center_text(cell[1], r2, pdf, text_style_1)
        contents.append(PlacedFlowableContent(cell[0], b1, pdf))
        contents.append(PlacedFlowableContent(cell[1], b2, pdf))

        if W3:
            r3 = Rect(top=r1.top, bottom=r1.bottom, width=W3, right=r1.right)
            cell[2].wrapOn(pdf, r3.width, r3.height)
            b3 = center_text(cell[2], r3, pdf, text_style)
            contents.append(PlacedFlowableContent(cell[2], b3, pdf))

        top = r2.bottom + 2 * padding

    content = PlacedGroupContent(contents, bounds)
    content.move(dx=(bounds.width - content.actual.width) / 2)
    return content
