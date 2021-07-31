from __future__ import annotations
import subprocess
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import common
import pdf
import reader
from layout.sheet import layout_sheet
from render import build_font_choices

LOGGER = common.configured_logger(__name__)

def install():
    font_file = Path(__file__).parent.parent.joinpath('data/fonts/Symbola.ttf')
    symbola_font = TTFont('Symbola', font_file)
    pdfmetrics.registerFont(symbola_font)

    fonts = build_font_choices()
    LOGGER.info("Installed fonts %s", fonts)


if __name__ == '__main__':
    # Read
    install()
    luna = reader.read_sheet('../data/luna.rst')

    luna.print()

    # Create
    context = pdf.PDF('../tmp/luna.pdf', luna.styles, debug=False)
    layout_sheet(luna, context)

    # Display
    subprocess.run(['open', '../tmp/luna.pdf'], check=True)


