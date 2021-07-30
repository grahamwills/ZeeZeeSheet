from typing import Dict

import reportlab.lib.colors
from colour import Color
from reportlab.lib import pagesizes
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from common import Rect, configured_logger
from model import Element, ElementType, Run, Style

LOGGER = configured_logger(__name__)

_CHECKED_BOX = '../data/images/system/checked.png'
_UNCHECKED_BOX = '../data/images/system/unchecked.png'


class PDF(canvas.Canvas):
    output_file: str
    page_width: int
    page_height: int
    _styles: Dict[str, Style]
    debug: bool

    _name_index: int

    def __init__(self, output_file, styles: Dict, debug: bool = False) -> None:
        pagesize = pagesizes.letter
        super().__init__(output_file, pagesize=pagesize)
        self.page_width = int(pagesize[0])
        self.page_height = int(pagesize[1])
        self._styles = styles
        self.debug = debug
        self._name_index = 0

    def finish(self):
        self.showPage()
        self.save()

    def drawImage(self, image, x, y, width=None, height=None, mask=None, preserveAspectRatio=False, anchor='c',
                  anchorAtXY=False, showBoundary=False):
        fileName = image.fileName if hasattr(image, 'fileName') else str(image)
        if fileName == _UNCHECKED_BOX:
            return self.add_checkbox(x, y, width, height, False)
        elif fileName == _CHECKED_BOX:
            return self.add_checkbox(x, y, width, height, True)
        else:
            return super().drawImage(image, x, y, width, height, mask, preserveAspectRatio, anchor, anchorAtXY,
                                     showBoundary)

    def add_checkbox(self, rx, ry, width, height, state) -> (int, int):
        x, y = self.absolutePosition(rx, ry)
        self._name_index += 1
        name = "f%d" % self._name_index
        LOGGER.debug("Adding checkbox name='%s' with state=%s ", name, state)
        self.acroForm.checkbox(name=name, x=x - 0.5, y=y - 0.5, size=min(width, height) + 1,
                               fillColor=reportlab.lib.colors.Color(1, 1, 1),
                               buttonStyle='cross', borderWidth=0.5, checked=state)
        return (width, height)

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

    def draw_flowable(self, flowable, bounds):
        if self.debug:
            self.stroke_rect(bounds, Style(borderColor=Color('red')))

        if hasattr(flowable, 'style'):
            self._drawing_style = flowable.style

        flowable.drawOn(self, bounds.left, self.page_height - bounds.bottom)

    def make_paragraph(self, run: Run, align=None, size_factor=1.0):
        style = self.style(run.base_style())

        align = align or style.align

        alignment = {'left': 0, 'center': 1, 'right': 2, 'fill': 4, 'justify': 4}[align]

        size = round(style.size * size_factor)
        pStyle = ParagraphStyle(name='tmp',
                                fontName=style.font, fontSize=size, leading=size * 1.2,
                                allowWidows=0, embeddedHyphenation=1, alignment=alignment,
                                textColor=reportlab.lib.colors.Color(*style.color.rgb))

        # Add spaces between check boxes and other items
        items = []
        for e in run.items:
            if e is not run.items[0] and not e.value[0] in ":;-=":
                items.append(' ')
            items.append(_element_to_html(e, self, style))
        return Paragraph("".join(items), pStyle)

    def descender(self, style: Style) -> float:
        return -pdfmetrics.getDescent(style.font, style.size)


def _element_to_html(e: Element, pdf: PDF, base_style: Style):
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

    if style.size and style.size != base_style.size:
        size = " size='%d'" % style.size
    else:
        size = ''

    if style.font and style.font != base_style.font:
        face = " face='%s'" % style.font
    else:
        face = ''

    if style.color and style.color != base_style.color:
        color = " color='%s'" % style.color.get_hex_l()
    else:
        color = ''

    if e.which == ElementType.CHECKBOX:
        target = _UNCHECKED_BOX if e.value in {'O', 'o', ' ', '0'} else _CHECKED_BOX
        return "<img height=%d width=%d src='%s'/>" % (style.size, style.size, target)
    if e.which != ElementType.TEXT:
        face = " face='Symbola'"
    if face or size or color:
        return "<font %s%s%s>%s</font>" % (face, size, color, txt)
    else:
        return txt