import functools
import warnings
from copy import copy
from functools import lru_cache
from typing import Callable, List, Optional, Sequence, Tuple, Union

from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable, Image, Paragraph

from structure import Block, Element, ElementType, Run, Spacing, Style
from util import BadParametersError, Margins, Optimizer, Rect, configured_logger, divide_space
from .flowables import Paragraph, Table
from .pdf import PDF
from .content import ErrorContent, ClipContent, Content, GroupContent, ImageContent, \
    ParagraphContent, PathContent, RectContent, TableContent

LOGGER = configured_logger(__name__)


# Patch with more efficient versions

@lru_cache
def stringWidth(text, fontName, fontSize, encoding='utf8'):
    return pdfmetrics.getFont(fontName).stringWidth(text, fontSize, encoding=encoding)


pdfmetrics.stringWidth = stringWidth


def _add_run(elements: [Element], row: [], pdf: PDF, align: str):
    if elements:
        para = make_paragraph(Run(elements), pdf, align)
        row.append(para)


def _make_cells_from_run(run: Run, pdf: PDF) -> (List[Paragraph], int):
    items = run.items

    spacer_count = sum(e.which == ElementType.SPACER for e in items)
    divider_count = sum(e.which == ElementType.DIVIDER for e in items)

    if divider_count + spacer_count == 0:
        # just a single line
        return [make_paragraph(run, pdf)], 0

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
        p = make_paragraph(run, pdf)
        return ParagraphContent(p, bounds, pdf)


def table_layout(block: Block, bounds: Rect, pdf: PDF) -> Content:
    cells = [make_row_from_run(run, pdf, bounds) for run in block.content]
    return as_table(cells, bounds, pdf, block.spacing.padding, return_as_placed=True)


class TableColumnsOptimizer(Optimizer[TableContent]):

    def __init__(self, cells: [[]], padding: int, bounds: Rect, pdf: PDF) -> None:
        ncols = max(len(row) for row in cells)
        super().__init__(ncols)
        self.padding = padding
        self.cells = cells
        self.bounds = bounds
        self.available_width = bounds.width - (ncols - 1) * padding
        self.pdf = pdf

    def make(self, x: [float]) -> Optional[TableContent]:
        LOGGER.fine("Trying table with divisions = %s", x)
        widths = divide_space(x, self.available_width, 10, granularity=5)
        return self._make(widths)

    def _make(self, widths):
        table = Table(self.cells, self.padding, widths, self.pdf)
        return TableContent(table, self.bounds, self.pdf)

    def score(self, placed: TableContent) -> float:
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
            return TableContent(table, bounds, pdf)
        else:
            return table
    else:
        optimizer = TableColumnsOptimizer(cells, padding, bounds, pdf)
        placed, _ = optimizer.run()
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
                row.append(make_paragraph(run1, pdf, 'center', multiplier))
            if e.which == ElementType.SPACER:
                spacer_idx += 1
            start = i + 1

    if len(row) == 1:
        multiplier = 1.5
    else:
        multiplier = 1.0
    if items[start:]:
        run2 = Run(items[start:])
        para = make_paragraph(run2, pdf, 'center', multiplier)
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


def thermometer_layout(block: Block, bounds: Rect, pdf: PDF) -> Content:
    nRows = int(block.method.options.get('rows', 6))
    text_style = block.style
    thermo_style = block.method.options.get('style', block.style)

    overrides = [
        text_style.clone(align='center'),
        text_style.clone(align='center', size=text_style.size * 1.5),
        text_style.clone(align='center')
    ]

    items = [split_into_paragraphs(run, pdf, overrides) for run in block.content]

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
        contents.append(RectContent(box, thermo_style, PDF.FILL, pdf, rounded=rounded))
        contents.append(RectContent(r2, thermo_style, PDF.FILL, pdf, rounded=rounded))

        placed0 = align_vertically_within(cell[0], r1.resize(width=r1.width - W3), pdf,
                                          metrics_adjust=-0.2)
        placed1 = align_vertically_within(cell[1], r2, pdf, metrics_adjust=-0.2)

        contents.append(placed0)
        contents.append(placed1)

        if W3:
            r3 = Rect.make(top=r1.top, bottom=r1.bottom, width=W3, right=r1.right)
            placed2 = align_vertically_within(cell[2], r3, pdf, metrics_adjust=-0.2)
            contents.append(placed2)

        top = r2.bottom + 2 * padding

    content = GroupContent(contents, bounds)
    content.move(dx=(bounds.width - content.actual.width) / 2)
    return content


def badge_template(width: int, y: Tuple[int], shape: str, tags: List[str],
                   shape_style: Style, tag_style: Style, pdf: PDF) -> (GroupContent, Tuple[int]):
    height = y[6] + y[0]
    r = y[1] - y[0]
    b = Rect.make(left=0, right=width, top=0, bottom=height)

    shape = shape or 'oval'

    if shape.startswith('oval'):
        path = pdf.beginPath()
        path.arc(0, 0, width, 0 + 2 * r, startAng=180, extent=180)
        path.lineTo(width, height - r)
        path.arcTo(0, height - 2 * r, width, height, startAng=0, extent=180)
        path.close()
        outer_shape = PathContent(path, b, shape_style, PDF.BOTH, pdf)
    elif shape.startswith('hex'):
        path = pdf.beginPath()
        path.moveTo(width / 2, 0)
        path.lineTo(width, 0 + r)
        path.lineTo(width, height - r)
        path.lineTo(width / 2, height)
        path.lineTo(0, height - r)
        path.lineTo(0, 0 + r)
        path.close()
        outer_shape = PathContent(path, b, shape_style, PDF.BOTH, pdf)
    elif shape.startswith('round'):
        outer_shape = RectContent(b, shape_style, PDF.BOTH, pdf, rounded=r // 2)
    else:
        if not shape.startswith('rect'):
            warnings.warn("Unknown shape '%s' for badge layout; using rectangle" % shape)
        outer_shape = RectContent(b, shape_style, PDF.BOTH, pdf)

    # Dividing lines
    path = pdf.beginPath()
    path.moveTo(0, y[2])
    path.lineTo(width, y[2])
    path.moveTo(0, y[4])
    path.lineTo(width, y[4])

    inner_shape = PathContent(path, b, shape_style, PDF.STROKE, pdf)
    group = [outer_shape, inner_shape]

    # tags
    if len(tags) > 0 and tags[0]:
        p = from_text(tags[0], tag_style, pdf)
        r = Rect.make(left=0, right=width, top=y[4] + shape_style.borderWidth, bottom=y[5])
        tag = align_vertically_within(p, r, pdf, posY=-1)
        group.append(tag)
    if len(tags) > 1 and tags[1]:
        p = from_text(tags[1], tag_style, pdf)
        r = Rect.make(left=0, right=width, top=y[1], bottom=y[2] - shape_style.borderWidth)
        tag = align_vertically_within(p, r, pdf, posY=1)
        group.append(tag)

    return GroupContent(group, b)


def badge_vertical_layout(width: int, tags: List[str], style: Style, tag_style: Style, lineWidth: float) -> Tuple[int]:
    # 20% extra for leading on the font sizes
    extreme = max(width / 2, style.size * 1.2 + lineWidth)
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


def add_stamp_values(stamp: GroupContent, y: Tuple[int], run: Run, pdf: PDF):
    contents = stamp.group
    width = stamp.requested.width

    style = run.style()
    styles = [style.clone(align='center'),
              style.clone(size=style.size * 2, align='center'),
              style.clone(size=round(style.size * 1.25), align='center'),
              style.clone(size=round(style.size * 1.25), align='center')]
    row = split_into_paragraphs(run, pdf, styles=styles)

    if len(row) > 0 and row[0]:
        r = Rect.make(left=0, right=width, top=y[2], bottom=y[3])
        p = align_vertically_within(row[0], r, pdf, metrics_adjust=0)
        contents.append(p)
    if len(row) > 1 and row[1]:
        r = Rect.make(left=0, right=width, top=y[3], bottom=y[4])
        p = align_vertically_within(row[1], r, pdf, metrics_adjust=0.75)
        contents.append(p)
    if len(row) > 2 and row[2]:
        r = Rect.make(left=0, right=width, top=y[5], bottom=y[6])
        p = align_vertically_within(row[2], r, pdf)
        contents.append(p)
    if len(row) > 3 and row[3]:
        r = Rect.make(left=0, right=width, top=y[0], bottom=y[1])
        p = align_vertically_within(row[3], r, pdf, metrics_adjust=1)
        contents.append(p)

    return GroupContent(contents, stamp.requested)


def badges_layout(block: Block, bounds: Rect, pdf: PDF) -> Content:
    n = len(block.content)

    shape = block.method.options.get('shape', 'oval')
    tags = block.method.options.get('tags', '').split(',')

    padding = block.spacing.padding

    shape_style = block.method.options.get('shape-style', block.style)
    tag_height = shape_style.size * 2 / 3

    tag_style = shape_style.clone(size=tag_height, align='center')
    width = (bounds.width - padding * (n - 1)) // n

    ypos = badge_vertical_layout(width, tags, block.style, tag_style, shape_style.borderWidth)

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

    content = GroupContent(items, bounds)
    if block.title:
        content.set_table_of_content_info(block.title.as_text())
    return content


def inset_for_content_style(style: Style, spacing: Spacing):
    inset = 0
    if style.has_border():
        inset += style.borderWidth
    if style.has_border() or style.background:
        inset += spacing.margin

    return round(inset)


@lru_cache
def layout_block(block: Block, outer: Rect, pdf: PDF):
    has_title = block.title and block.title_method.name not in {'hidden', 'none'}

    # Reduce the space to account for borders and gaps for background fill
    inset = inset_for_content_style(block.style, block.spacing)
    inner = outer - Margins.balanced(inset)

    items = []

    if has_title:
        # Create title and move the innertop down to avoid it
        title = banner_title_layout(block, outer, inset, pdf)
        inner = Rect(left=inner.left, right=inner.right, bottom=inner.bottom,
                     top=title.actual.bottom + block.spacing.padding)
    else:
        title = None

    content = content_layout(block, inner, pdf)

    # Adjust outer to cover the actual content
    outer = Rect.make(left=outer.left, right=outer.right, top=outer.top,
                      bottom=content.actual.bottom + block.spacing.margin)

    if has_title:
        path = pdf.rect_to_path(outer, block.style)
        clip = ClipContent(path, outer, pdf)
    else:
        clip = None

    if block.style.has_border():
        post = RectContent(outer, block.style, PDF.STROKE, pdf)
    else:
        post = None

    if block.style.background:
        back = RectContent(outer, block.style, PDF.FILL, pdf)
    else:
        back = None

    main = GroupContent([clip, back, title, content], outer)
    if post:
        main =  GroupContent([main, post], outer)

    if block.title:
        main.set_table_of_content_info(block.title.as_text())

    return main


def content_layout(block, inner: Rect, pdf: PDF):
    method = block.method.name
    if method.startswith('therm'):
        content_layout = thermometer_layout
    elif method == 'badge':
        content_layout = badges_layout
    else:
        if method != 'default':
            warnings.warn("Unknown block method '%s'. Using default instead" % method)
        if block.needs_table():
            content_layout = table_layout
        else:
            content_layout = paragraph_layout

    if block.image:
        return image_layout(block, inner, pdf, other_layout=content_layout)
    else:
        return content_layout(block, inner, pdf)


class ImagePlacement(Optimizer):

    def __init__(self, block: Block, bounds: Rect, pdf: PDF, other_layout: Callable, style) -> None:
        super().__init__(2)
        self.style = style
        self.bounds = bounds
        self.block = block
        self.other_layout = other_layout
        self.pdf = pdf

    def make(self, x: Tuple[float]) -> GroupContent:
        outer = self.bounds

        padding = self.block.spacing.padding
        widths = divide_space(x, outer.width - padding, 10 + (padding + 1) // 2)

        LOGGER.fine("Allocating %d to image, %d to other", widths[0], widths[1])

        if self.on_right():
            b_image = outer.make_column(right=outer.right, width=widths[0])
            b_other = outer.make_column(left=outer.left, width=widths[1])
        else:
            b_image = outer.make_column(left=outer.left, width=widths[0])
            b_other = outer.make_column(right=outer.right, width=widths[1])

        other = self.other_layout(self.block, b_other, self.pdf)
        b_image = b_image.resize(height=min(b_image.height, other.requested.height))
        image = self.place_image(b_image)
        return GroupContent([image, other], outer)

    def on_right(self):
        return self.block.image.get('align', 'left') == 'right'

    def score(self, placed: GroupContent) -> float:
        # Want them about the same height if possible
        size_diff = (placed[0].actual.height - placed[1].actual.height) ** 2
        score = size_diff + placed.error_from_breaks(50, 1) + placed.error_from_variance(1) - placed[0].actual.width
        LOGGER.fine("Score: %13f (diff=%1.3f, breaks=%1.3f, var=%1.3f", score, size_diff,
                    placed.error_from_breaks(50, 1), placed.error_from_variance(1))
        return score

    def place_image(self, bounds: Rect):
        im = self.make_image(bounds)
        return ImageContent(im, bounds, self.style, self.pdf)

    def make_image(self, bounds) -> Image:
        im_info = self.block.image
        file = self.pdf.base_dir.joinpath(im_info['uri'])
        width = int(im_info['width']) if 'width' in im_info else None
        height = int(im_info['height']) if 'height' in im_info else None
        if width and height:
            im = Image(file, width=width, height=height, lazy=0)
        else:
            im = Image(file, lazy=0)
            w, h = im.imageWidth, im.imageHeight
            if width:
                im = Image(file, width=width, height=h * width / w, lazy=0)
            elif height:
                im = Image(file, height=height, width=w * height / h, lazy=0)
            elif w > bounds.width:
                # Fit to the column's width
                im = Image(file, width=bounds.width, height=h * bounds.width / w, lazy=0)
        return im


def image_layout(block: Block, bounds: Rect, pdf: PDF, other_layout: Callable) -> Content:
    placer = ImagePlacement(block, bounds, pdf, other_layout, block.style)
    if block.content:
        if 'height' in block.image or 'width' in block.image:
            # It has a fixed size, so we can just use that
            image = placer.place_image(bounds)
            if placer.on_right():
                image.move(dx=bounds.right - image.actual.right)
                obounds = bounds.make_column(left=bounds.left, right=image.actual.left - block.spacing.padding)
            else:
                obounds = bounds.make_column(left=image.actual.right + block.spacing.padding, right=bounds.right)
            other = other_layout(block, obounds, pdf)
            return GroupContent([image, other], bounds)
        else:
            # Must optimize to find best image size
            placed, (score, div) = placer.run()
            LOGGER.debug("Placed image combination %s, score=%1.3f, division=%s", placed, score, div)
            return placed if placed else ErrorContent(bounds, pdf)
    else:
        return placer.place_image(bounds)


def paragraph_layout(block: Block, bounds: Rect, pdf: PDF) -> Optional[Content]:
    if not block.content:
        return None

    results = []
    style = block.style

    padding = block.spacing.padding

    # Move up by the excess leading
    b = bounds.move(dy=-(style.size * 0.2))
    for item in block.content:
        p = make_paragraph(item, pdf)
        placed = ParagraphContent(p, b, pdf)
        results.append(placed)
        b = Rect.make(top=placed.actual.bottom + padding, left=b.left, right=b.right, bottom=b.bottom)
    if not results:
        return None
    elif len(results) == 1:
        return results[0]
    else:
        return GroupContent(results, bounds)


def banner_title_layout(block: Block, bounds: Rect, inset: int, pdf: PDF) -> Content:
    # Banner needs a minimum padding around it
    pad = block.spacing.padding
    mgn = block.spacing.margin
    m = Margins(left=max(inset, pad), right=max(inset, pad),
                top=max(inset, mgn), bottom=max(inset, mgn))
    bounds -= m

    style = block.title_style
    placed = []
    plaque = bounds.resize(height=round(style.size) + block.spacing.padding)

    title_mod = Run(block.title.items).with_style(style)
    title = one_line_flowable(title_mod, plaque, block.spacing.padding, pdf)
    extraLines = title.ok_breaks + title.bad_breaks
    if extraLines:
        plaque = plaque.resize(height=plaque.height + extraLines * (style.size * 1.2))

    if style.background:
        r = plaque + Margins(left=20, top=20, right=20, bottom=0)
        placed.append(RectContent(r, style, PDF.FILL, pdf))

    # Move the title up a little to account for the descender and lien spacing
    dy = pdf.descender(style) + style.size * 0.1
    title.move(dy=-dy)
    placed.append(title)

    return GroupContent(placed, bounds)


def place_within(p: Union[Paragraph, Table], r: Rect, pdf: PDF, posX=0, posY=0, descent_adjust=0.3) -> Content:
    """
        Create a placed paragraph within a set of bounds
        :param Paragraph p: place this
        :param Rect r:  within this
        :param int posX: <0 means to the left, 0 centered, > 0 to the right
        :param int posY:  <0 means at the top, 0 centered, > 0 at the right
    """

    if isinstance(p, Paragraph):
        pfc = ParagraphContent(p, r, pdf)
    else:
        pfc = TableContent(p, r, pdf)
    a = pfc.actual
    if posX < 0:
        dx = r.left - a.left
    elif posX > 0:
        dx = r.right - a.right
    else:
        dx = r.center.x - a.center.x

    if posY < 0:
        dy = r.top - a.top
    elif posY > 0:
        dy = r.bottom - a.bottom
    else:
        dy = r.center.y - a.center.y

    pfc.move(dx=dx, dy=dy + descent_of(p) * descent_adjust)
    return pfc


def align_vertically_within(p: Paragraph, r: Rect, pdf: PDF, posY=0, metrics_adjust=0) -> ParagraphContent:
    """
        Create a placed paragraph within a set of bounds
        :param Paragraph p: place this
        :param Rect r:  within this
        :param int posY:  <0 means at the top, 0 centered, > 0 at the right
    """

    pfc = ParagraphContent(p, r, pdf)
    a = pfc.actual
    if posY < 0:
        dy = r.top - a.top - leading_extra(p) * metrics_adjust
    elif posY > 0:
        dy = r.bottom - a.bottom + descent_of(p) * metrics_adjust
    else:
        dy = r.center.y - a.center.y + descent_of(p) * metrics_adjust

    pfc.move(dy=dy)
    return pfc


def descent_of(p):
    if hasattr(p, 'blPara'):
        if hasattr(p.blPara, 'descent'):
            return p.blPara.descent
        else:
            return min(d.descent for d in p.blPara.lines)
    return 0


def leading_extra(p: Flowable):
    if hasattr(p, 'style'):
        return p.style.leading - p.style.fontSize
    else:
        return 0


def from_text(txt, style: Style, pdf: PDF) -> Paragraph:
    run = Run([Element(ElementType.TEXT, txt, style)])
    return make_paragraph(run, pdf)


def split_into_paragraphs(run, pdf, styles: List[Style] = None) -> List[Paragraph]:
    items = run.items
    row = []
    start = 0
    spacer_idx = 0
    for i, e in enumerate(items):
        if e.which in {ElementType.SPACER, ElementType.DIVIDER}:
            _add_to_row(row, items[start:i], pdf, styles)
            if e.which == ElementType.SPACER:
                spacer_idx += 1
            start = i + 1
    _add_to_row(row, items[start:], pdf, styles)
    return row


def _add_to_row(row, elements: Sequence[Element], pdf: PDF, styles):
    added = len(row)
    if styles and added < len(styles) and styles[added] is not None:
        elements = [e.with_style(e.style.clone_using(styles[added])) for e in elements]
    run = Run(elements)
    row.append(make_paragraph(run, pdf))


def make_paragraph(run: Run, pdf: PDF, align=None, size_factor=None) -> Optional[Paragraph]:
    if not len(run.items):
        return None

    style = pdf.paragraph_style_for(run)
    if align:
        style = style.clone(align=align)
    if size_factor:
        style = style.clone(size=style.size * size_factor)

    return Paragraph(run, style, pdf)


@functools.lru_cache(maxsize=1024)
def make_block_layout(target: Block, width: int, pdf: PDF) -> Content:
    rect = Rect.make(left=0, top=0, width=width, height=1000)
    return layout_block(target, rect, pdf)


def place_block(bounds: Rect, block: Block, pdf: PDF) -> Content:
    base = copy(make_block_layout(block, bounds.width, pdf))
    base.move(dx=bounds.left - base.requested.left, dy=bounds.top - base.requested.top)
    return base
