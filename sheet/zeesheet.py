from __future__ import annotations
import subprocess
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import pdf
import reader
from layout.sheet import layout_sheet


def install():
    font_file = Path(__file__).parent.parent.joinpath('data/fonts/Symbola.ttf')
    symbola_font = TTFont('Symbola', font_file)
    pdfmetrics.registerFont(symbola_font)


if __name__ == '__main__':
    # Read
    install()
    luna = reader.read_sheet('../data/luna.rst')

    # Create
    context = pdf.PDF('../tmp/luna.pdf', luna.styles, debug=False)
    layout_sheet(luna, context)
    context.finish()

    # Display
    subprocess.run(['open', '../tmp/luna.pdf'], check=True)


