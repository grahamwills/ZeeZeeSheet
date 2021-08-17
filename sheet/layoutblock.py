""" Defines layout methods """

from __future__ import annotations, annotations

import warnings
from typing import Callable, Optional, Tuple

from reportlab.platypus import Image

import para
from placed import ErrorContent, PlacedContent, PlacedFlowableContent, PlacedGroupContent, PlacedRectContent
from sheet import common
from sheet.common import Margins, Rect
from sheet.model import Block, Run
from sheet.optimize import Optimizer, divide_space
from sheet.pdf import PDF
from table import badges_layout, key_values_layout, one_line_flowable, table_layout

LOGGER = common.configured_logger(__name__)


def layout_block(block: Block, bounds: Rect, pdf: PDF):
    pre, insets = _pre_content_layout(block, bounds, pdf)

    content = _content_layout(block, bounds - insets, pdf)

    inner = Rect(left=bounds.left, right=bounds.right, top=bounds.top,
                 bottom=content.actual.bottom + insets.bottom)

    back, post = _post_content_layout(block, inner, pdf)

    items = [p for p in [back, pre, content, post] if p]
    return PlacedGroupContent(items, bounds)


def _pre_content_layout(block, bounds, pdf) -> (PlacedContent, Margins):
    title = block.title_method
    title_style = title.options.get('style', 'default')
    if title.command in {'hidden', 'none'}:
        return banner_pre_layout(block, bounds, title_style, pdf, show_title=False)
    elif title.command == 'banner':
        return banner_pre_layout(block, bounds, title_style, pdf, show_title=True)
    else:
        raise ValueError("unknown title method '%s'" % title.command)


def _post_content_layout(block: Block, inner, pdf):
    title = block.title_method
    title_style = title.options.get('style', 'default')
    style = pdf.style(block.base_style())
    if style and style.background:
        back = PlacedRectContent(inner, style, pdf, fill=True, stroke=False)
    else:
        back = None
    post = outline_post_layout(inner, title_style, pdf)
    return back, post


def _content_layout(block, inner, pdf):
    method = block.block_method.command
    if method == 'key-values':
        content_layout = key_values_layout
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
        return content_layout(block, inner, pdf, **block.block_method.options)


class ImagePlacement(Optimizer):

    def __init__(self, block: Block, bounds: Rect, pdf: PDF, other_layout: Callable) -> None:
        super().__init__(2)
        self.bounds = bounds
        self.block = block
        self.other_layout = other_layout
        self.pdf = pdf

    def make(self, x: Tuple[float]) -> PlacedGroupContent:
        outer = self.bounds

        padding = self.block.padding
        widths = divide_space(x, outer.width - padding, 10 + (padding + 1) // 2)

        LOGGER.fine("Allocating %d to image, %d to other", widths[0], widths[1])

        if self.on_right():
            b_image = outer.modify_horizontal(right=outer.right, width=widths[0])
            b_other = outer.modify_horizontal(left=outer.left, width=widths[1])
        else:
            b_image = outer.modify_horizontal(left=outer.left, width=widths[0])
            b_other = outer.modify_horizontal(right=outer.right, width=widths[1])

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
        return PlacedFlowableContent(im, bounds, self.pdf)

    def make_image(self, bounds) -> Image:
        im_info = self.block.image
        file = self.pdf.working_dir.joinpath(im_info['uri'])
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
    placer = ImagePlacement(block, bounds, pdf, other_layout)
    if block.content:
        if 'height' in block.image or 'width' in block.image:
            # It has a fixed size, so we can just use that
            image = placer.place_image(bounds)
            if placer.on_right():
                image.move(dx=bounds.right - image.actual.right)
                obounds = bounds.modify_horizontal(left=bounds.left, right=image.actual.left - block.padding)
            else:
                obounds = bounds.modify_horizontal(left=image.actual.right + block.padding, right=bounds.right)
            other = other_layout(block, obounds, pdf)
            return PlacedGroupContent([image, other], bounds)
        else:
            # Must optimize to find best image size
            placed, (score, div) = placer.run()
            LOGGER.debug("Placed image combination %s, score=%1.3f, division=%s", placed, score, div)
            return placed if placed else ErrorContent(bounds, pdf)
    else:
        return placer.place_image(bounds)


def paragraph_layout(block: Block, bounds: Rect, pdf: PDF, padding: int=None) -> Optional[PlacedContent]:
    if not block.content:
        return None

    results = []
    style = pdf.style(block.base_style())

    padding = int(padding) if padding is not None else block.padding

    # Move up by the excess leading
    b = bounds.move(dy=-(style.size * 0.2))
    for item in block.content:
        p = para.make_paragraph(item, pdf)
        placed = PlacedFlowableContent(p, b, pdf)
        results.append(placed)
        b = Rect(top=placed.actual.bottom + padding, left=b.left, right=b.right, bottom=b.bottom)
    if not results:
        return None
    elif len(results) == 1:
        return results[0]
    else:
        return PlacedGroupContent(results, bounds)


def banner_pre_layout(block: Block, bounds: Rect, style_name: str, pdf: PDF, show_title=True) -> (
        PlacedContent, Margins):
    style = pdf.style(style_name)
    if style.has_border():
        line_width = int(style.borderWidth)
    else:
        line_width = 0

    if style.has_border() or style.background:
        margin = block.margin
    else:
        margin = 0

    inset = line_width + margin
    margins = Margins.all_equal(inset)

    plaque_height = round(style.size + margin * 2)

    if show_title and block.title:
        placed = []
        plaque = bounds.resize(height=plaque_height)

        title_bounds = plaque - margins
        title_mod = Run([e.replace_style(style_name) for e in block.title.items])
        title = one_line_flowable(title_mod, title_bounds, margin, pdf)
        extraLines = title.ok_breaks + title.bad_breaks
        if extraLines:
            plaque = plaque.resize(height=plaque.height + extraLines*pdf.style(style_name).size)

        if style.background:
            placed.append(PlacedRectContent(plaque, style, pdf, fill=True, stroke=False))

        # Move the title up a little to account for the descender
        title.move(dy=-pdf.descender(style))
        placed.append(title)

        margins = Margins(left=inset, right=inset, top=inset + plaque.height, bottom=inset)

        group = PlacedGroupContent(placed, bounds)
        group.margins = margins
        return group, margins
    else:
        return None, margins


def outline_post_layout(bounds: Rect, style_name: str, pdf: PDF) -> Optional[PlacedContent]:
    style = pdf.style(style_name)
    if style.has_border():
        return PlacedRectContent(bounds, style, pdf, fill=False, stroke=True)
    else:
        return None


def no_post_layout(*_) -> Optional[PlacedContent]:
    return None
