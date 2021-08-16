from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import dnd4e
from common import DATA_DIR
from sheet import common, pdf, reader
from sheetlayout import layout_sheet

LOGGER = common.configured_logger(__name__)


def show(file: str):
    sheet = reader.read_sheet(file)
    # sheet.print()
    out = file.replace('.rst', '.pdf').replace("../data", "../tmp")
    context = pdf.PDF(out, sheet.styles, sheet.pagesize, debug=False)
    layout_sheet(sheet, context)
    subprocess.run(['open', out], check=True)


def find_file(d, ext) -> Optional[Path]:
    results = list(d.glob('*.' + ext))
    if not results:
        return None
    if len(results) > 1:
        LOGGER.warning("Directory had multiple files with extension '%s', ignoring all except first: %s", ext, d)
    return results[0]


if __name__ == '__main__':

    DEBUG = False

    character_dir = DATA_DIR.joinpath('characters')
    if not character_dir.exists():
        raise ValueError("character director '%s' does not exist", character_dir)

    if len(sys.argv) > 1:
        target_directories = [character_dir.joinpath(name) for name in sys.argv[1:]]
    else:
        target_directories = [f for f in character_dir.glob('*') if f.is_dir()]

    for i, d in enumerate(target_directories):
        t = time.time()
        print("[%d/%d]: Making sheet for '%s'" % (i+1, len(target_directories), d.name))

        file_4e = find_file(d, 'dnd4e')
        if file_4e:
            print("  .. Converting '%s' to ReStructuredText file" % file_4e.name)
            result = dnd4e.convert(file_4e)
            print("  .. ReStructuredText file = %s" % result)

        file_rst = find_file(d, 'rst')
        if file_rst:
            sheet = reader.read_sheet(file_rst)
            # sheet.print()
            out = file_rst.parent.joinpath(file_rst.stem + '.pdf')
            context = pdf.PDF(out, sheet.styles, sheet.pagesize, debug=DEBUG)
            layout_sheet(sheet, context)
            subprocess.run(['open', out], check=True)
        else:
            print(" .. No ReStructuredText file (*.rst) found, skipping directory")

        print("  .. Completed '%s' in %1.1f seconds" % (d.name, time.time() - t))
