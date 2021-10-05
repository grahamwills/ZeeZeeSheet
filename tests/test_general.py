from pathlib import Path

import common
import layout_content
from colour import Color
from layout.common import Rect
from layout.model import Block, Run
from layout.pdf import PDF
from content import TableContent
from style import Stylesheet

from layout_content import layout_block


def test_table_creation():
    stylesheet = Stylesheet()
    stylesheet.define('default', font='Gotham', size=10)
    pdf = PDF(Path("/_tmp/killme.pdf"), stylesheet, (500, 1000), True)
    bounds = Rect.make(left=0, top=0, right=120, bottom=100)

    r1 = Run().add("Kung Fu Points:", 'default')
    r2 = Run().add("[ ][ ][ ][ ][ ][ ][ ][ ]", 'default')
    r3 = Run().add("Impediments:", 'default')
    r4 = Run().add("[ ][ ][ ][ ][ ][ ][ ][ ]", 'default')

    cells = [
        [layout_content.make_paragraph(r1, pdf), layout_content.make_paragraph(r2, pdf)],
        [layout_content.make_paragraph(r3, pdf), layout_content.make_paragraph(r4, pdf)]
    ]

    t = layout_content.as_table(cells, bounds, pdf, 10)
    content = TableContent(t, bounds, pdf)

    assert content.actual == Rect.make(left=0, top=0, right=120, bottom=106)
    assert content.unused_width == 8
    assert content.bad_breaks == 0
    assert content.ok_breaks == 6


def test_block_table_creation():
    stylesheet = Stylesheet()
    stylesheet.define('default', color=Color('white'), background=Color('navy'), borderWidth=1, align='left', size=10,
                      font='Gotham')
    stylesheet.define('banner', font='Gotham', size=10)
    pdf = PDF(Path("/_tmp/killme.pdf"), (500, 1000), True)
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
