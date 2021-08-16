""" Defines layout methods """

from __future__ import annotations, annotations

from pathlib import Path
from typing import Callable, Optional, Tuple

from reportlab.platypus import Image

from sheet.optimize import Optimizer, divide_space
from sheet import common
from sheet.common import Margins, Rect
from table import key_values_layout, one_line_flowable, table_layout
from sheet.model import Block, Run
from sheet.pdf import PDF
from placed import PlacedContent, PlacedFlowableContent, PlacedGroupContent, \
    PlacedRectContent, ErrorContent

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


def _post_content_layout(block, inner, pdf):
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
    if block.block_method.command == 'key-values':
        content_layout = key_values_layout
    elif block.needs_table():
        content_layout = table_layout
    else:
        content_layout = paragraph_layout

    if block.image:
        return image_layout(block, inner, pdf, other_layout=content_layout)
    else:
        return content_layout(block, inner, pdf)


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
        file = Path(__file__).parent.parent.joinpath(im_info['uri'])
        width = int(im_info['width']) if 'width' in im_info else None
        height = int(im_info['height']) if 'height' in im_info else None
        if width and height:
            im = Image(file, width=width, height=height)
        else:
            im = Image(file)
            w, h = im.imageWidth, im.imageHeight
            if width:
                im = Image(file, width=width, height=h * width / w)
            elif height:
                im = Image(file, height=height, width=w * height / h)
            elif w > bounds.width:
                # Fit to the column's width
                im = Image(file, width=bounds.width, height=h * bounds.width / w)
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


def paragraph_layout(block: Block, bounds: Rect, pdf: PDF) -> Optional[PlacedContent]:
    if not block.content:
        return None

    results = []
    style = pdf.style(block.base_style())

    # Move up by the excess leading
    b = bounds.move(dy=-(style.size * 0.2))
    for item in block.content:
        p = pdf.make_paragraph(item)
        placed = PlacedFlowableContent(p, b, pdf)
        results.append(placed)
        b = Rect(top=placed.actual.bottom + block.padding,
                 left=b.left, right=b.right, bottom=b.bottom)
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

    if show_title and block.title:
        title_mod = Run([e.replace_style(style_name) for e in block.title.items])
        title_bounds = bounds - margins
        title = one_line_flowable(title_mod, title_bounds, margin, pdf)

        # We remove the extra leading the paragraph gave us at the bottom (0.2 * font-size)
        plaque_height = title.actual.height + 2 * margin - style.size * 0.2

        # Move the title up a little to account for the descender
        title.move(dy=-pdf.descender(style))

        placed = []
        if style.background:
            plaque = (bounds - Margins.all_equal(line_width)).resize(height=plaque_height)
            placed.append(PlacedRectContent(plaque, style, pdf, fill=True, stroke=False))

        placed.append(title)

        margins = Margins(left=inset, right=inset, top=inset + plaque_height, bottom=inset)

        group = PlacedGroupContent(placed, bounds)
        group.margins = margins
        return (group, margins)
    else:
        return (None, margins)


def outline_post_layout(bounds: Rect, style_name: str, pdf: PDF) -> Optional[PlacedContent]:
    style = pdf.style(style_name)
    if style.has_border():
        return PlacedRectContent(bounds, style, pdf, fill=False, stroke=True)
    else:
        return None


def no_post_layout(*_) -> Optional[PlacedContent]:
    return None
