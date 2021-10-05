import subprocess

from layout.pdf import PDF
from content import Content


def debug_placed_content(p: Content, pdf: PDF):
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
    subprocess.run(['open', "/_tmp/killme.pdf"], check=True)
