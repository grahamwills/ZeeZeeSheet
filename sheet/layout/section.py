from __future__ import annotations

from typing import List, NamedTuple, Tuple

from optimize import Optimizer, divide_space
from sheet.common import Rect, configured_logger
from sheet.placement.placed import PlacedContent, PlacedGroupContent

LOGGER = configured_logger(__name__)
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


def place_in_column(placeables: List, bounds: Rect, padding: int) -> PlacedContent:
    current = bounds.top
    contents = []

    for item in placeables:
        available = Rect(top=current, left=bounds.left, right=bounds.right, bottom=bounds.bottom)
        p = item.place(available)
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
        placement = score_placement(columns)
        return placement

    def place_all(self, widths: [int], counts: [int]) -> List[PlacedContent]:
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

            b = Rect(left=left, right=right, top=self.outer.top, bottom=self.outer.bottom)
            placed = place_in_column(self.placeables[first:last], b, self.padding)
            placed_columns.append(placed)
        return placed_columns


class ColumnAllocationOptimizer(ColumnOptimizer):
    widths: [int]

    def __init__(self, k: int, placeables: List, outer: Rect, widths: [int], padding: int):
        super().__init__(k, placeables, outer, padding)
        self.widths = widths


    def make(self, x: [float]) -> [PlacedContent]:
        counts = divide_space(x, len(self.placeables))
        if any(c==0 for c in counts):
            return None
        return self.place_all(self.widths, counts)


class ColumnWidthOptimizer(ColumnOptimizer):
    available_width: int

    def __init__(self, k: int, placeables: List, outer: Rect, padding: int):
        super().__init__(k, placeables, outer, padding)
        self.available_width = outer.width - (k - 1) * padding

    def make_for_known_widths(self, widths):
        counts = [len(self.placeables) // self.k] * self.k
        counts[0] += len(self.placeables) - sum(counts)
        return self.place_all(widths, counts)

    def make(self, x: [float]) -> [PlacedContent]:
        widths = divide_space(x, self.available_width)

        if len(self.placeables) == self.k:
            return self.place_all(widths, [1] * self.k)
        else:
            alloc = ColumnAllocationOptimizer(self.k, self.placeables, self.outer, widths, self.padding)
            result, _ = alloc.run()
            return result


def score_placement(columns: List[PlacedGroupContent]):
    column_bounds = [c.actual for c in columns]
    max_height = max(c.height for c in column_bounds)
    min_height = min(c.height for c in column_bounds)
    diff = max_height
    err = sum(c.error() for c in columns)

    for i, c in enumerate(columns):
        LOGGER.debug("[%d] n=%d width=%d height=%d err=%1.3f", i,
                     len(c.group), c.actual.width, c.actual.height, c.error())
    LOGGER.debug("Score: base=%1.3f, err=%1.3f", diff, err)
    return diff + err


def stack_in_columns(bounds: Rect, placeables: List, padding: int, columns=1, equal=False) -> PlacedContent:
    # Limit column count to child count -- no empty columns
    k = min(int(columns), len(placeables))
    if k == 1:
        LOGGER.info("Stacking %d items in single column: %s", len(placeables), bounds)
        return place_in_column(placeables, bounds, padding)

    columns_optimizer = ColumnWidthOptimizer(k, placeables, bounds, padding)
    equal = equal in {True, 'True', 'true', 'yes', 'y', '1'}
    if equal:
        LOGGER.info("Allocating %d items in %d equal columns: %s", len(placeables), k, bounds)
        widths = divide_space([1] * k, columns_optimizer.available_width)
        columns = columns_optimizer.make_for_known_widths(widths)
        return PlacedGroupContent(columns, bounds)
    else:
        LOGGER.info("Allocating %d items in %d unequal columns: %s", len(placeables), k, bounds)
        columns, _ = columns_optimizer.run()
        return PlacedGroupContent(columns, bounds)
