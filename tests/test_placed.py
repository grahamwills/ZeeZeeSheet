import pytest
from reportlab.platypus import Paragraph

from model import Style
from sheet.common import Rect
from sheet.pdf import PDF
from sheet.placement.placed import PlacedFlowableContent, PlacedGroupContent, PlacedRectContent, PlacementError


@pytest.fixture
def pdf() -> PDF:
    return PDF("/tmp/killme.pdf", dict(), (500, 1000), False)


@pytest.fixture
def simple() -> Paragraph:
    return Paragraph("This is some very simple text")


@pytest.fixture
def styled() -> Paragraph:
    return Paragraph("<para leading=20>This is <b>some</b> very simple text</para>")


def test_paragraph_on_one_line(simple, pdf):
    defined = Rect(left=0, top=0, width=150, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=21, surplus_height=28, bad_breaks=0, ok_breaks=0)


def test_paragraph_which_wraps_once(simple, pdf):
    defined = Rect(left=0, top=0, width=80, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=32, surplus_height=16, bad_breaks=0, ok_breaks=1)


def test_paragraph_which_wraps_a_lot(simple, pdf):
    defined = Rect(left=0, top=0, width=30, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=13, surplus_height=-20, bad_breaks=0, ok_breaks=4)


def test_paragraph_which_wraps_badly(simple, pdf):
    defined = Rect(left=0, top=0, width=24, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=18, surplus_height=-44, bad_breaks=4, ok_breaks=2)


def test_styled_paragraph_on_one_line(styled, pdf):
    defined = Rect(left=0, top=0, width=150, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=19, surplus_height=20, bad_breaks=0, ok_breaks=0)


def test_styled_paragraph_which_wraps_once(styled, pdf):
    defined = Rect(left=0, top=0, width=80, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=32, surplus_height=0, bad_breaks=0, ok_breaks=1)


def test_styled_paragraph_which_wraps_a_lot(styled, pdf):
    defined = Rect(left=0, top=0, width=30, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=13, surplus_height=-60, bad_breaks=0, ok_breaks=4)


def test_styled_paragraph_which_wraps_badly(styled, pdf):
    defined = Rect(left=0, top=0, width=24, height=40)
    p = PlacedFlowableContent(styled, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=18, surplus_height=-100, bad_breaks=3, ok_breaks=1)


def test_paragraph_which_wraps_because_of_newline(pdf):
    simple = Paragraph("This is some very<BR/>simple text")
    defined = Rect(left=0, top=0, width=200, height=40)
    p = PlacedFlowableContent(simple, defined, pdf)
    assert p.requested == defined
    assert p.error() == PlacementError(surplus_width=152, surplus_height=16, bad_breaks=0, ok_breaks=0)


def test_rectangle(pdf):
    r = PlacedRectContent(Rect(left=10, top=10, right=100, bottom=100), Style(), pdf)
    assert r.actual == r.requested
    assert r.error() == PlacementError(0, 0, 0, 0)


def test_group(simple, styled, pdf):
    simple_placed = PlacedFlowableContent(simple, Rect(left=0, top=40, width=80, height=40), pdf)
    styled_placed = PlacedFlowableContent(styled, Rect(left=0, top=5, width=24, height=40), pdf)

    g = PlacedGroupContent(Rect(left=0, top=0, right=100, bottom=100), [simple_placed, styled_placed], pdf)
    assert g.actual == Rect(left=0, top=5, right=48, bottom=145)
    assert g.error() == PlacementError(surplus_width=52, surplus_height=-40, ok_breaks=2, bad_breaks=3)
