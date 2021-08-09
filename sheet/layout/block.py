""" Defines layout methods """
from __future__ import annotations

import functools
from pathlib import Path
from typing import Callable, NamedTuple, Optional

from reportlab.platypus import Image

from sheet import common
from sheet.common import Margins, Rect
from sheet.layout.optimizer import OptParams, OptimizeProblem
from sheet.layout.table import as_one_line, key_values_layout, table_layout
from sheet.model import Block, Run
from sheet.pdf import PDF
from sheet.placement.placed import PlacedContent, PlacedFlowableContent, PlacedGroupContent, PlacedRectContent, EmptyPlacedContent

LOGGER = common.configured_logger(__name__)

class BorderDetails(NamedTuple):
    placed: Optional[PlacedContent]
    insets: Margins


# Creates insets for the next step and placed items to be drawn
BorderPreLayout = Callable[[Block, Rect, str, PDF], BorderDetails]

# Creates placed items to be drawn as the final border
BorderPostLayout = Callable[[Block, Rect, str, PDF], Optional[PlacedContent]]

# Creates placed items to be drawn in the main section
ContentLayout = Callable[[Block, Rect, PDF], Optional[PlacedContent]]



class BlockLayout:
    block: Block
    bounds: Rect
    title_style: str
    pdf: PDF

    pre_layout: BorderPreLayout
    content_layout: ContentLayout
    post_layout: BorderPostLayout

    def __init__(self, block: Block, bounds: Rect, context: PDF):
        self.pdf = context
        self.bounds = bounds
        self.block = block
        self.set_methods(block.title_method)

    def set_methods(self, title: common.Command):
        self.title_style = title.options.get('style', 'default')
        if title.command in {'hidden', 'none'}:
            self.pre_layout = functools.partial(banner_pre_layout, show_title=False)
            self.post_layout = outline_post_layout
        elif title.command == 'banner':
            self.pre_layout = functools.partial(banner_pre_layout, show_title=True)
            self.post_layout = outline_post_layout
        else:
            raise ValueError("unknown title method '%s'" % title.command)

        if self.block.block_method.command == 'key-values':
            self.content_layout = key_values_layout
        elif self.block.needs_table():
            self.content_layout = table_layout
        else:
            self.content_layout = paragraph_layout

        if self.block.image:
            self.content_layout = functools.partial(image_layout, other_layout=self.content_layout)

    def layout(self):
        bounds = self.bounds
        pre = self.pre_layout(self.block, bounds, self.title_style, self.pdf)
        inner = bounds - pre.insets
        content = self.content_layout(self.block, inner, self.pdf)
        inner = Rect(left=bounds.left, right=bounds.right, top=bounds.top,
                     bottom=content.actual.bottom + pre.insets.bottom)

        style = self.pdf.style(self.block.base_style())
        if style and style.background:
            back = PlacedRectContent(inner, style, self.pdf, fill=True, stroke=False)
        else:
            back = None
        post = self.post_layout(self.block, inner, self.title_style, self.pdf)
        items = [p for p in [back, pre.placed, content, post] if p]
        return PlacedGroupContent(items, bounds, self.pdf)

class ImageOptimizer(OptimizeProblem):

    def __init__(self, block: Block, bounds: Rect, pdf: PDF, other_layout: Callable) -> None:
        super().__init__()
        self.bounds = bounds
        self.block = block
        self.other_layout = other_layout
        self.pdf = pdf

    def place_two(self, D: int):
        outer = self.bounds

        b_image = Rect(top=outer.top, bottom=outer.bottom, left=outer.left, right=outer.left + D)
        b_other = Rect(top=outer.top, bottom=outer.bottom, left=outer.left + D, right=outer.right)

        if self.block.image.get('align', 'left') == 'right':
            b_image, b_other = b_other, b_image

        other = self.other_layout(self.block, b_other, self.pdf)
        b_image = b_image.resize(height =min(b_image.height, other.requested.height))
        image = self.place_image(b_image)
        return PlacedGroupContent([image, other], outer, self.pdf)

    def place_image(self, b:Rect):
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

    def score(self, x1: OptParams, x2: OptParams) -> float:
        placed = self.place_two(x1.value[0])
        return placed.actual.height

    def stage2parameters(self, stage1params: OptParams) -> Optional[OptParams]:
        return OptParams((0,),0,1)

    def validity_error(self, params: OptParams) -> float:
        if params.value[0] < 10 or params.value[0] > self.bounds.width -10:
            return 10
        else:
            return 0


def image_layout(block: Block, bounds: Rect, pdf: PDF, other_layout: Callable) -> PlacedContent:
    optimizer = ImageOptimizer(block, bounds, pdf, other_layout)
    if not other_layout:
        return optimizer.place_image(bounds)
    else:
        init_params = OptParams((bounds.width/3,), 10, bounds.width-10)
        _1, p, _2 = optimizer.run(init_params)
        return optimizer.place_two(p.value[0])


def paragraph_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    if not block.content:
        return EmptyPlacedContent(bounds.resize(height=0), pdf)

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
        return EmptyPlacedContent(bounds.resize(height=0), pdf)
    elif len(results) == 1:
        return results[0]
    else:
        return PlacedGroupContent(results, bounds, pdf)


def banner_pre_layout(block: Block, bounds: Rect, style_name: str, pdf: PDF, show_title=True) -> BorderDetails:
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
        paragraph, w, height = as_one_line(title_mod, pdf, title_bounds.width, margin)

        # We remove the extra leading the paragraph gave us at the bottom (0.2 * font-size)
        plaque_height = height + 2 * margin - style.size * 0.2
        title_bounds = title_bounds.resize(height=height)

        placed = []
        if style.background:
            plaque = (bounds - Margins.all_equal(line_width)).resize(height=plaque_height)
            placed.append(PlacedRectContent(plaque, style, pdf, fill=True, stroke=False))

        descent = pdf.descender(style)
        placed.append(PlacedFlowableContent(paragraph, title_bounds.move(dy=-descent), pdf))

        margins = Margins(left=inset, right=inset, top=inset + plaque_height, bottom=inset)

        group = PlacedGroupContent(placed, bounds, pdf)
        group.margins = margins
        return BorderDetails(group, margins)
    else:
        return BorderDetails(None, margins)


def outline_post_layout(block: Block, bounds: Rect, style_name: str, pdf: PDF) -> Optional[PlacedContent]:
    style = pdf.style(style_name)
    if style.has_border():
        return PlacedRectContent(bounds, style, pdf, fill=False, stroke=True)
    else:
        return None


def no_post_layout(*_) -> Optional[PlacedContent]:
    return None
