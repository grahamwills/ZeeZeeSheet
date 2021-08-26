from pathlib import Path

from colour import Color

import common
import layoutparagraph
import table
from layoutblock import layout_block
from placed import PlacedTableContent
from sheet.common import Rect
from sheet.model import Block, Run
from sheet.pdf import PDF
from style import Stylesheet


def test_table_creation():
    stylesheet = Stylesheet()
    stylesheet.define('default', font='Gotham', size=10)
    pdf = PDF(Path("/tmp/killme.pdf"), stylesheet, (500, 1000), True)
    bounds = Rect.make(left=0, top=0, right=120, bottom=100)

    r1 = Run().add("Kung Fu Points:", 'default')
    r2 = Run().add("[ ][ ][ ][ ][ ][ ][ ][ ]", 'default')
    r3 = Run().add("Impediments:", 'default')
    r4 = Run().add("[ ][ ][ ][ ][ ][ ][ ][ ]", 'default')

    cells = [
        [layoutparagraph.make_paragraph(r1, pdf), layoutparagraph.make_paragraph(r2, pdf)],
        [layoutparagraph.make_paragraph(r3, pdf), layoutparagraph.make_paragraph(r4, pdf)]
    ]

    t = table.as_table(cells, bounds, pdf, 10)
    content = PlacedTableContent(t, bounds, pdf)

    assert content.actual == Rect.make(left=0, top=0, right=120, bottom=106)
    assert content.unused_width == 8
    assert content.bad_breaks == 0
    assert content.ok_breaks == 6


def test_block_table_creation():
    stylesheet = Stylesheet()
    stylesheet.define('default', color=Color('white'), background=Color('navy'), borderWidth=1, align='left', size=10,
                      font='Gotham')
    stylesheet.define('banner', font='Gotham', size=10)
    pdf = PDF(Path("/tmp/killme.pdf"), stylesheet, (500, 1000), True)
    bounds = Rect.make(left=0, top=0, right=120, bottom=100)

    block = Block()
    block.title_method = common.parse_directive('banner style=banner')
    block.title = Run().add("Status", 'default')
    block.content = [
        Run().add("Kung Fu Points: | [ ][ ][ ][ ][ ][ ][ ][ ]", 'default'),
        Run().add("Impediments:    | [ ][ ][ ][ ][ ][ ][ ][ ]", 'default')
    ]

    content = layout_block(block, bounds, pdf)

    assert content.unused_width == 0
    assert content.bad_breaks == 0
    assert content.ok_breaks == 6
