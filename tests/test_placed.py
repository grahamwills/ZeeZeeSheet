from collections import namedtuple
from pathlib import Path

import pytest
from colour import Color
from reportlab.platypus import Paragraph

import layoutparagraph
from placed import PlacedFlowableContent, PlacedGroupContent, PlacedRectContent, \
    calculate_unused_width_for_group
from flowable import Table, line_info
from sheet.common import Rect
from sheet.model import Run
from sheet.pdf import PDF
from sheet.style import Style, Stylesheet


@pytest.fixture
def pdf() -> PDF:
    return PDF(Path("/tmp/killme.pdf"), Stylesheet(), (500, 1000), True)


@pytest.fixture
def simple() -> Paragraph:
    return Paragraph("This is some fantastical text")


@pytest.fixture
def styled() -> Paragraph:
    return Paragraph("<para leading=20>This is <b>some</b> fantastical text</para>")


@pytest.fixture
def table(simple, styled) -> Table:
    cells = [
        [styled, simple],
        [Paragraph('Just a long piece of text that will need wrapping in most situations')],
    ]


    return Table(cells, padding=5)


def test_paragraph_on_one_line(simple, pdf):
    defined = Rect(left=0, top=0, width=150, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p.bad_breaks == 0
    assert p.ok_breaks == 0
    assert p.unused_width == 27
    assert p.internal_variance == 0


def test_paragraph_which_wraps_once(simple, pdf):
    defined = Rect(left=0, top=0, width=80, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.bad_breaks == 0
    assert p.ok_breaks == 1
    assert p.unused_width == 16
    assert p.internal_variance == 0


def test_paragraph_which_wraps_a_lot(simple, pdf):
    defined = Rect(left=0, top=0, width=30, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.bad_breaks == 1
    assert p.ok_breaks == 3
    assert p.unused_width == 1
    assert p.internal_variance == 0


def test_paragraph_which_wraps_badly(simple, pdf):
    defined = Rect(left=0, top=0, width=24, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.bad_breaks == 3
    assert p.ok_breaks == 2
    assert p.unused_width == 1
    assert p.internal_variance == 0


def test_styled_paragraph_on_one_line(styled, pdf):
    defined = Rect(left=0, top=0, width=150, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.bad_breaks == 0
    assert p.ok_breaks == 0
    assert p.unused_width == 25
    assert p.internal_variance == 0


def test_styled_paragraph_which_wraps_once(styled, pdf):
    defined = Rect(left=0, top=0, width=80, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.bad_breaks == 0
    assert p.ok_breaks == 1
    assert p.unused_width == 16
    assert p.internal_variance == 0


def test_styled_paragraph_which_wraps_a_lot(styled, pdf):
    defined = Rect(left=0, top=0, width=30, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p.bad_breaks == 2
    assert p.ok_breaks == 1
    assert p.unused_width == 1
    assert p.internal_variance == 0


def test_styled_paragraph_which_wraps_badly(styled, pdf):
    defined = Rect(left=0, top=0, width=24, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.bad_breaks == 3
    assert p.ok_breaks == 0
    assert p.unused_width == 1
    assert p.internal_variance == 0


def test_paragraph_which_wraps_because_of_newline(pdf):
    simple = Paragraph("This is some very simple <BR/>text")
    defined = Rect(left=0, top=0, width=200, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.bad_breaks == 0
    assert p.ok_breaks == 0
    assert p.unused_width == 90
    assert p.internal_variance == 0


def test_rectangle(pdf):
    r = PlacedRectContent(Rect(left=10, top=10, right=100, bottom=100), Style(), pdf)
    assert r.actual == r.requested
    assert r.bad_breaks == 0
    assert r.ok_breaks == 0
    assert r.unused_width == 0
    assert r.internal_variance == 0


def test_group_bad_fits(simple, styled, pdf):
    simple_placed = PlacedFlowableContent(simple, Rect(left=0, top=40, width=80, height=40), pdf)
    styled_placed = PlacedFlowableContent(styled, Rect(left=80, top=5, width=24, height=40), pdf)

    gp = PlacedGroupContent([simple_placed, styled_placed], Rect(left=0, top=0, right=200, bottom=100))
    assert gp.actual == Rect(left=0, top=5, right=103, bottom=125)
    assert gp.bad_breaks == 3
    assert gp.ok_breaks == 1
    assert gp.unused_width == 113
    assert gp.internal_variance == 0


def test_group_with_space_horizontal(simple, styled, pdf):
    a = PlacedFlowableContent(simple, Rect(left=10, top=40, right=200, height=40), pdf)
    b = PlacedFlowableContent(styled, Rect(left=200, top=5, right=350, height=40), pdf)

    gp = PlacedGroupContent([a, b], Rect(left=0, top=0, right=350, bottom=500))

    assert gp.bad_breaks == 0
    assert gp.ok_breaks == 0
    assert gp.unused_width == 35 + b.actual.left - a.actual.right
    assert gp.internal_variance == 0


def test_group_with_space_vertical(simple, styled, pdf):
    a = PlacedFlowableContent(simple, Rect(left=10, top=20, right=200, height=40), pdf)
    b = PlacedFlowableContent(styled, Rect(left=40, top=50, right=200, height=40), pdf)

    gp = PlacedGroupContent([a, b], Rect(left=0, top=0, right=200, bottom=100))

    assert gp.bad_breaks == 0
    assert gp.ok_breaks == 0
    assert gp.unused_width == 61
    assert gp.internal_variance == 0


def test_group_with_space_vertical_second(simple, pdf):
    a = PlacedFlowableContent(simple, Rect(left=10, top=20, right=200, height=40), pdf)
    b = PlacedFlowableContent(Paragraph("a very long piece of text that will just fit"),
                              Rect(left=20, top=50, right=200, height=40), pdf)

    gp = PlacedGroupContent([a, b], Rect(left=0, top=0, right=200, bottom=100))

    assert gp.bad_breaks == 0
    assert gp.ok_breaks == 0
    assert gp.unused_width == 29
    assert gp.internal_variance == 0


def test_table_in_plenty_of_space(table, pdf):
    p = PlacedFlowableContent(table, Rect(left=10, top=10, width=400, height=100), pdf)
    assert p.bad_breaks == 0
    assert p.ok_breaks == 0
    assert p.unused_width == 100
    assert p.internal_variance == 0


def test_table_with_one_wraps(table, pdf):
    p = PlacedFlowableContent(table, Rect(left=10, top=10, width=280, height=100), pdf)
    assert p.bad_breaks == 0
    assert p.ok_breaks == 1
    assert p.unused_width == 12
    assert p.internal_variance == 2


def test_table_with_several_wraps(table, pdf):
    p = PlacedFlowableContent(table, Rect(left=10, top=10, width=180, height=100), pdf)
    assert p.bad_breaks == 0
    assert p.ok_breaks == 3
    assert p.unused_width == 3
    assert p.internal_variance == 0


def test_table_with_terrible_wraps(table, pdf):
    p = PlacedFlowableContent(table, Rect(left=10, top=10, width=40, height=100), pdf)

    assert p.bad_breaks == 0
    assert p.ok_breaks == 9
    assert p.unused_width == 0
    assert p.internal_variance == 0


def test_line_info():
    style = Style(align='left', font='Gotham', size=10, color=Color('black'))
    pdf = PDF(Path("/tmp/killme.pdf"), Stylesheet(), (500, 1000), True)

    run = Run().add("basic test", 'default')

    p = layoutparagraph.make_paragraph(run, pdf)
    p.wrapOn(pdf, 10, 100)
    bad_breaks, ok_breaks, unused = line_info(p)
    assert bad_breaks == 4
    assert ok_breaks == 1


def test_line_info_for_boxes():
    style = Style(align='left', font='Gotham', size=10, color=Color('black'))
    pdf = PDF(Path("/tmp/killme.pdf"), Stylesheet(), (500, 1000), True)

    run = Run().add("[ ][ ][ ][ ][ ][ ][ ][ ]", 'default')

    p = layoutparagraph.make_paragraph(run, pdf)
    p.wrapOn(pdf, 20, 100)
    bad_breaks, ok_breaks, unused = line_info(p)
    assert bad_breaks == 0
    assert ok_breaks == 7


MockContent = namedtuple('MockContent', 'requested unused_width')


def test_unused_group_of_horizontal():
    bounds = Rect(left=100, top=100, right=200, bottom=200)

    a = MockContent(Rect(left=130, top=100, right=170, bottom=200), 17)
    b = MockContent(Rect(left=180, top=100, right=190, bottom=200), 2)
    c = MockContent(Rect(left=100, top=100, right=190, bottom=200), 2)

    assert calculate_unused_width_for_group([a], bounds) == 30 + 30 + 17
    assert calculate_unused_width_for_group([a, b], bounds) == 30 + 10 + 10 + 17 + 2
    assert calculate_unused_width_for_group([c], bounds) == 10 + 2
    assert calculate_unused_width_for_group([a, c], bounds) == 10 + 2
    assert calculate_unused_width_for_group([b, c], bounds) == 10 + 2
    assert calculate_unused_width_for_group([a, b, c], bounds) == 10 + 2
