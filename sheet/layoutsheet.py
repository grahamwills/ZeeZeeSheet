from __future__ import annotations

import functools
import warnings
from copy import copy
from typing import List

from reportlab.platypus import Image

from layoutblock import layout_block
from layoutsection import stack_in_columns
from placed import PlacedContent, PlacedGroupContent
from sheet.common import Margins, Rect, configured_logger
from sheet.model import Block, Sheet
from sheet.pdf import PDF

LOGGER = configured_logger(__name__)


@functools.lru_cache(maxsize=1024)
def make_block_layout(target: Block, width: int, pdf: PDF) -> PlacedContent:
    rect = Rect.make(left=0, top=0, width=width, height=1000)
    return layout_block(target, rect, pdf)


def place_block(bounds: Rect, block: Block, pdf: PDF) -> PlacedContent:
    base = copy(make_block_layout(block, bounds.width, pdf))
    base.move(dx=bounds.left - base.requested.left, dy=bounds.top - base.requested.top)
    return base


def place_sheet(sheet: Sheet, outer: Rect, pdf: PDF) -> PlacedGroupContent:
    children = []
    bounds = outer
    for section in sheet.content:
        blocks = [functools.partial(place_block, block=block, pdf=pdf) for block in section.content]

        # Add all pages creatd by stacking in columns
        placed_pages = stack_in_columns(bounds, outer, blocks, section.spacing.padding, section.method.options)
        children += placed_pages

        # Set bounds top for the next section
        bounds = Rect.make(left=bounds.left, right=bounds.right,
                           top=placed_pages[-1].actual.bottom + sheet.spacing.padding, bottom=bounds.bottom)

        LOGGER.info("Placed %s", section)
        if hasattr(make_block_layout, 'cache_info'):
            LOGGER.debug("Block Layout Cache info = %s", make_block_layout.cache_info())
            make_block_layout.cache_clear()

    return PlacedGroupContent(children, outer)


def draw_watermark(sheet: Sheet, pdf: PDF):
    image = sheet.watermark
    if not image:
        return
    if not hasattr(image, 'imageHeight'):
        # replace it with a real image, not the name fo the file
        file = pdf.working_dir.joinpath(sheet.watermark)
        image = Image(file)
        scale = max(sheet.pagesize[0] / image.imageWidth, sheet.pagesize[1] / image.imageHeight)
        sheet.watermark = Image(file, width=scale * image.imageWidth, height=scale * image.imageHeight)
        sheet.watermark.wrapOn(pdf, sheet.pagesize[0], sheet.pagesize[1])

    pdf.saveState()
    pdf.resetTransforms()
    sheet.watermark.drawOn(pdf, 0, 0)
    pdf.restoreState()


def draw_sheet(sheet: Sheet, sections: List[PlacedContent], pdf):
    draw_watermark(sheet, pdf)
    for section in sections:
        if section.page_break_before:
            pdf.showPage()
            draw_watermark(sheet, pdf)
        section.draw()
    pdf.showPage()
    pdf.save()


def layout_sheet(sheet: Sheet, pdf: PDF):
    margins = Margins.all_equal(sheet.spacing.margin)
    outer = Rect.make(left=0, top=0, right=sheet.pagesize[0], bottom=sheet.pagesize[1]) - margins
    with warnings.catch_warnings(record=True) as warns:
        top = place_sheet(sheet, outer, pdf)
        for w in warns:
            LOGGER.warning("[%s:%s] While placing: %s" % (w.filename, w.lineno, w.message))

    with warnings.catch_warnings(record=True) as warns:
        draw_sheet(sheet, top.group, pdf)
        for w in warns:
            LOGGER.warning("[%s:%s] While drawing: %s" % (w.filename, w.lineno, w.message))
    # analyze_placement(top)
