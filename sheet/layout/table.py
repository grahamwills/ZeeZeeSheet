from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

from common import Rect
from model import Block, Element, ElementType, Run
from pdf import PDF
from render import PlacedContent, PlacedFlowableContent


def _add_run(elements: [Element], row: [], pdf: PDF, align: str):
    if elements:
        para = pdf.make_paragraph(Run(elements), align=align)
        row.append(para)


def make_row_from_run(run: [Element], pdf: PDF, width: int) -> [Flowable]:
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
        alignments = ['left'] * (spacer_count - 2) + ['center', 'right']

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
        return [as_table([row], width)]
    else:
        return row


def as_one_line(run: Run, pdf: PDF, width: int):
    if not any(e.which == ElementType.SPACER for e in run.items):
        # No spacers -- nice and simple
        p = pdf.make_paragraph(run)
        w, h = p.wrapOn(pdf, width, 1000)
        return p, w, h

    # Make a one-row table
    cells = [make_row_from_run(run, pdf, width)]
    return make_table(pdf, cells, width)


def table_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    cells = [make_row_from_run(run, pdf, bounds.width) for run in block.content]
    table, w, h = make_table(pdf, cells, bounds.width)
    return PlacedFlowableContent(table, bounds.resize(width=w, height=h))


def make_table(pdf, paragraphs, width):
    table = as_table(paragraphs, width)
    w, h = table.wrapOn(pdf, width, 1000)
    return table, w, h


def _estimate_col_width(cells: [[Flowable]], col: int) -> float:
    mx = 1
    for row in cells:
        if col < len(row) and isinstance(row[col], Paragraph):
            p: Paragraph = row[col]
            t = sum(len(f.text) * f.fontSize for f in p.frags)
            mx = max(mx, t)
    return mx


def as_table(cells, width: int):
    commands = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]

    estimated_widths = [_estimate_col_width(cells, i) for i in range(0, len(cells[0]))]

    factor = width / sum(estimated_widths)
    colWidths = [w * factor for w in estimated_widths]


    return Table(cells, colWidths=colWidths, style=(TableStyle(commands)))
