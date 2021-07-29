""" Defines layout methods """
from __future__ import annotations

import functools
from pathlib import Path
from typing import Callable, NamedTuple, Optional

import PIL
from reportlab.platypus import Image

import common
from common import Margins, Rect
from layout.table import as_one_line, table_layout
from model import Block, Run
from pdf import PDF
from render import PlacedContent, PlacedFlowableContent, PlacedGroupContent, PlacedRectContent


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

        if self.block.needs_table():
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
                     bottom=content.bounds.bottom + pre.insets.bottom)

        style = self.pdf.style(self.block.base_style())
        if style and style.background:
            back = PlacedRectContent(inner, style, fill=True, stroke=False)
        else:
            back = None
        post = self.post_layout(self.block, inner, self.title_style, self.pdf)
        items = [p for p in [back, pre.placed, content, post] if p]
        return PlacedGroupContent(items)


def image_layout(block: Block, bounds: Rect, pdf: PDF, other_layout: Callable) -> PlacedContent:
    file = Path(__file__).parent.parent.parent.joinpath(block.image['uri'])
    width = int(block.image['width']) if 'width' in block.image else None
    height = int(block.image['height']) if 'height' in block.image else None

    on_right = block.image.get('align', 'left').lower() == 'right'

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

    w, h = im.wrapOn(pdf, bounds.width, bounds.height)
    image = PlacedFlowableContent(im, bounds.resize(width=w, height=h))

    if on_right:
        ob = Rect(left=bounds.left, right=bounds.right - w - block.padding, top=bounds.top, bottom=bounds.bottom)
        image.bounds = image.bounds.move(dx=bounds.width - w)
    else:
        ob = Rect(left=bounds.left + w + block.padding, right=bounds.right, top=bounds.top, bottom=bounds.bottom)
    other = other_layout(block, ob, pdf)

    return PlacedGroupContent([image, other])


def paragraph_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    if not block.content:
        return PlacedContent(bounds.resize(height=0))

    results = []
    style = pdf.style(block.base_style())

    # Move up by the excess leading
    b = bounds.move(dy=-(style.size * 0.2))
    for item in block.content:
        p = pdf.make_paragraph(item)
        w, h = p.wrapOn(pdf, b.width, b.height)
        placed = PlacedFlowableContent(p, b.resize(width=w, height=h))
        results.append(placed)
        b = Rect(top=placed.bounds.bottom + block.padding,
                 left=b.left, right=b.right, bottom=b.bottom)
    if not results:
        return PlacedContent(bounds.resize(height=0))
    elif len(results) == 1:
        return results[0]
    else:
        return PlacedGroupContent(results)


def banner_pre_layout(block: Block, bounds: Rect, style_name: str, pdf: PDF, show_title=True) -> BorderDetails:
    style = pdf.style(style_name)
    if style.has_border():
        line_width = int(style.borderWidth)
    else:
        line_width = 0

    if style.has_border():
        padding = block.padding
    else:
        padding = 0

    inset = line_width + padding
    margins = Margins.all_equal(inset)

    if show_title and block.title:
        title_mod = Run([e.replace_style(style_name) for e in block.title.items])
        title_bounds = bounds - margins
        paragraph, w, height = as_one_line(title_mod, pdf, title_bounds.width)

        # We remove the extra leading the paragraph gave us at the bottom (0.2 * font-size)
        plaque_height = height + 2 * padding - style.size * 0.2
        title_bounds = title_bounds.resize(height=height)

        placed = []
        if style.background:
            plaque = (bounds - Margins.all_equal(line_width)).resize(height=plaque_height)
            placed.append(PlacedRectContent(plaque, style, fill=True, stroke=False))

        descent = pdf.descender(style)
        placed.append(PlacedFlowableContent(paragraph, title_bounds.move(dy=-descent)))

        margins = Margins(left=inset, right=inset, top=inset + plaque_height, bottom=inset)

        group = PlacedGroupContent(placed)
        group.margins = margins
        return BorderDetails(group, margins)
    else:
        return BorderDetails(None, margins)


def outline_post_layout(block: Block, bounds: Rect, style_name: str, context: PDF) -> Optional[PlacedContent]:
    style = context.style(style_name)
    if style.has_border():
        return PlacedRectContent(bounds, style, fill=False, stroke=True)
    else:
        return None


def no_post_layout(*_) -> Optional[PlacedContent]:
    return None
