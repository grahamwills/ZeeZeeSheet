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
from sheet.model import Block, Section, Sheet
from sheet.pdf import PDF

LOGGER = configured_logger(__name__)


@functools.lru_cache
def make_block_layout(target: Block, width: int, pdf: PDF) -> PlacedContent:
    rect = Rect(left=0, top=0, width=width, height=1000)
    return layout_block(target, rect, pdf)


def place_block(bounds: Rect, block: Block, pdf: PDF) -> PlacedContent:
    base = copy(make_block_layout(block, bounds.width, pdf))
    base.move(dx=bounds.left - base.requested.left, dy=bounds.top - base.requested.top)
    return base


def place_section(bounds: Rect, section: Section, pdf: PDF) -> PlacedContent:
    children = [functools.partial(place_block, block=block, pdf=pdf) for block in section.content]

    placed = stack_in_columns(bounds, children, **section.layout_method.options)
    LOGGER.info("Placed %s", section)
    if hasattr(make_block_layout, 'cache_info'):
        LOGGER.debug("Block Layout Cache info = %s", make_block_layout.cache_info())
        make_block_layout.cache_clear()
    return placed


def place_sheet(sheet: Sheet, bounds: Rect, pdf: PDF) -> PlacedGroupContent:
    children = [functools.partial(place_section, section=section, pdf=pdf) for section in sheet.content]
    return stack_in_columns(bounds, children, sheet.padding)


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
    page_index = 1
    margin = sheet.margin
    cumulative_offset = 0
    draw_watermark(sheet, pdf)
    for section in sections:
        section_bounds = section.actual
        if section_bounds.bottom > cumulative_offset + sheet.pagesize[1] - margin:
            pdf.showPage()
            page_index += 1
            dy = section_bounds.top - margin
            pdf.translate(dx=0, dy=dy)
            cumulative_offset += dy
            draw_watermark(sheet, pdf)
        section.draw()

    pdf.showPage()
    pdf.save()


def layout_sheet(sheet: Sheet, pdf: PDF):
    outer = Rect(left=0, top=0, right=sheet.pagesize[0], bottom=sheet.pagesize[1]) - Margins.all_equal(sheet.margin)
    with warnings.catch_warnings(record=True) as warns:
        top = place_sheet(sheet, outer, pdf)
        for w in warns:
            LOGGER.warning("[%s:%s] While placing: %s" % (w.filename, w.lineno, w.message))

    with warnings.catch_warnings(record=True) as warns:
        draw_sheet(sheet, top.group, pdf)
        for w in warns:
            LOGGER.warning("[%s:%s] While drawing: %s" % (w.filename, w.lineno, w.message))
    # analyze_placement(top)
