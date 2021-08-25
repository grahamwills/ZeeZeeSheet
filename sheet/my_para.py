from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

from pdf import PDF


class MyParagraph(Paragraph):
    def __init__(self, items, style:ParagraphStyle, pdf:PDF):
        super().__init__(items, style)
        leading = pdf.leading_for(style)
        descent = pdf.descender(style)
        self.v_offset = style.fontSize*1.2 - leading + descent/2
        self._showBoundary = pdf.debug

    def drawOn(self, pdf:PDF, x, y, _sW=0):
        pdf.translate(0, self.v_offset)
        super().drawOn(pdf, x, y, _sW)
        pdf.translate(0, -self.v_offset)