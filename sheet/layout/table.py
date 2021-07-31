from copy import copy

from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

import common
from common import Rect
from model import Block, Element, ElementType, Run, Style
from pdf import PDF
from render import PlacedContent, PlacedFlowableContent, PlacedGroupContent, PlacedRectContent

LOGGER = common.configured_logger(__name__)


def _add_run(elements: [Element], row: [], pdf: PDF, align: str):
    if elements:
        para = pdf.make_paragraph(Run(elements), align=align)
        row.append(para)


def make_row_from_run(run: [Element], pdf: PDF, width: int, padding: int) -> [Flowable]:
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


def as_one_line(run: Run, pdf: PDF, width: int, padding: int):
    if not any(e.which == ElementType.SPACER for e in run.items):
        # No spacers -- nice and simple
        p = pdf.make_paragraph(run)
        w, h = p.wrapOn(pdf, width, 1000)
        return p, w, h

    # Make a one-row table
    cells = [make_row_from_run(run, pdf, width, padding)]
    return make_table(pdf, cells, width, padding)


def table_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    cells = [make_row_from_run(run, pdf, bounds.width, block.padding) for run in block.content]
    table, w, h = make_table(pdf, cells, bounds.width, block.padding)
    return PlacedFlowableContent(table, bounds.resize(width=w, height=h))


def make_table(pdf, paragraphs, width, padding):
    table = as_table(paragraphs, width, pdf, padding)
    w, h = table.wrapOn(pdf, width, 1000)
    return table, w, h


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

    estimated_widths = [_col_width(cells, i, pdf) for i in range(0, len(cells[0]))]

    # Pad short rows and add spans for them
    nCols = max(len(row) for row in cells)
    for i, row in enumerate(cells):
        n = len(row)
        if n < nCols:
            row.extend([' '] * (nCols - n))
            commands.append((('SPAN'), (n - 1, i), (-1, i)))

    factor = width / sum(estimated_widths)
    colWidths = [w * factor for w in estimated_widths]

    return Table(cells, colWidths=colWidths, style=(TableStyle(commands)))


def center_text(p: Flowable, bounds: Rect, pdf: PDF, style: Style) -> Rect:
    p.wrapOn(pdf, bounds.width, bounds.height)
    top = bounds.top + (bounds.height - style.size) / 2
    return Rect(left=bounds.left, top=top, width=bounds.width, height=style.size)


def stats_runs(run: [Element], pdf: PDF) -> [Paragraph]:
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


def _col_width(cells: [[Paragraph]], col: int, pdf: PDF) -> float:
    nCols = max(len(r) for r in cells)
    mx = 1
    for row in cells:
        # Only check for paragraphs and for rows that don't span multiple columns
        if len(row) == nCols and isinstance(row[col], Paragraph):
            p: Paragraph = row[col]
            t = sum(pdf.stringWidth(f.text, f.fontName, f.fontSize) for f in p.frags)
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
        W3 = 2 * padding + round(_col_width(items, 2, pdf))
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
        contents.append(
            PlacedRectContent(r1.move(dx=-H1).resize(width=r1.width + H1), box_style, True, False, rounded=rounded))
        contents.append(PlacedRectContent(r2, box_style, True, False, rounded=rounded))

        cell[0].wrapOn(pdf, r1.width, r1.height)
        cell[1].wrapOn(pdf, r2.width, r2.height)
        b1 = center_text(cell[0], r1.resize(width=r1.width - W3), pdf, text_style)
        b2 = center_text(cell[1], r2, pdf, text_style_1).move(dy=1)
        contents.append(PlacedFlowableContent(cell[0], b1))
        contents.append(PlacedFlowableContent(cell[1], b2))

        if W3:
            r3 = Rect(top=r1.top, bottom=r1.bottom, width=W3, right=r1.right)
            cell[2].wrapOn(pdf, r3.width, r3.height)
            b3 = center_text(cell[2], r3, pdf, text_style)
            contents.append(PlacedFlowableContent(cell[2], b3))

        top = r2.bottom + 2 * padding

    content = PlacedGroupContent(contents)
    content.move(dx=(bounds.width - content.bounds.width) / 2)
    content.add_fit_err(bounds)
    return content
