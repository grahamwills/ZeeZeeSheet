"""Items to be placed on a page"""
from __future__ import annotations

from typing import Optional

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from common import Margins, Rect
from model import Element, ElementType, Run, Style
from pdf import PDF


def y(canvas: Canvas, y):
    return canvas._pagesize[1] - y


def rect(canvas: Canvas, r: Rect, fill=0, stroke=1):
    """ Draw rect inside the bounds"""
    d = canvas._lineWidth
    canvas.rect(r.left + d / 2, y(canvas, r.bottom) + d / 2, r.width - d, r.height - d, fill=fill, stroke=stroke)


class PlacedContent:
    bounds: Rect
    margins: Optional[Margins]

    def __init__(self, bounds: Rect) -> None:
        self.bounds = bounds
        self.margins = None

    def draw(self, canvas: Canvas, debug: bool):
        raise NotImplementedError()


class PlacedGroup(PlacedContent):
    group: [PlacedContent]

    def __init__(self, group: [PlacedContent]) -> None:
        super().__init__(Rect.union(p.bounds for p in group))
        self.group = group

    def draw(self, canvas: Canvas, debug: bool):
        for p in self.group:
            p.draw(canvas, debug)


class EmptyPlacedContent(PlacedContent):

    def draw(self, canvas: Canvas, debug: bool):
        pass


class PlacedParagraph(PlacedContent):
    paragraph: Paragraph
    overflow: float

    def __init__(self, bounds: Rect, paragraph: Paragraph, overflow: float = 0) -> None:
        super().__init__(bounds)
        self.paragraph = paragraph
        self.overflow = overflow

    def draw(self, canvas: Canvas, debug: bool):
        if debug:
            canvas.saveState()
            canvas.setLineWidth(1)
            canvas.setStrokeColorRGB(0, 0, 0, 0.25)
            canvas.setFillColorRGB(0, 0, 0, 0.1)
            rect(canvas, self.bounds, fill=1)
            canvas.restoreState()

        self.paragraph.drawOn(canvas, self.bounds.left, y(canvas, self.bounds.bottom))


class PlacedRect(PlacedContent):
    style: Style
    fill: int
    stroke: int

    def __init__(self, bounds: Rect, style: Style, fill=0, stroke=1):
        super().__init__(bounds)
        self.stroke = stroke
        self.fill = fill
        self.style = style

    def draw(self, canvas: Canvas, debug: bool):
        stroke = self.stroke and self.style.has_border()
        if stroke:
            canvas.setStrokeColorRGB(*self.style.borderColor.rgb)
            canvas.setLineWidth(self.style.borderWidth)
        else:
            canvas.setLineWidth(0)

        fill = self.fill and self.style.background is not None
        if fill:
            canvas.setFillColorRGB(*self.style.background.rgb)

        if fill or stroke:
            rect(canvas, self.bounds, fill=fill, stroke=stroke)


def element_to_html(e: Element, context: PDF):
    if e.which == ElementType.TEXT:
        txt = e.value
        if e.modifiers:
            if 'I' in e.modifiers:
                txt = '<i>' + txt + '</i>'
            if 'B' in e.modifiers:
                txt = '<b>' + txt + '</b>'
        if e.style:
            style = context.styles[e.style]
            size = " size='%d'" % style.size if style.size else ''
            face = " face='%s'" % style.font if style.font else ''
            color = " color='%s'" % style.color.get_hex_l() if style.color else ''
            return "<font %s%s%s>%s</font>" % (face, size, color, txt)
    else:
        return str(e)


def run_to_html(run: Run, context: PDF):
    return "".join(element_to_html(e, context) for e in run.items)


def as_one_line(run: Run, context: PDF, width: int):
    if not any(e.which == ElementType.SPACER for e in run.items):
        # No spacers -- nice and simple
        p = run_to_para(run, context)
        w, h = p.wrapOn(context, width, 1000)
        return p, w, h

    # Make a one-row table
    paragraphs = []

    commands = [
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('ALIGN', (-1, 0), (-1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]

    # Spacers divide up the run
    parts = run.divide_by_spacers()
    for i, sub in enumerate(parts):
        if sub.valid():
            if i == 0:
                align = "left"
            elif i == len(parts) - 1:
                align = "right"
            else:
                align = 'center'
            para = run_to_para(sub, context, align=align)
            paragraphs.append(para)

    table = Table([paragraphs])

    table.setStyle(TableStyle(commands))

    w, h = table.wrapOn(context, width, 1000)

    return table, w, h


def run_to_para(run, context, align='left') -> Paragraph:
    return Paragraph("<para autoleading='min' align='%s'>%s</para>" % (align, run_to_html(run, context)))


def descender(style: Style) -> float:
    return -pdfmetrics.getDescent(style.font, style.size)
