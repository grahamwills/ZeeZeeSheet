from __future__ import annotations
import subprocess

import pdf
import reader
from layout.sheet import layout_sheet

if __name__ == '__main__':
    # Read
    luna = reader.read_sheet('../data/luna.rst')

    # Create
    context = pdf.PDF('../tmp/luna.pdf', luna.styles, debug=False)
    layout_sheet(luna, context)
    context.finish()

    # Display
    subprocess.run(['open', '../tmp/luna.pdf'], check=True)


