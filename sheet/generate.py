from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

import reader
from common import Context, Margins, Rect
from model import Sheet
from place import Placement, layout


def generate(sheet: Sheet, out):
    canvas = Canvas(out, pagesize=letter)
    context = Context(canvas, sheet.styles, debug=False)

    M = sheet.margin
    outer = Rect(left=0, top=0, right=letter[0], bottom=letter[1]) - Margins(M, M, M, M)

    placement = Placement(sheet, context)
    layout(placement, outer)

    placement.draw()
    context.canvas.showPage()
    context.canvas.save()


if __name__ == '__main__':
    luna = reader.read('../data/luna.rst')
    # luna.print()
    generate(luna, '../tmp/luna.pdf')
