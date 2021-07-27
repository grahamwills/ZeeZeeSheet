from typing import Dict

from reportlab.lib import pagesizes
from reportlab.pdfgen import canvas


class PDF(canvas.Canvas):
    output_file : str
    page_width: int
    page_height: int
    styles: Dict[str, object]
    debug: bool

    def __init__(self, output_file, styles: Dict, debug: bool = False) -> None:
        pagesize = pagesizes.letter
        super().__init__(output_file, pagesize=pagesize)
        self.page_width = int(pagesize[0])
        self.page_height = int(pagesize[1])
        self.styles = styles
        self.debug = debug

    def finish(self):
        self.showPage()
        self.save()
