from typing import Dict

from colour import Color
from reportlab.lib import pagesizes
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from common import Rect
from model import Element, ElementType, Run, Style


class PDF(canvas.Canvas):
    output_file: str
    page_width: int
    page_height: int
    _styles: Dict[str, Style]
    debug: bool

    def __init__(self, output_file, styles: Dict, debug: bool = False) -> None:
        pagesize = pagesizes.letter
        super().__init__(output_file, pagesize=pagesize)
        self.page_width = int(pagesize[0])
        self.page_height = int(pagesize[1])
        self._styles = styles
        self.debug = debug

    def finish(self):
        self.showPage()
        self.save()

    def style(self, style):
        return self._styles[style]

    def fillColor(self, color: Color, alpha=None):
        self.setFillColorRGB(*color.rgb, alpha=alpha)

    def strokeColor(self, color: Color, alpha=None):
        self.setStrokeColorRGB(*color.rgb, alpha=alpha)

    def fill_rect(self, r: Rect, style: Style):
        if style.background:
            self.fillColor(style.background)
            self.setLineWidth(0)
            self.rect(r.left, self.page_height - r.bottom, r.width, r.height, fill=1, stroke=0)

    def stroke_rect(self, r: Rect, style: Style):
        if style.borderColor and style.borderWidth:
            self.strokeColor(style.borderColor)
            self.setLineWidth(style.borderWidth)
            self.rect(r.left, self.page_height - r.bottom, r.width, r.height, fill=0, stroke=1)

    def draw_flowable(self, paragraph, bounds):
        paragraph.drawOn(self, bounds.left, self.page_height - bounds.bottom)

    def make_paragraph(self, run: Run, align='left'):
        style = self.style(run.base_style())

        """
    font: str = None
    align: str = None
    size: float = None
    color: Color = None
    background: Color = None
    borderColor: Color = None
    borderWidth: float = 0.5
        
        """

        pStyle = ParagraphStyle(name='a', fontName=style.font, fontSize=style.size, leading=style.size*1.2)


        html = "".join(_element_to_html(e, self) for e in run.items)
        html = "<para autoleading='off' align='%s'>%s</para>" % (align, html)
        return Paragraph(html, pStyle)

    def descender(self, style:Style) -> float:
        return -pdfmetrics.getDescent(style.font, style.size)


def _element_to_html(e: Element, pdf: PDF):
    if e.which == ElementType.TEXT:
        txt = e.value
        if e.modifiers:
            if 'I' in e.modifiers:
                txt = '<i>' + txt + '</i>'
            if 'B' in e.modifiers:
                txt = '<b>' + txt + '</b>'
        if e.style:
            style = pdf.style(e.style)
            size = " size='%d'" % style.size if style.size else ''
            face = " face='%s'" % style.font if style.font else ''
            color = " color='%s'" % style.color.get_hex_l() if style.color else ''
            return "<font %s%s%s>%s</font>" % (face, size, color, txt)
    else:
        return str(e)


def as_one_line(run: Run, context: PDF, width: int):
    if not any(e.which == ElementType.SPACER for e in run.items):
        # No spacers -- nice and simple
        p = context.make_paragraph(run)
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
            para = context.make_paragraph(sub, align=align)
            paragraphs.append(para)

    table = Table([paragraphs])

    table.setStyle(TableStyle(commands))

    w, h = table.wrapOn(context, width, 1000)

    return table, w, h
