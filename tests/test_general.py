from colour import Color

import table
import zeesheet
from conftest import debug_placed_content
from sheet.common import Rect
from block import layout_block
from sheet.model import Block, Run, Style
from sheet.pdf import PDF
from placed import PlacedFlowableContent


def test_table_creation():
    zeesheet.install()
    style = Style(align='left', font='Gotham', size=10, color=Color('black'))
    pdf = PDF("/tmp/killme.pdf", {'default': style}, (500, 1000), True)
    bounds = Rect(left=0, top=0, right=120, bottom=100)

    r1 = Run().add("Kung Fu Points:", 'default', '')
    r2 = Run().add("[ ][ ][ ][ ][ ][ ][ ][ ]", 'default', '')
    r3 = Run().add("Impediments:", 'default', '')
    r4 = Run().add("[ ][ ][ ][ ][ ][ ][ ][ ]", 'default', '')

    cells = [
        [pdf.make_paragraph(r1), pdf.make_paragraph(r2)],
        [pdf.make_paragraph(r3), pdf.make_paragraph(r4)]
    ]

    t = table.as_table(cells, bounds.width, pdf, 10)
    content = PlacedFlowableContent(t, bounds, pdf)
    debug_placed_content(content, pdf)


    assert content.actual == Rect(left=0, top=0, right=120, bottom=106)
    assert content.unused_width == 8
    assert content.bad_breaks == 0
    assert content.ok_breaks == 6


def test_block_table_creation():
    zeesheet.install()
    style = Style(align='left', font='Gotham', size=10, color=Color('black'))
    banner = Style(color=Color('white'), background=Color('navy'), borderWidth=1, align='left', size=10, font='Gotham')
    pdf = PDF("/tmp/killme.pdf", {'default': style, 'banner':banner}, (500, 1000), True)
    bounds = Rect(left=0, top=0, right=120, bottom=100)

    block = Block()
    # block.title_method = common.Command = common.parse_directive('banner style=banner')
    block.title = Run().add("Status", 'default', '')
    block.content = [
        Run().add("Kung Fu Points: | [ ][ ][ ][ ][ ][ ][ ][ ]", 'default', ''),
        Run().add("Impediments:    | [ ][ ][ ][ ][ ][ ][ ][ ]", 'default', '')
    ]

    content = layout_block(block, bounds, pdf)


    assert content.unused_width == 1
    assert content.bad_breaks == 0
    assert content.ok_breaks == 3
