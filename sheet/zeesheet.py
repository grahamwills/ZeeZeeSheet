from __future__ import annotations

import subprocess
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from sheet import common, pdf, reader
from sheet.layout.sheet import layout_sheet
from sheet.pdf import build_font_choices

LOGGER = common.configured_logger(__name__)

def install():
    font_file = Path(__file__).parent.parent.joinpath('data/fonts/Symbola.ttf')
    symbola_font = TTFont('Symbola', font_file)
    pdfmetrics.registerFont(symbola_font)

    fonts = build_font_choices()
    LOGGER.info("Installed fonts %s", fonts)

def show(file:str):
    sheet = reader.read_sheet(file)
    # sheet.print()
    out = file.replace('.rst', '.pdf').replace("../data", "../tmp")
    context = pdf.PDF(out, sheet.styles, sheet.pagesize, debug=True)
    layout_sheet(sheet, context)
    subprocess.run(['open', out], check=True)


if __name__ == '__main__':
    # Read
    install()

    if True:
        show('../data/ethik.rst')
        show('../data/grumph.rst')
        show('../data/mouse.rst')
        show('../data/luna.rst')
    else:
        show('../data/test.rst')



