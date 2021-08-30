""" Defines layout methods """

from __future__ import annotations, annotations

import warnings
from functools import lru_cache
from typing import Callable, Optional, Tuple

from reportlab.platypus import Image

import layoutparagraph
from placed import ErrorContent, PlacedClipContent, PlacedContent, PlacedGroupContent, PlacedImageContent, \
    PlacedParagraphContent, PlacedRectContent
from sheet import common
from sheet.common import Margins, Rect
from sheet.model import Block, Run, Spacing
from sheet.optimize import Optimizer, divide_space
from sheet.pdf import PDF
from style import Style
from table import badges_layout, one_line_flowable, table_layout, thermometer_layout

LOGGER = common.configured_logger(__name__)


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

    post, clip = outline_post_layout(outer, block.style, pdf)

    if not has_title:
        clip = None

    if block.style.background:
        back = PlacedRectContent(outer, block.style, PDF.FILL, pdf)
    else:
        back = None

    main = PlacedGroupContent([clip, back, title, content], outer)
    if post:
        return PlacedGroupContent([main, post], outer)
    else:
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

    def make(self, x: Tuple[float]) -> PlacedGroupContent:
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
        return PlacedGroupContent([image, other], outer)

    def on_right(self):
        return self.block.image.get('align', 'left') == 'right'

    def score(self, placed: PlacedGroupContent) -> float:
        # Want them about the same height if possible
        size_diff = (placed[0].actual.height - placed[1].actual.height) ** 2
        score = size_diff + placed.error_from_breaks(50, 1) + placed.error_from_variance(1) - placed[0].actual.width
        LOGGER.fine("Score: %13f (diff=%1.3f, breaks=%1.3f, var=%1.3f", score, size_diff,
                    placed.error_from_breaks(50, 1), placed.error_from_variance(1))
        return score

    def place_image(self, bounds: Rect):
        im = self.make_image(bounds)
        return PlacedImageContent(im, bounds, self.style, self.pdf)

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


def image_layout(block: Block, bounds: Rect, pdf: PDF, other_layout: Callable) -> PlacedContent:
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
            return PlacedGroupContent([image, other], bounds)
        else:
            # Must optimize to find best image size
            placed, (score, div) = placer.run()
            LOGGER.debug("Placed image combination %s, score=%1.3f, division=%s", placed, score, div)
            return placed if placed else ErrorContent(bounds, pdf)
    else:
        return placer.place_image(bounds)


def paragraph_layout(block: Block, bounds: Rect, pdf: PDF) -> Optional[PlacedContent]:
    if not block.content:
        return None

    results = []
    style = block.style

    padding = block.spacing.padding

    # Move up by the excess leading
    b = bounds.move(dy=-(style.size * 0.2))
    for item in block.content:
        p = layoutparagraph.make_paragraph(item, pdf)
        placed = PlacedParagraphContent(p, b, pdf)
        results.append(placed)
        b = Rect.make(top=placed.actual.bottom + padding, left=b.left, right=b.right, bottom=b.bottom)
    if not results:
        return None
    elif len(results) == 1:
        return results[0]
    else:
        return PlacedGroupContent(results, bounds)


def banner_title_layout(block: Block, bounds: Rect, inset: int, pdf: PDF) -> PlacedContent:
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
        plaque = plaque.resize(height=plaque.height + extraLines * style.size)

    if style.background:
        r = plaque + Margins(left=20, top=20, right=20, bottom=0)
        placed.append(PlacedRectContent(r, style, PDF.FILL, pdf))

    # Move the title up a little to account for the descender
    title.move(dy=-pdf.descender(style))
    placed.append(title)

    return PlacedGroupContent(placed, bounds)


def outline_post_layout(bounds: Rect, style: Style, pdf: PDF) -> (Optional[PlacedContent], PlacedClipContent):
    path = pdf.rect_to_path(bounds, style)
    clip = PlacedClipContent(path, bounds, pdf)
    if style.has_border():
        return PlacedRectContent(bounds, style, PDF.STROKE, pdf), clip
    else:
        return None, clip


def no_post_layout(*_) -> Optional[PlacedContent]:
    return None
