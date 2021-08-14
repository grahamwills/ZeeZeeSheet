import subprocess

from sheet.pdf import PDF
from sheet.placement.placed import PlacedContent


def debug_placed_content(p: PlacedContent, pdf: PDF):
    pdf.setStrokeColorRGB(0, 0, 0, 0.2)
    pdf.setLineWidth(0.25)
    for v in range(0, 1000, 10):
        pdf.line(v, 0, v, 1000)
        pdf.line(0, v, 1000, v)

    pdf.setFillColorRGB(1, 0, 0, 0.2)
    pdf.rect(p.requested.left, pdf.page_height - p.requested.bottom, p.requested.width, p.requested.height, 0, 1)
    p.draw()
    pdf.showPage()
    pdf.save()
    subprocess.run(['open', "/tmp/killme.pdf"], check=True)
