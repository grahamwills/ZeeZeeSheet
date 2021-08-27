import warnings
from copy import copy
from functools import lru_cache
from typing import List, Optional, Tuple

from reportlab.platypus import Flowable, Paragraph

import layoutparagraph
import layoutparagraph as para1
import layoutparagraph as para2
from flowable import Table
from placed import PlacedContent, PlacedGroupContent, PlacedParagraphContent, PlacedPathContent, PlacedRectContent, \
    PlacedTableContent
from sheet import common
from sheet.common import Rect
from sheet.model import Block, Element, ElementType, Run
from sheet.optimize import BadParametersError, Optimizer, divide_space
from sheet.pdf import PDF
from sheet.style import Style

LOGGER = common.configured_logger(__name__)


def _add_run(elements: [Element], row: [], pdf: PDF, align: str):
    if elements:
        para = para1.make_paragraph(Run(elements), pdf, align)
        row.append(para)


def _make_cells_from_run(run: Run, pdf: PDF) -> (List[Paragraph], int):
    items = run.items

    spacer_count = sum(e.which == ElementType.SPACER for e in items)
    divider_count = sum(e.which == ElementType.DIVIDER for e in items)

    if divider_count + spacer_count == 0:
        # just a single line
        return [layoutparagraph.make_paragraph(run, pdf)], 0

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


@lru_cache(maxsize=2048)
def make_row_from_run(run: Run, pdf: PDF, bounds: Rect) -> [Flowable]:
    row, dividers = _make_cells_from_run(run, pdf)
    if not dividers:
        # Make a sub-table just for this line
        return [as_table([row], bounds, pdf, 0)]
    else:
        return row


def one_line_flowable(run: Run, bounds: Rect, padding: int, pdf: PDF):
    if any(e.which == ElementType.SPACER for e in run.items):
        # Make a one-row table
        cells = [make_row_from_run(run, pdf, bounds)]
        return as_table(cells, bounds, pdf, padding, return_as_placed=True)
    else:
        # No spacers -- nice and simple
        p = layoutparagraph.make_paragraph(run, pdf)
        return PlacedParagraphContent(p, bounds, pdf)


def table_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    cells = [make_row_from_run(run, pdf, bounds) for run in block.content]
    return as_table(cells, bounds, pdf, block.spacing.padding, return_as_placed=True)


class TableColumnsOptimizer(Optimizer[PlacedTableContent]):

    def __init__(self, cells: [[]], padding: int, bounds: Rect, pdf: PDF) -> None:
        ncols = max(len(row) for row in cells)
        super().__init__(ncols)
        self.padding = padding
        self.cells = cells
        self.bounds = bounds
        self.available_width = bounds.width - (ncols - 1) * padding
        self.pdf = pdf

    def make(self, x: [float]) -> Optional[PlacedTableContent]:
        LOGGER.fine("Trying table with divisions = %s", x)
        widths = divide_space(x, self.available_width, 10, granularity=5)
        return self._make(widths)

    def _make(self, widths):
        table = Table(self.cells, self.padding, widths, self.pdf)
        return PlacedTableContent(table, self.bounds, self.pdf)

    def score(self, placed: PlacedTableContent) -> float:
        return placed.error_from_breaks(100, 5) + placed.error_from_variance(0.1)

    def __hash__(self):
        return id(self)


def as_table(cells, bounds: Rect, pdf: PDF, padding: int, return_as_placed=False):
    ncols = max(len(row) for row in cells)
    width = bounds.width
    if ncols * 10 >= width:
        LOGGER.debug("Cannot fit %d columns into a table of width %d", ncols, width)
        raise BadParametersError("Columns too small for table", ncols * 10 - width)
    elif ncols == 1:
        table = Table(cells, padding, [width], pdf)
        if return_as_placed:
            return PlacedTableContent(table, bounds, pdf)
        else:
            return table
    else:
        optimizer = TableColumnsOptimizer(cells, padding, bounds, pdf)
        placed, _ = optimizer.run(method='Nelder-Mead')
        if return_as_placed:
            return placed
        else:
            return placed.table


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
                run1 = Run(items[start:i])
                row.append(para1.make_paragraph(run1, pdf, 'center', multiplier))
            if e.which == ElementType.SPACER:
                spacer_idx += 1
            start = i + 1

    if len(row) == 1:
        multiplier = 1.5
    else:
        multiplier = 1.0
    if items[start:]:
        run2 = Run(items[start:])
        para = para2.make_paragraph(run2, pdf, 'center', multiplier)
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


def thermometer_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    nRows = int(block.method.options.get('rows', 6))
    text_style = block.style
    thermo_style = block.method.options.get('style', block.style)

    overrides = [
        text_style.clone(align='center'),
        text_style.clone(align='center', size=text_style.size * 1.5),
        text_style.clone(align='center')
    ]

    items = [layoutparagraph.split_into_paragraphs(run, pdf, overrides) for run in block.content]

    padding = block.spacing.padding

    H1 = overrides[0].size + 2 * padding
    W1 = 2 * padding + round(_col_width(items, 0, pdf))

    H2 = overrides[1].size + 2 * padding
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

        r2 = Rect.make(left=left, top=top, height=H2, width=W2)
        r1 = Rect.make(left=r2.right, top=top + (H2 - H1) / 2, width=W1 + W3, height=H1)

        # Extend under the other rectangle to hide joins of 'round edges'
        box = r1.move(dx=-H1).resize(width=r1.width + H1)
        contents.append(PlacedRectContent(box, thermo_style, PDF.FILL, pdf, rounded=rounded))
        contents.append(PlacedRectContent(r2, thermo_style, PDF.FILL, pdf, rounded=rounded))

        placed0 = layoutparagraph.align_vertically_within(cell[0], r1.resize(width=r1.width - W3), pdf,
                                                          metrics_adjust=-0.2)
        placed1 = layoutparagraph.align_vertically_within(cell[1], r2, pdf, metrics_adjust=-0.2)

        contents.append(placed0)
        contents.append(placed1)

        if W3:
            r3 = Rect.make(top=r1.top, bottom=r1.bottom, width=W3, right=r1.right)
            placed2 = layoutparagraph.align_vertically_within(cell[2], r3, pdf, metrics_adjust=-0.2)
            contents.append(placed2)

        top = r2.bottom + 2 * padding

    content = PlacedGroupContent(contents, bounds)
    content.move(dx=(bounds.width - content.actual.width) / 2)
    return content


def badge_template(width: int, y: Tuple[int], shape: str, tags: List[str],
                   shape_style: Style, tag_style: Style, pdf: PDF) -> (PlacedGroupContent, Tuple[int]):
    height = y[6]
    r = y[1]
    b = Rect.make(left=0, right=width, top=0, bottom=height)

    shape = shape or 'oval'

    if shape.startswith('oval'):
        path = pdf.beginPath()
        path.arc(0, 0, width, 0 + 2 * r, startAng=180, extent=180)

        path.lineTo(width, height - r)
        path.arcTo(0, height - 2 * r, width, height, startAng=0, extent=180)
        path.close()
        outer_shape = PlacedPathContent(path, b, shape_style, PDF.BOTH, pdf)
    elif shape.startswith('hex'):
        path = pdf.beginPath()
        path.moveTo(width / 2, 0)
        path.lineTo(width, 0 + r)
        path.lineTo(width, height - r)
        path.lineTo(width / 2, height)
        path.lineTo(0, height - r)
        path.lineTo(0, 0 + r)
        path.close()
        outer_shape = PlacedPathContent(path, b, shape_style, PDF.BOTH, pdf)
    elif shape.startswith('round'):
        outer_shape = PlacedRectContent(b, shape_style, PDF.BOTH, pdf, rounded=r // 2)
    else:
        if not shape.startswith('rect'):
            warnings.warn("Unknown shape '%s' for badge layout; using rectangle" % shape)
        outer_shape = PlacedRectContent(b, shape_style, PDF.BOTH, pdf)

    # Dividing lines
    path = pdf.beginPath()
    path.moveTo(0, y[2])
    path.lineTo(width, y[2])
    path.moveTo(0, y[4])
    path.lineTo(width, y[4])

    inner_shape = PlacedPathContent(path, b, shape_style, PDF.STROKE, pdf)
    group = [outer_shape, inner_shape]

    # tags
    if len(tags) > 0 and tags[0]:
        p = layoutparagraph.from_text(tags[0], tag_style, pdf)
        r = Rect.make(left=0, right=width, top=y[4], bottom=y[5])
        tag = layoutparagraph.align_vertically_within(p, r, pdf, posY=-1)
        group.append(tag)
    if len(tags) > 1 and tags[1]:
        p = layoutparagraph.from_text(tags[1], tag_style, pdf)
        r = Rect.make(left=0, right=width, top=y[1], bottom=y[2])
        tag = layoutparagraph.align_vertically_within(p, r, pdf, posY=1)
        group.append(tag)

    return PlacedGroupContent(group, b)


def badge_vertical_layout(width: int, tags: List[str], style: Style, tag_style: Style) -> Tuple[int]:
    # 20% extra for leading on the font sizes
    extreme = max(width / 2, style.size * 1.2)
    tag = tag_style.size * 1.2
    title = style.size * 1.2
    main = max(width - title, style.size * 2 * 1.2)

    upper_tag_ht = bool(len(tags) > 1 and tags[1]) * tag
    lower_tag_ht = bool(len(tags) > 0 and tags[0]) * tag

    height = main + title + 2 * extreme + upper_tag_ht + lower_tag_ht

    # Vertical dividing positions for the shape, rounded to integers
    y = (0, extreme, extreme + upper_tag_ht, extreme + upper_tag_ht + title, height - extreme - lower_tag_ht,
         height - extreme, height)
    return tuple(round(x) for x in y)


def add_stamp_values(stamp: PlacedGroupContent, y: Tuple[int], run: Run, pdf: PDF):
    contents = stamp.group
    width = stamp.requested.width

    style = run.style()
    styles = [style.clone(align='center'),
              style.clone(size=style.size * 2, align='center'),
              style.clone(size=round(style.size * 1.25), align='center'),
              style.clone(size=round(style.size * 1.25), align='center')]
    row = layoutparagraph.split_into_paragraphs(run, pdf, styles=styles)

    if len(row) > 0 and row[0]:
        r = Rect.make(left=0, right=width, top=y[2], bottom=y[3])
        p = layoutparagraph.align_vertically_within(row[0], r, pdf, metrics_adjust=0)
        contents.append(p)
    if len(row) > 1 and row[1]:
        r = Rect.make(left=0, right=width, top=y[3], bottom=y[4])
        p = layoutparagraph.align_vertically_within(row[1], r, pdf, metrics_adjust=0.75)
        contents.append(p)
    if len(row) > 2 and row[2]:
        r = Rect.make(left=0, right=width, top=y[5], bottom=y[6])
        p = layoutparagraph.align_vertically_within(row[2], r, pdf)
        contents.append(p)
    if len(row) > 3 and row[3]:
        r = Rect.make(left=0, right=width, top=y[0], bottom=y[1])
        p = layoutparagraph.align_vertically_within(row[3], r, pdf, metrics_adjust=1)
        contents.append(p)

    return PlacedGroupContent(contents, stamp.requested)


def badges_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    n = len(block.content)

    shape = block.method.options.get('shape', 'oval')
    tags = block.method.options.get('tags', '').split(',')

    padding = block.spacing.padding

    shape_style = block.method.options.get('shape-style', block.style)
    tag_height = shape_style.size * 2 / 3

    tag_style = shape_style.clone(size=tag_height, align='center')
    width = (bounds.width - padding * (n - 1)) // n

    ypos = badge_vertical_layout(width, tags, block.style, tag_style)

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
