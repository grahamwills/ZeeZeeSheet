import subprocess

import pytest
from reportlab.lib import colors
from reportlab.platypus import Paragraph, Table, TableStyle

from model import Style
from sheet.common import Rect
from sheet.pdf import PDF
from sheet.placement.placed import PlacedContent, PlacedFlowableContent, PlacedGroupContent, PlacedRectContent, \
    PlacementError


@pytest.fixture
def pdf() -> PDF:
    return PDF("/tmp/killme.pdf", dict(), (500, 1000), False)


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

    commands = [
        ('GRID', (0, 0), (-1, -1), 1, colors.green),
        ('SPAN', (0, 1), (-1, 1)),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]

    return Table(cells, style=TableStyle(commands))


def test_paragraph_on_one_line(simple, pdf):
    defined = Rect(left=0, top=0, width=150, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=27, bad_breaks=0, ok_breaks=0)


def test_paragraph_which_wraps_once(simple, pdf):
    defined = Rect(left=0, top=0, width=80, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=16, bad_breaks=0, ok_breaks=1)


def test_paragraph_which_wraps_a_lot(simple, pdf):
    defined = Rect(left=0, top=0, width=30, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=1, bad_breaks=2, ok_breaks=2)


def test_paragraph_which_wraps_badly(simple, pdf):
    defined = Rect(left=0, top=0, width=24, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=1, bad_breaks=5, ok_breaks=0)


def test_styled_paragraph_on_one_line(styled, pdf):
    defined = Rect(left=0, top=0, width=150, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=25, bad_breaks=0, ok_breaks=0)


def test_styled_paragraph_which_wraps_once(styled, pdf):
    defined = Rect(left=0, top=0, width=80, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=16,bad_breaks=0, ok_breaks=1)


def test_styled_paragraph_which_wraps_a_lot(styled, pdf):
    defined = Rect(left=0, top=0, width=30, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=1, bad_breaks=2, ok_breaks=1)


def test_styled_paragraph_which_wraps_badly(styled, pdf):
    defined = Rect(left=0, top=0, width=24, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=1, bad_breaks=3, ok_breaks=0)


def test_paragraph_which_wraps_because_of_newline(pdf):
    simple = Paragraph("This is some very simple <BR/>text")
    defined = Rect(left=0, top=0, width=200, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p._error == PlacementError(surplus_width=90, bad_breaks=0, ok_breaks=0)


def test_rectangle(pdf):
    r = PlacedRectContent(Rect(left=10, top=10, right=100, bottom=100), Style(), pdf)
    assert r.actual == r.requested
    assert r._error == PlacementError(0, 0, 0, 0)


def test_group(simple, styled, pdf):
    simple_placed = PlacedFlowableContent(simple, Rect(left=0, top=40, width=80, height=40), pdf)
    styled_placed = PlacedFlowableContent(styled, Rect(left=0, top=5, width=24, height=40), pdf)

    g = PlacedGroupContent([simple_placed, styled_placed], Rect(left=0, top=0, right=100, bottom=100))
    assert g.actual == Rect(left=0, top=5, right=64, bottom=125)
    assert g.error_from_variance(1) == 0
    assert g.error_from_size(1, 0) == 0
    assert g.error_from_size(0, 1) == 0
    assert g.error_from_breaks(1, 0) == 3
    assert g.error_from_breaks(0, 1) == 1


def _show(p: PlacedContent, pdf: PDF):
    pdf.setFillColorRGB(1, 0, 0, 0.2)
    pdf.rect(p.requested.left, pdf.page_height - p.requested.bottom, p.requested.width, p.requested.height, 0, 1)
    p.draw()
    pdf.showPage()
    pdf.save()
    subprocess.run(['open', "/tmp/killme.pdf"], check=True)


def test_table_in_plenty_of_space(table, pdf):
    pdf = PDF("/tmp/killme.pdf", dict(), (620, 620), False)
    p = PlacedFlowableContent(table, Rect(left=10, top=10, width=400, height=100), pdf)
    _show(p, pdf)
    assert p._error == PlacementError(surplus_width=100, bad_breaks=0, ok_breaks=0)


def test_table_with_one_wraps(table, pdf):
    p = PlacedFlowableContent(table, Rect(left=10, top=10, width=280, height=100), pdf)
    assert p._error == PlacementError(surplus_width=12, bad_breaks=0, ok_breaks=1, internal_variance=2)


def test_table_with_several_wraps(table, pdf):
    p = PlacedFlowableContent(table, Rect(left=10, top=10, width=180, height=100), pdf)
    assert p._error == PlacementError(surplus_width=3,bad_breaks=0, ok_breaks=3)



def test_table_with_terrible_wraps(table, pdf):
    p = PlacedFlowableContent(table, Rect(left=10, top=10, width=40, height=100), pdf)
    assert p._error == PlacementError(surplus_width=0, bad_breaks=0, ok_breaks=9)
