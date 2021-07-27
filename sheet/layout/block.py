""" Defines layout methods """
from __future__ import annotations

from typing import Callable, NamedTuple, Optional

from reportlab.platypus import Table, TableStyle

from common import Directive, Margins, Rect
from model import Block, Run
from pdf import PDF, as_one_line
from render import PlacedContent, empty_content, flowable_content, grouped_content, rect_content


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
        self.set_methods(block.renderers[0], block.renderers[1])

    def set_methods(self, title_method: str, content_method: str):
        title = Directive(title_method)
        self.title_style = title.get('style', 'default')
        if title.name == 'none':
            self.pre_layout = no_pre_layout
            self.post_layout = no_post_layout
        elif title.name == 'banner':
            self.pre_layout = banner_pre_layout
            self.post_layout = banner_post_layout
        else:
            raise ValueError("unknown title method '%s'" % title_method)

        # Just the one method so far
        if self.block.needs_table():
            self.content_layout = table_layout
        else:
            self.content_layout = paragraph_layout

    def layout(self):
        bounds = self.bounds
        pre = self.pre_layout(self.block, bounds, self.title_style, self.pdf)
        inner = bounds - pre.insets
        content = self.content_layout(self.block, inner, self.pdf)
        inner = Rect(left=bounds.left, right=bounds.right, top=bounds.top,
                     bottom=content.bounds.bottom + pre.insets.bottom)
        post = self.post_layout(self.block, inner, self.title_style, self.pdf)
        items = [p for p in [pre.placed, content, post] if p]
        return grouped_content(items)


def paragraph_layout(block: Block, bounds: Rect, context: PDF) -> PlacedContent:
    results = []
    b = bounds
    for item in block.content:
        p = context.make_paragraph(item)
        w, h = p.wrapOn(context, b.width, b.height)
        placed = flowable_content(p, b.resize(width=w, height=h))
        results.append(placed)
        b = Rect(top=placed.bounds.bottom + block.padding,
                 left=b.left, right=b.right, bottom=b.bottom)
    if not results:
        return empty_content(bounds.resize(height=0))
    elif len(results) == 1:
        return results[0]
    else:
        return grouped_content(results)


def table_layout(block: Block, bounds: Rect, pdf: PDF) -> PlacedContent:
    cells = []
    for run in block.content:
        row = []
        for r in run.divide_by_spacers():
            if r.valid():
                row.append(pdf.make_paragraph(r))
            else:
                row.append(' ')
        cells.append(row)

    commands = [
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]

    # Spacers divide up the run
    table = Table(cells)

    table.setStyle(TableStyle(commands))
    w, h = table.wrapOn(pdf, bounds.width, 1000)
    return flowable_content(table, bounds.resize(width=w, height=h))


def banner_pre_layout(block: Block, bounds: Rect, style_name: str, pdf: PDF) -> BorderDetails:
    style = pdf.style(style_name)
    if style.has_border():
        line_width = int(style.borderWidth)
    else:
        line_width = 0

    inset = line_width + block.padding
    margins = Margins.all_equal(inset)

    placed = []

    if block.title:
        title_mod = Run([e.replace_style(style_name) for e in block.title.items])
        title_bounds = bounds - margins
        paragraph, w, height = as_one_line(title_mod, pdf, title_bounds.width)
        plaque_height = height + 2 * block.padding
        title_bounds = title_bounds.resize(height=height)

        if style.background:
            plaque = (bounds - Margins.all_equal(line_width)).resize(height=plaque_height)
            placed.append(rect_content(plaque, style, fill=1, stroke=0))

        descent = pdf.descender(style)
        placed.append(flowable_content(paragraph, title_bounds.move(dy=-descent)))

        margins = Margins(left=inset, right=inset, top=inset + plaque_height, bottom=inset)

    group = grouped_content(placed)
    group.margins = margins
    return BorderDetails(group, margins)


def banner_post_layout(block: Block, bounds: Rect, style_name: str, context: PDF) -> Optional[PlacedContent]:
    style = context.style(style_name)
    if style.has_border():
        return rect_content(bounds, style, fill=0, stroke=1)
    else:
        return None


def no_pre_layout(block: Block, bounds: Rect, style_name: str, context: PDF) -> BorderDetails:
    return BorderDetails(None, Margins.all_equal(0))


def no_post_layout(block: Block, bounds: Rect, style_name: str, context: PDF) -> Optional[PlacedContent]:
    return None
