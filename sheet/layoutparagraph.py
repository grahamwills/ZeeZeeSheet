from typing import List, Optional, Sequence, Union

from reportlab.platypus import Flowable, Paragraph

from flowable import Paragraph, Table
from placed import PlacedContent, PlacedParagraphContent, PlacedTableContent
from sheet.common import Rect
from sheet.model import Element, ElementType, Run
from sheet.pdf import PDF
from sheet.style import Style


def place_within(p: Union[Paragraph, Table], r: Rect, pdf: PDF, posX=0, posY=0, descent_adjust=0.3) -> PlacedContent:
    """
        Create a placed paragraph within a set of bounds
        :param Paragraph p: place this
        :param Rect r:  within this
        :param int posX: <0 means to the left, 0 centered, > 0 to the right
        :param int posY:  <0 means at the top, 0 centered, > 0 at the right
    """

    if isinstance(p, Paragraph):
        pfc = PlacedParagraphContent(p, r, pdf)
    else:
        pfc = PlacedTableContent(p, r, pdf)
    a = pfc.actual
    if posX < 0:
        dx = r.left - a.left
    elif posX > 0:
        dx = r.right - a.right
    else:
        dx = r.center.x - a.center.x

    if posY < 0:
        dy = r.top - a.top
    elif posY > 0:
        dy = r.bottom - a.bottom
    else:
        dy = r.center.y - a.center.y

    pfc.move(dx=dx, dy=dy + descent_of(p) * descent_adjust)
    return pfc


def align_vertically_within(p: Paragraph, r: Rect, pdf: PDF, posY=0, metrics_adjust=0) -> PlacedParagraphContent:
    """
        Create a placed paragraph within a set of bounds
        :param Paragraph p: place this
        :param Rect r:  within this
        :param int posY:  <0 means at the top, 0 centered, > 0 at the right
    """

    pfc = PlacedParagraphContent(p, r, pdf)
    a = pfc.actual
    if posY < 0:
        dy = r.top - a.top - leading_extra(p) * metrics_adjust
    elif posY > 0:
        dy = r.bottom - a.bottom + descent_of(p) * metrics_adjust
    else:
        dy = r.center.y - a.center.y + descent_of(p) * metrics_adjust

    pfc.move(dy=dy)
    return pfc


def descent_of(p):
    if hasattr(p, 'blPara'):
        if hasattr(p.blPara, 'descent'):
            return p.blPara.descent
        else:
            return min(d.descent for d in p.blPara.lines)
    return 0


def leading_extra(p: Flowable):
    if hasattr(p, 'style'):
        return p.style.leading - p.style.fontSize
    else:
        return 0


def from_text(txt, style: Style, pdf: PDF) -> Paragraph:
    run = Run([Element(ElementType.TEXT, txt, style)])
    return make_paragraph(run, pdf)


def split_into_paragraphs(run, pdf, styles: List[Style] = None) -> List[Paragraph]:
    items = run.items
    row = []
    start = 0
    spacer_idx = 0
    for i, e in enumerate(items):
        if e.which in {ElementType.SPACER, ElementType.DIVIDER}:
            _add_to_row(row, items[start:i], pdf, styles)
            if e.which == ElementType.SPACER:
                spacer_idx += 1
            start = i + 1
    _add_to_row(row, items[start:], pdf, styles)
    return row


def _add_to_row(row, elements:Sequence[Element], pdf: PDF, styles):
    added = len(row)
    if styles and added < len(styles) and styles[added] is not None:
        elements = [e.with_style(e.style.clone_using(styles[added])) for e in elements]
    run = Run(elements)
    row.append(make_paragraph(run, pdf))


def make_paragraph(run: Run, pdf: PDF, align=None, size_factor=None) -> Optional[Paragraph]:
    if not len(run.items):
        return None

    style = pdf.paragraph_style_for(run)
    if align:
        style = style.clone(align=align)
    if size_factor:
        style = style.clone(size=style.size * size_factor)

    return Paragraph(run, style, pdf)
