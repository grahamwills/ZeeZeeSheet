""" Defines layout methods """

from __future__ import annotations, annotations

import functools
from pathlib import Path
from typing import Callable, Optional

from reportlab.platypus import Image

from optimize import Optimizer
from sheet import common
from sheet.common import Margins, Rect
from sheet.layout.table import key_values_layout, one_line_flowable, table_layout
from sheet.model import Block, Run
from sheet.pdf import PDF
from sheet.placement.placed import PlacedContent, PlacedFlowableContent, PlacedGroupContent, \
    PlacedRectContent

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


class ImageOptimizer(Optimizer):

    def __init__(self, block: Block, bounds: Rect, pdf: PDF, other_layout: Callable) -> None:
        super().__init__(1)
        self.bounds = bounds
        self.block = block
        self.other_layout = other_layout
        self.pdf = pdf

    def make(self, x: [float]) -> PlacedGroupContent:
        outer = self.bounds
        D = outer.width * x[0]

        b_image = Rect(top=outer.top, bottom=outer.bottom, left=outer.left, right=outer.left + D)
        b_other = Rect(top=outer.top, bottom=outer.bottom, left=outer.left + D, right=outer.right)

        if self.block.image.get('align', 'left') == 'right':
            b_image, b_other = b_other, b_image

        other = self.other_layout(self.block, b_other, self.pdf)
        b_image = b_image.resize(height=min(b_image.height, other.requested.height))
        image = self.place_image(b_image)
        return PlacedGroupContent([image, other], outer)

    def score(self, placed: PlacedGroupContent) -> float:
        # Want them about the same height if possible
        return abs(placed[0].actual.height - placed[1].actual.height) + placed.error_from_breaks() * 40

    def place_image(self, b: Rect):
        im_info = self.block.image
        file = Path(__file__).parent.parent.parent.joinpath(im_info['uri'])
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
            elif w > b.width:
                # Fit to the column's width
                im = Image(file, width=b.width, height=h * b.width / w)

        w, h = im.wrapOn(self.pdf, b.width, b.height)
        return PlacedFlowableContent(im, b.resize(width=w, height=h), self.pdf)


def image_layout(block: Block, bounds: Rect, pdf: PDF, other_layout: Callable) -> PlacedContent:
    optimizer = ImageOptimizer(block, bounds, pdf, other_layout)
    if block.content:
        placed, _ = optimizer.run()
        return placed
    else:
        return optimizer.place_image(bounds)


def paragraph_layout(block: Block, bounds: Rect, pdf: PDF) -> Optional[PlacedContent]:
    if not block.content:
        return None

    results = []
    style = pdf.style(block.base_style())

    # Move up by the excess leading
    b = bounds.move(dy=-(style.size * 0.2))
    for item in block.content:
        p = pdf.make_paragraph(item)
        w, h = p.wrapOn(pdf, b.width, b.height)
        placed = PlacedFlowableContent(p, b.resize(width=w, height=h), pdf)
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
