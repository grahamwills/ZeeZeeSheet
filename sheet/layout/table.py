from typing import List

from reportlab.platypus import Paragraph, Table, TableStyle

from common import Rect
from model import Block, Element, ElementType, Run
from pdf import PDF
from render import PlacedContent, flowable_content


def _add_run(elements:[Element], row:[], pdf: PDF, align:str):
    if elements:
        para = pdf.make_paragraph(Run(elements), align=align)
        row.append(para)


def make_row_from_run(run, pdf:PDF) -> [Paragraph]:
    items = run.items

    # Establish spacing patterns
    spacer_count = sum(e.which == ElementType.SPACER for e in items)
    if spacer_count <2:
        alignments = ['left', 'right']
    else:
        alignments = ['left'] * (spacer_count-2) + ['center', 'right']

    row = []
    start = 0
    spacer_idx = 0
    for i, e in  enumerate(items):
        if e.which in {ElementType.SPACER, ElementType.DIVIDER}:
            _add_run(items[start:i], row, pdf, alignments[spacer_idx])
            if e.which == ElementType.SPACER:
                spacer_idx += 1
            start = i+1

    _add_run(items[start:], row, pdf, alignments[spacer_idx])
    return row


def as_one_line(run: Run, pdf: PDF, width: int):
    if not any(e.which == ElementType.SPACER for e in run.items):
        # No spacers -- nice and simple
        p = pdf.make_paragraph(run)
        w, h = p.wrapOn(pdf, width, 1000)
        return p, w, h

    # Make a one-row table
    cells = [make_row_from_run(run, pdf)]
    return make_table(pdf, cells, width)


def table_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    cells = [make_row_from_run(run, pdf) for run in block.content]
    table, w, h = make_table(pdf, cells, bounds.width)
    return flowable_content(table, bounds.resize(width=w, height=h))


def make_table(pdf, paragraphs, width):
    table = Table(paragraphs)
    commands = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]
    table.setStyle(TableStyle(commands))
    w, h = table.wrapOn(pdf, width, 1000)
    return table, w, h
