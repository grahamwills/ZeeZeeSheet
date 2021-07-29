from typing import Dict

from colour import Color
from reportlab.lib import pagesizes
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

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
        return self._styles[style] if style else None

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
        if self.debug:
            self.stroke_rect(bounds, Style(borderColor=Color('red')))
        paragraph.drawOn(self, bounds.left, self.page_height - bounds.bottom)

    def make_paragraph(self, run: Run, align=None):
        style = self.style(run.base_style())

        align = align or style.align

        alignment = {'left':0, 'center':1, 'right':2, 'fill':4, 'justify':4}[align]

        pStyle = ParagraphStyle(name='a', fontName=style.font, fontSize=style.size, leading=style.size*1.2,
                                allowWidows=0, embeddedHyphenation =1, alignment=alignment)


        # Add spaces between check boxes and other items
        items = []
        for e in run.items:
            if e is not run.items[0] and not e.value[0] in ":;-=":
                items.append(' ')
            items.append(_element_to_html(e, self))
        return Paragraph("".join(items), pStyle)

    def descender(self, style: Style) -> float:
        return -pdfmetrics.getDescent(style.font, style.size)


def _element_to_html(e: Element, pdf: PDF):
    if e.which == ElementType.TEXT or e.which == ElementType.SYMBOL:
        txt = e.value
    else:
        txt = str(e)
    if e.modifiers:
        if 'I' in e.modifiers:
            txt = '<i>' + txt + '</i>'
        if 'B' in e.modifiers:
            txt = '<b>' + txt + '</b>'
    style = pdf.style(e.style)
    size = " size='%d'" % style.size if style.size else ''
    face = " face='%s'" % style.font if style.font else ''
    color = " color='%s'" % style.color.get_hex_l() if style.color else ''
    if e.which != ElementType.TEXT:
        face = " face='Symbola'"
    return "<font %s%s%s>%s</font>" % (face, size, color, txt)


