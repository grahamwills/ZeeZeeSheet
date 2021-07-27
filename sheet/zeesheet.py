from __future__ import annotations
import subprocess

import reader
from common import Context
from layout.sheet import layout_sheet

if __name__ == '__main__':
    luna = reader.read_sheet('../data/luna.rst')
    context = Context('../tmp/luna.pdf', luna.styles, debug=False)
    layout_sheet(luna, context)
    context.finish()

    # Display
    subprocess.run(['open', '../tmp/luna.pdf'], check=True)


