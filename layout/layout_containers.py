from __future__ import annotations

import functools
import math
import statistics
import time
import warnings
from typing import List, Optional, Tuple

from reportlab.platypus import Image

from structure import Sheet
from util import FINE, Margins, Optimizer, Rect, configured_logger, divide_space
from .layout_content import make_block_layout, place_block
from .pdf import PDF
from .content import Content, GroupContent

LOGGER = configured_logger(__name__)


def place_sheet(sheet: Sheet, outer: Rect, pdf: PDF) -> GroupContent:
    children = []
    bounds = outer
    page_break = False
    for section in sheet.content:
        blocks = [functools.partial(place_block, block=block, pdf=pdf) for block in section.content]

        # Add all pages creatd by stacking in columns
        placed_pages = stack_in_columns(bounds, outer, blocks, section.spacing.padding, section.method.options, page_break)
        children += placed_pages

        # Set bounds top for the next section
        bounds = Rect.make(left=bounds.left, right=bounds.right,
                           top=placed_pages[-1].actual.bottom + sheet.spacing.padding, bottom=bounds.bottom)

        LOGGER.info("Placed %s", section)
        if hasattr(make_block_layout, 'cache_info'):
            LOGGER.debug("Block Layout Cache info = %s", make_block_layout.cache_info())
            make_block_layout.cache_clear()
        page_break = section.page_break_after

    return GroupContent(children, outer)


def draw_watermark(sheet: Sheet, pdf: PDF):
    image = sheet.watermark
    if not image:
        return
    if not hasattr(image, 'imageHeight'):
        # replace it with a real image, not the name fo the file
        file = pdf.base_dir.joinpath(sheet.watermark)
        image = Image(file)
        scale = max(sheet.pagesize[0] / image.imageWidth, sheet.pagesize[1] / image.imageHeight)
        sheet.watermark = Image(file, width=scale * image.imageWidth, height=scale * image.imageHeight)
        sheet.watermark.wrapOn(pdf, sheet.pagesize[0], sheet.pagesize[1])

    pdf.saveState()
    pdf.resetTransforms()
    sheet.watermark.drawOn(pdf, 0, 0)
    pdf.restoreState()


def draw_sheet(sheet: Sheet, sections: List[Content], pdf):
    draw_watermark(sheet, pdf)
    for section in sections:
        if section.page_break_before:
            pdf.showPage()
            draw_watermark(sheet, pdf)
        section.draw()

    pdf.showPage()
    pdf.save()


def layout_sheet(sheet: Sheet, pdf: PDF):
    margins = Margins.balanced(sheet.spacing.margin)
    outer = Rect.make(left=0, top=0, right=sheet.pagesize[0], bottom=sheet.pagesize[1]) - margins
    with warnings.catch_warnings(record=True) as warns:
        top = place_sheet(sheet, outer, pdf)
        for w in warns:
            LOGGER.warning("[%s:%s] While placing: %s" % (w.filename, w.lineno, w.message))

    with warnings.catch_warnings(record=True) as warns:
        draw_sheet(sheet, top.group, pdf)
        for w in warns:
            LOGGER.warning("[%s:%s] While drawing: %s" % (w.filename, w.lineno, w.message))


MIN_COLUMN_WIDTH = 40


def place_in_column(placeables: List, bounds: Rect, padding: int) -> Optional[GroupContent]:
    assert bounds.width >= MIN_COLUMN_WIDTH

    current = bounds.top
    contents = []

    for place in placeables:
        available = Rect.make(top=current, left=bounds.left, right=bounds.right, bottom=bounds.bottom)
        p = place(available)
        contents.append(p)
        current = p.actual.bottom + padding
        if current > bounds.bottom + bounds.height * 0.1:
            # Give up -- it takes too much space
            break

    return GroupContent(contents, bounds)


class ColumnOptimizer(Optimizer):
    placeables: List
    outer: Rect
    padding: int

    def __init__(self, k: int, placeables: List, outer: Rect, padding: int):
        super().__init__(k)
        self.placeables = placeables
        self.outer = outer
        self.padding = padding

    def score(self, columns: [GroupContent]) -> float:
        column_bounds = [c.actual for c in columns]
        max_height = max(c.height for c in column_bounds)
        min_height = min(c.height for c in column_bounds)

        stddev = statistics.stdev(c.height for c in column_bounds) / 10

        # Increase the error quadratically  as it gets very far from balanced
        stddev *= 1 + max(0, max_height / min_height - 1) ** 2

        breaks = sum(c.error_from_breaks(30, 3) for c in columns)
        fit = sum(c.error_from_size(10, 0.01) for c in columns)
        var = sum(c.error_from_variance(0.1) for c in columns)

        if LOGGER.getEffectiveLevel() <= FINE:
            for i, c in enumerate(columns):
                LOGGER.fine("[%d] n=%d width=%d height=%d breaks=%1.3f fit=%1.3f", i,
                            len(c.group), c.actual.width, c.actual.height,
                            c.error_from_breaks(30, 3), c.error_from_size(10, 0.01))

        score = max_height + breaks + fit + stddev

        # If we didn't place everything, add that to the error also
        placed_count = sum(len(c) for c in columns)
        missed = len(self.placeables) - placed_count
        score += 1e6 * missed

        LOGGER.debug("Score: %1.3f -- max_ht=%1.1f, breaks=%1.3f, fit=%1.3f, stddev=%1.3f, var=%1.3f",
                     score, max_height, breaks, fit, stddev, var)
        return score

    def place_all(self, widths: Tuple[int], counts: Tuple[int]) -> List[Content]:
        LOGGER.fine("Placing with widths=%s, alloc=%s", widths, counts)
        placed_columns = []
        sum_widths = 0
        sum_counts = 0

        for width, count in zip(widths, counts):
            left = self.outer.left + sum_widths
            sum_widths += width
            right = self.outer.left + sum_widths
            sum_widths += self.padding

            first = sum_counts
            sum_counts += count
            last = sum_counts

            b = self.outer.make_column(left=left, right=right)
            placed = place_in_column(self.placeables[first:last], b, self.padding)
            placed_columns.append(placed)

        return placed_columns

    def __hash__(self):
        return id(self)


class ColumnAllocationOptimizer(ColumnOptimizer):
    widths: Tuple[int]

    def __init__(self, k: int, placeables: List, outer: Rect, widths: [int], padding: int):
        super().__init__(k, placeables, outer, padding)
        self.widths = widths

    def make(self, x: Tuple[float]) -> List[Content]:
        counts = self.vector_to_counts(x)
        return self.place_all(self.widths, counts)

    def vector_to_counts(self, x):
        return divide_space(x, len(self.placeables), 1)


def add_recursive(possibilities, idx, k, current, current_sum, N):
    if idx == k - 1:
        possibilities.append(current + [N - current_sum])
    else:
        for i in range(1, N - current_sum - (k - idx - 2)):
            add_recursive(possibilities, idx + 1, k, current + [i], current_sum + i, N)


class ColumnWidthOptimizer(ColumnOptimizer):
    available_width: int

    def __init__(self, k: int, placeables: List, outer: Rect, padding: int):
        super().__init__(k, placeables, outer, padding)
        self.available_width = outer.width - (k - 1) * padding

    def make_for_known_widths(self):
        even = tuple([1 / self.k] * self.k)
        return self.make(even)

    def brute_allocation(self, widths: Tuple[int]) -> (List[Content], float, List[int]):
        k = self.k
        N = len(self.placeables)

        possibilities = []
        add_recursive(possibilities, idx=0, k=k, current=[], current_sum=0, N=N)

        best = None, math.inf, None
        for alloc in possibilities:
            columns = self.place_all(widths, alloc)
            s = self.score(columns)
            if s < best[1]:
                best = columns, s, alloc

        LOGGER.debug("Brute force allocation widths=%s: %s -> %1.3f", widths, best[2], best[1])
        return best

    def make(self, x: Tuple[float]) -> Optional[List[Content]]:
        widths = self.vector_to_widths(x)

        if len(self.placeables) < 10:
            result, score, div = self.brute_allocation(widths)
            LOGGER.info("For widths=%s, best counts=%s -> %1.3f", widths, div, score)
            return result
        else:
            alloc = ColumnAllocationOptimizer(self.k, self.placeables, self.outer, widths, self.padding)
            result, (score, div) = alloc.run()
            if result is None:
                LOGGER.info("No solution for widths=%s", widths)
            else:
                LOGGER.info("For widths=%s, best counts=%s -> %1.3f", widths, alloc.vector_to_counts(div), score)
            return result

    def vector_to_widths(self, x):
        return divide_space(x, self.available_width, MIN_COLUMN_WIDTH, granularity=5)


def stack_together(bounds, columns, equal, padding, placeables):
    padding = int(padding)
    columns = int(columns)
    # Limit column count to child count -- no empty columns
    k = min(columns, len(placeables))
    if k < columns and equal:
        # Reduce width so we columsn will eb the right size in the reduced space
        bounds = bounds.resize(width=bounds.width * k // columns)

    if k == 1:
        LOGGER.info("Stacking %d items in single column: %s", len(placeables), bounds)
        return place_in_column(placeables, bounds, padding)
    columns_optimizer = ColumnWidthOptimizer(k, placeables, bounds, padding)
    equal = equal in {True, 'True', 'true', 'yes', 'y', '1'}
    if equal:
        LOGGER.info("Allocating %d items in %d equal columns: %s", len(placeables), k, bounds)
        columns = columns_optimizer.make_for_known_widths()
        return GroupContent(columns, bounds)
    else:
        LOGGER.info("Allocating %d items in %d unequal columns: %s", len(placeables), k, bounds)
        start = time.process_time()
        columns, (score, div) = columns_optimizer.run()
        widths = columns_optimizer.vector_to_widths(div)
        LOGGER.info("Completed in %1.2fs, widths=%s, score=%1.3f", time.process_time() - start, widths, score)
        return GroupContent(columns, bounds)


def _fits(together: Content, bounds: Rect) -> int:
    return together.actual.bottom <= bounds.bottom


def stack_in_columns(bounds: Rect, page: Rect, placeables: List, padding, options: dict, break_before:bool) -> List[GroupContent]:
    if break_before:
        on_next_page = stack_in_columns(page, page, placeables, padding, options, False)
        on_next_page[0].page_break_before = True
        return on_next_page

    equal = bool(options.get('equal', False))
    columns = int(options.get('columns', 1))

    LOGGER.info("Placing %d blocks in %d columns for bounds=%s, page=%s", len(placeables), columns, bounds, padding)
    k = min(int(columns), len(placeables))

    # If it fits completely, we are done
    all = stack_together(bounds, columns, equal, padding, placeables)
    LOGGER.debug("Binary Search: Trying to fit all (%d), result = %s", len(placeables), _fits(all, bounds))
    if _fits(all, bounds):
        return [all]

    # Try k items
    one = stack_together(bounds, columns, equal, padding, placeables[:k])
    if not _fits(one, bounds):
        # They don't fit, so this section will not fit on the page
        if bounds == page:
            # This section will not fit even on a full page
            warnings.warn("Even on an empty page, a section will not fit even one row of blocks")
            return [all]
        else:
            # Set the bounds to a full page and try that
            on_next_page = stack_in_columns(page, page, placeables, padding, options, False)
            on_next_page[0].page_break_before = True
            return on_next_page

    # Do binary search to see what fits. We know 'lo' fits and 'hi' does not

    lo = k
    lo_bottom = one.actual.bottom

    hi = len(placeables)
    hi_bottom = all.actual.bottom

    best = one

    while hi > lo + 1:
        # Find a good midpoint by linear approximation
        a = bounds.bottom - lo_bottom
        b = hi_bottom - bounds.bottom

        # Bias downwards slightly
        mid = int((a * hi + b * lo) / (a + b) - 0.5)
        if mid <= lo:
            mid = lo + 1
        if mid >= hi:
            mid = hi - 1

        trial = stack_together(bounds, columns, equal, padding, placeables[:mid])
        LOGGER.info("Binary Search: Trying %d of %d items, result = %s", mid, len(placeables), _fits(trial, bounds))
        if _fits(trial, bounds):
            lo = mid
            lo_bottom = trial.actual.bottom
            best = trial
        else:
            hi = mid
            hi_bottom = trial.actual.bottom

    assert sum(len(c.group) for c in best.group) == lo

    # Now try the rest on a new page, inserting the section we just made before it
    all = stack_in_columns(page, page, placeables[lo:], padding, options, False)
    all[0].page_break_before = True
    all.insert(0, best)

    return all