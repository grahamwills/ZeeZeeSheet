from __future__ import annotations

import functools
from copy import copy
from typing import List

from sheet.common import Margins, Rect, configured_logger
from block import layout_block
from section import stack_in_columns
from sheet.model import Block, Section, Sheet
from sheet.pdf import PDF
from placed import PlacedContent, PlacedGroupContent

LOGGER = configured_logger(__name__)


@functools.lru_cache
def make_block_layout(target: Block, width: int, pdf: PDF) -> PlacedContent:
    rect = Rect(left=0, top=0, width=width, height=1000)
    return layout_block(target, rect, pdf)


def place_block(bounds: Rect, block: Block, pdf: PDF) -> PlacedContent:
    base = copy(make_block_layout(block, bounds.width, pdf))
    base.move(dx=bounds.left - base.actual.left, dy=bounds.top - base.actual.top)
    return base


def place_section(bounds: Rect, section: Section, pdf: PDF) -> PlacedContent:
    children = [functools.partial(place_block, block=block, pdf=pdf) for block in section.content]
    placed = stack_in_columns(bounds, children, section.padding, **section.layout_method.options)
    LOGGER.info("Placed %s", section)
    if hasattr(make_block_layout, 'cache_info'):
        LOGGER.debug("Block Layout Cache info = %s", make_block_layout.cache_info())
        make_block_layout.cache_clear()
    return placed


def place_sheet(sheet: Sheet, bounds: Rect, pdf: PDF) -> PlacedGroupContent:
    children = [functools.partial(place_section, section=section, pdf=pdf) for section in sheet.content]
    return stack_in_columns(bounds, children, sheet.padding)


def draw_sheet(sheet: Sheet, sections: List[PlacedContent], pdf):
    page_index = 1
    margin = sheet.margin
    cumulative_offset = 0
    for section in sections:
        section_bounds = section.actual
        if section_bounds.bottom > cumulative_offset + sheet.pagesize[1] - margin:
            pdf.showPage()
            page_index += 1
            dy = section_bounds.top - margin
            pdf.translate(dx=0, dy=dy)
            cumulative_offset += dy
        section.draw()

    pdf.showPage()
    pdf.save()


def layout_sheet(sheet: Sheet, pdf: PDF):
    outer = Rect(left=0, top=0, right=sheet.pagesize[0], bottom=sheet.pagesize[1]) - Margins.all_equal(sheet.margin)
    top = place_sheet(sheet, outer, pdf)
    draw_sheet(sheet, top.group, pdf)
    # analyze_placement(top)
