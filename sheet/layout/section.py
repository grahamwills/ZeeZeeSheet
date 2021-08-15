from __future__ import annotations

import logging
import math
import statistics
from typing import List, NamedTuple, Optional, Tuple

from sheet.common import Rect, configured_logger
from sheet.optimize import Optimizer, divide_space
from sheet.placement.placed import PlacedContent, PlacedGroupContent

LOGGER = configured_logger(__name__)

MIN_COLUMN_WIDTH = 10


class LayoutDetails(NamedTuple):
    column_divisions: Tuple[(int, int)]
    allocation_divisions: Tuple[(int, int)]
    placed: PlacedContent
    score: float

    def __str__(self):
        a = " ".join("%d…%d" % s for s in self.column_divisions)
        b = " ".join("%d…%d" % s for s in self.allocation_divisions)
        return "cols=(%s) alloc=(%s) -> extent = %d (%1.2f)" % (a, b, self.placed.actual.height, self.score)

    def height(self):
        return self.placed.actual.height


def place_in_column(placeables: List, bounds: Rect, padding: int) -> Optional[PlacedGroupContent]:
    if bounds.width < MIN_COLUMN_WIDTH:
        LOGGER.warn("Column of width %f was smaller than the minimum of %d", bounds.width, MIN_COLUMN_WIDTH)
        return None

    current = bounds.top
    contents = []

    for place in placeables:
        available = Rect(top=current, left=bounds.left, right=bounds.right, bottom=bounds.bottom)
        p = place(available)
        contents.append(p)
        current = p.actual.bottom + padding

    return PlacedGroupContent(contents, bounds)


class ColumnOptimizer(Optimizer):
    placeables: List
    outer: Rect
    padding: int

    def __init__(self, k: int, placeables: List, outer: Rect, padding: int):
        super().__init__(k)
        self.placeables = placeables
        self.outer = outer
        self.padding = padding

    def score(self, columns: [PlacedGroupContent]) -> float:
        column_bounds = [c.actual for c in columns]
        max_height = max(c.height for c in column_bounds)

        stddev = statistics.stdev(c.height for c in column_bounds) / 10
        breaks = sum(c.error_from_breaks(30, 3) for c in columns)
        fit = sum(c.error_from_size(10, 0.01) for c in columns)
        var = sum(c.error_from_variance(0.1) for c in columns)

        if LOGGER.getEffectiveLevel() <= logging.FINE:
            for i, c in enumerate(columns):
                LOGGER.fine("[%d] n=%d width=%d height=%d breaks=%1.3f fit=%1.3f", i,
                            len(c.group), c.actual.width, c.actual.height,
                            c.error_from_breaks(30,3), c.error_from_size(10, 0.01))

        score = max_height + breaks + fit + stddev

        LOGGER.debug("Score: %1.3f -- max_ht=%1.1f, breaks=%1.3f, fit=%1.3f, stddev=%1.3f, var=%1.3f",
                     score, max_height, breaks, fit, stddev, var)
        return score

    def place_all(self, widths: Tuple[int], counts: Tuple[int]) -> List[PlacedContent]:
        LOGGER.debug("Placing with widths=%s, alloc=%s", widths, counts)
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

            b = self.outer.modify_horizontal(left=left, right=right)
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

    def make(self, x: Tuple[float]) -> List[PlacedContent]:
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

    def make_for_known_widths(self, widths):
        counts = [len(self.placeables) // self.k] * self.k
        counts[0] += len(self.placeables) - sum(counts)
        return self.place_all(widths, tuple(counts))

    def brute_allocation(self, widths: Tuple[int]) -> (List[PlacedContent], float, List[int]):
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


    def make(self, x: Tuple[float]) -> Optional[List[PlacedContent]]:
        try:
            widths = self.vector_to_widths(x)
        except ValueError:
            LOGGER.error("Not enough space for columns", exc_info=True)
            return None

        if len(self.placeables) < 10:
            result, score, div = self.brute_allocation(widths)
            LOGGER.info("For widths=%s, best counts=%s -> %1.3f", widths, div, score)
            return result
        else:
            alloc = ColumnAllocationOptimizer(self.k, self.placeables, self.outer, widths, self.padding)
            result, (score, div) = alloc.run()
            LOGGER.info("For widths=%s, best counts=%s -> %1.3f", widths, alloc.vector_to_counts(div), score)
            return result


    def vector_to_widths(self, x):
        return divide_space(x, self.available_width, MIN_COLUMN_WIDTH)


def stack_in_columns(bounds: Rect, placeables: List, padding: int, columns=1, equal=False) -> PlacedGroupContent:
    # Limit column count to child count -- no empty columns
    k = min(int(columns), len(placeables))
    if k == 1:
        LOGGER.info("Stacking %d items in single column: %s", len(placeables), bounds)
        return place_in_column(placeables, bounds, padding)

    columns_optimizer = ColumnWidthOptimizer(k, placeables, bounds, padding)
    equal = equal in {True, 'True', 'true', 'yes', 'y', '1'}
    if equal:
        LOGGER.info("Allocating %d items in %d equal columns: %s", len(placeables), k, bounds)
        widths = divide_space([1] * k, columns_optimizer.available_width, MIN_COLUMN_WIDTH)
        columns = columns_optimizer.make_for_known_widths(widths)
        return PlacedGroupContent(columns, bounds)
    else:
        LOGGER.info("Allocating %d items in %d unequal columns: %s", len(placeables), k, bounds)
        columns, (score, div) = columns_optimizer.run(method='nelder-meade')
        widths = columns_optimizer.vector_to_widths(div)
        LOGGER.info("Allocation: %s -> %1.3f", widths, score)
        columns_optimizer.score(columns)
        return PlacedGroupContent(columns, bounds)
