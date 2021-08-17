import warnings
from copy import copy
from typing import List, Optional, Tuple

from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

import para
from placed import PlacedContent, PlacedFlowableContent, PlacedGroupContent, PlacedPathContent, PlacedRectContent
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


def _make_cells_from_run(run: Run, pdf: PDF) -> (List[Paragraph], int):
    items = run.items

    spacer_count = sum(e.which == ElementType.SPACER for e in items)
    divider_count = sum(e.which == ElementType.DIVIDER for e in items)

    if divider_count + spacer_count == 0:
        # just a single line
        return [pdf.make_paragraph(run)], 0

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
    return row, divider_count


def make_row_from_run(run: Run, pdf: PDF, width: int) -> [Flowable]:
    row, dividers = _make_cells_from_run(run, pdf)
    if not dividers:
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


def key_values_layout(block: Block, bounds: Rect, pdf: PDF, style: str, rows: int) -> PlacedContent:
    items = [stats_runs(run, pdf) for run in block.content]

    padding = block.padding

    nRows = int(rows)
    box_style = pdf.style(style)
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

        placed0 = para.place_within(cell[0], r1.resize(width=r1.width - W3), pdf)
        placed1 = para.place_within(cell[1], r2, pdf)

        contents.append(placed0)
        contents.append(placed1)

        if W3:
            r3 = Rect(top=r1.top, bottom=r1.bottom, width=W3, right=r1.right)
            placed2 = para.place_within(cell[2], r3, pdf)
            contents.append(placed2)

        top = r2.bottom + 2 * padding

    content = PlacedGroupContent(contents, bounds)
    content.move(dx=(bounds.width - content.actual.width) / 2)
    return content


def badge_template(width: int, y: Tuple[int], shape: str, tags: List[str],
                   shape_style: Style, tag_style: Style, pdf: PDF) -> (PlacedGroupContent, Tuple[int]):
    height = y[6]
    r = y[1]
    b = Rect(left=0, right=width, top=0, bottom=height)

    if shape.startswith('oval'):
        path = pdf.beginPath()
        path.arc(0, 0, width, 0 + 2 * r, startAng=180, extent=180)

        path.lineTo(width, height - r)
        path.arcTo(0, height - 2 * r, width, height, startAng=0, extent=180)
        path.close()
        outer_shape = PlacedPathContent(path, b, shape_style, pdf=pdf, fill=True, stroke=True)
    elif shape.startswith('hex'):
        path = pdf.beginPath()
        path.moveTo(width / 2, 0)
        path.lineTo(width, 0 + r)
        path.lineTo(width, height - r)
        path.lineTo(width / 2, height)
        path.lineTo(0, height - r)
        path.lineTo(0, 0 + r)
        path.close()
        outer_shape = PlacedPathContent(path, b, shape_style, pdf=pdf, fill=True, stroke=True)
    elif shape.startswith('round'):
        outer_shape = PlacedRectContent(b, shape_style, pdf=pdf, fill=True, stroke=True, rounded=r // 2)
    else:
        if not shape.startswith('rect'):
            warnings.warn("Unknown shape '%s' for badge layout; using rectangle" % shape)
        outer_shape = PlacedRectContent(b, shape_style, pdf=pdf, fill=True, stroke=True)

    # Dividing lines
    path = pdf.beginPath()
    path.moveTo(0, y[2])
    path.lineTo(width, y[2])
    path.moveTo(0, y[4])
    path.lineTo(width, y[4])

    inner_shape = PlacedPathContent(path, b, shape_style, pdf=pdf, fill=False, stroke=True)
    group = [outer_shape, inner_shape]

    # tags
    if len(tags)> 0 and tags[0]:
        p = para.from_text(tags[0], tag_style, pdf)
        r = Rect(left=0, right=width, top=y[4], bottom=y[5])
        tag = para.align_vertically_within(p, r, pdf, posY=-1)
        group.append(tag)
    if len(tags)> 1 and tags[1]:
        p = para.from_text(tags[1], tag_style, pdf)
        r = Rect(left=0, right=width, top=y[1], bottom=y[2])
        tag = para.align_vertically_within(p, r, pdf, posY=1)
        group.append(tag)

    return PlacedGroupContent(group, b)


def badge_vertical_layout(width: int, tags: List[str], style: Style, tag_style: Style) -> Tuple[int]:
    # 20% extra for leading on the font sizes
    extreme = max(width / 2, style.size * 1.2)
    tag = tag_style.size * 1.2
    title = style.size * 1.2
    main = max(width-title, style.size * 2 * 1.2)

    upper_tag_ht = bool(len(tags) > 1 and tags[1]) * tag
    lower_tag_ht = bool(len(tags) > 0 and tags[0]) * tag

    height = main + title + 2 * extreme + upper_tag_ht + lower_tag_ht

    # Vertical dividing positions for the shape, rounded to integers
    y = (0, extreme, extreme + upper_tag_ht, extreme+upper_tag_ht + title, height - extreme - lower_tag_ht, height - extreme, height)
    return tuple(round(x) for x in y)


def add_stamp_values(stamp: PlacedGroupContent, y: Tuple[int], run: Run, pdf: PDF):
    contents = stamp.group
    width = stamp.requested.width

    style = pdf.style(run.base_style())
    styles = [style.modify(align='center'),
              style.modify(size=style.size * 2, align='center'),
              style.modify(size=round(style.size * 1.5), align='center'),
              style.modify(size=round(style.size * 1.5), align='center')]
    row = para.split_into_paragraphs(pdf, run, styles=styles)

    if len(row) > 0 and row[0]:
        r = Rect(left=0, right=width, top=y[2], bottom=y[3])
        p = para.align_vertically_within(row[0], r, pdf, posY=0)
        contents.append(p)
    if len(row) > 1 and row[1]:
        r = Rect(left=0, right=width, top=y[3], bottom=y[4])
        p = para.align_vertically_within(row[1], r, pdf, posY=0, metrics_adjust=0.75)
        contents.append(p)
    if len(row) > 2 and row[2]:
        r = Rect(left=0, right=width, top=y[5], bottom=y[6])
        contents.append(PlacedFlowableContent(row[2], r, pdf))
    if len(row) > 3 and row[3]:
        r = Rect(left=0, right=width, top=y[0], bottom=y[1])
        contents.append(PlacedFlowableContent(row[3], r, pdf))

    return PlacedGroupContent(contents, stamp.requested)


def badges_layout(block: Block, bounds: Rect, pdf: PDF, tags: str = None, shape: str = None,
                  style=None, padding=None) -> PlacedContent:
    n = len(block.content)

    tags = tags.split(',') if tags else []

    if padding is None:
        padding = block.padding

    content_style = pdf.style(block.base_style())
    tag_height = content_style.size * 2 / 3
    tag_style = content_style.modify(size=tag_height, align='center')
    width = (bounds.width - padding * (n - 1)) // n

    ypos = badge_vertical_layout(width, tags, content_style, tag_style)

    shape_style = pdf.style(style) if style else content_style
    stamp = badge_template(width, ypos, shape, tags, shape_style, tag_style, pdf)

    # Adjust for round off error in amiking the widths all integers
    left = bounds.left + (bounds.width - width * n - padding * (n - 1)) // 2

    items = []
    for i, run in enumerate(block.content):
        right = left + width
        badge = add_stamp_values(copy(stamp), ypos, run, pdf)
        badge.move(dx=left, dy=bounds.top)
        items.append(badge)
        left = right + padding

    return PlacedGroupContent(items, bounds)
