""" Defines layout methods """
from __future__ import annotations
from typing import Callable, NamedTuple, Optional

from reportlab.platypus import Paragraph, Table, TableStyle

from common import Directive, Margins, Rect
from model import Block, Run
from pdf import PDF
from render import EmptyPlacedContent, PlacedContent, PlacedGroup, PlacedParagraph, PlacedRect, as_one_line, \
    descender, \
    run_to_html


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
    context: PDF

    pre_layout: BorderPreLayout
    content_layout: ContentLayout
    post_layout: BorderPostLayout

    def __init__(self, block: Block, bounds: Rect, context: PDF):
        self.context = context
        self.bounds = bounds
        self.block = block

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
        pre = self.pre_layout(self.block, bounds, self.title_style, self.context)
        inner = bounds - pre.insets
        content = self.content_layout(self.block, inner, self.context)
        inner = Rect(left=bounds.left, right=bounds.right, top=bounds.top,
                     bottom=content.bounds.bottom + pre.insets.bottom)
        post = self.post_layout(self.block, inner, self.title_style, self.context)
        items = [p for p in [pre.placed, content, post] if p]
        return PlacedGroup(items)


def paragraph_layout(block: Block, bounds: Rect, context: PDF) -> PlacedContent:
    results = []
    b = bounds
    for item in block.content:
        p = Paragraph(run_to_html(item, context))
        w, h = p.wrapOn(context, b.width, b.height)
        dh = max(0, w - b.width)
        dv = max(0, h - b.height)
        if dh > 0 or dv > 0:
            # The amount of excess overlap as an area
            overflow = w * dv + h * dh
        else:
            overflow = 0
        placed = PlacedParagraph(b.resize(width=w, height=h), p, overflow)
        results.append(placed)
        b = Rect(top=placed.bounds.bottom + block.padding,
                 left=b.left, right=b.right, bottom=b.bottom)
    if not results:
        return EmptyPlacedContent(bounds.resize(height=0))
    elif len(results) == 1:
        return results[0]
    else:
        return PlacedGroup(results)


def table_layout(block: Block, bounds: Rect, context: PDF) -> PlacedContent:
    cells = []
    for run in block.content:
        row = []
        for r in run.divide_by_spacers():
            if r.valid():
                row.append(Paragraph(run_to_html(r, context)))
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
    w, h = table.wrapOn(context, bounds.width, 1000)
    return PlacedParagraph(bounds.resize(width=w, height=h), table)


def banner_pre_layout(block: Block, bounds: Rect, style_name: str, context: PDF) -> BorderDetails:
    style = context.styles[style_name]
    if style.has_border():
        line_width = int(style.borderWidth)
    else:
        line_width = 0

    inset = line_width + block.padding
    margins = Margins.simple(inset)

    placed = []

    if block.title:
        title_mod = Run([e.replace_style(style_name) for e in block.title.items])
        title_bounds = bounds - margins
        paragraph, w, height = as_one_line(title_mod, context, title_bounds.width)
        plaque_height = height + 2 * block.padding
        title_bounds = title_bounds.resize(height=height)

        if style.background:
            plaque = (bounds - Margins.simple(line_width)).resize(height=plaque_height)
            placed.append(PlacedRect(plaque, style, fill=1, stroke=0))

        descent = descender(style)
        placed.append(PlacedParagraph(title_bounds.move(dy=-descent), paragraph))

        margins = Margins(left=inset, right=inset, top=inset + plaque_height, bottom=inset)

    group = PlacedGroup(placed)
    group.margins = margins
    return BorderDetails(group, margins)


def banner_post_layout(block: Block, bounds: Rect, style_name: str, context: PDF) -> Optional[PlacedContent]:
    style = context.styles[style_name]
    if style.has_border():
        return PlacedRect(bounds, style, fill=0, stroke=1)
    else:
        return None


def no_pre_layout(block: Block, bounds: Rect, style_name: str, context: PDF) -> BorderDetails:
    return BorderDetails(None, Margins.simple(0))


def no_post_layout(block: Block, bounds: Rect, style_name: str, context: PDF) -> Optional[PlacedContent]:
    return None


