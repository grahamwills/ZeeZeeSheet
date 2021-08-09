from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple

from sheet.common import Rect, configured_logger
from sheet.layout.optimizer import OptParams, OptimizeProblem
from sheet.placement.placed import PlacedContent, PlacedGroupContent, score_error

LOGGER = configured_logger(__name__)

_MIN_WIDTH = 20


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


class SectionLayout(OptimizeProblem):
    """
            Treat as an optimization problem where the first stage params are column sizes,
            second stage params are the allocations to each column

    """
    items: List
    bounds: Rect
    padding: int
    exact_placement: bool

    def __init__(self, items: List, bounds: Rect, padding: int):
        self.padding = padding
        self.bounds = bounds
        self.items = items
        self.exact_placement = True

    def score_placement(self, columns: [PlacedContent]) -> float:

        gp = PlacedGroupContent(columns, self.bounds)

        column_bounds = [c.actual for c in columns]
        max_height = max(c.height for c in column_bounds)
        min_height = min(c.height for c in column_bounds)

        diff = max_height - min_height

        error = gp.error()
        err = score_error(error)
        LOGGER.warn("Diff=%1.3f, err=%1.3f (%s)", diff, err, error)
        return diff + err

    def place_all_columns(self, column_sizes: Tuple[int], item_counts: Tuple[int]) -> [PlacedContent]:
        placed_columns = []
        sum_widths = 0
        sum_counts = 0
        # add the value for the last item
        all_cols = list(column_sizes) + [(self.available_width - sum(column_sizes))]
        all_counts = list(item_counts) + [len(self.items) - sum(item_counts)]

        for width, count in zip(all_cols, all_counts):
            left = self.bounds.left + sum_widths
            sum_widths += width
            right = self.bounds.left + sum_widths
            sum_widths += self.padding

            first = sum_counts
            sum_counts += count
            last = sum_counts

            b = Rect(left=left, right=right, top=self.bounds.top, bottom=self.bounds.bottom)
            placed = place_in_column(self.items[first:last], b, self.padding)
            placed_columns.append(placed)
        return placed_columns

    def score(self, column_sizes: OptParams, item_counts: OptParams) -> Optional[float]:
        placed_columns = self.place_all_columns(column_sizes.value, item_counts.value)
        return self.score_placement(placed_columns)

    def stage2parameters(self, stage1params: OptParams) -> Optional[OptParams]:
        n = len(self.items)
        k = len(stage1params) + 1
        m = n // k
        initial = [m] * (k - 1)

        return OptParams(tuple(initial), 1, n - k + 1)

    def validity_error(self, params: OptParams):
        """ >0 implies far away from desired """
        low = params.low
        high = params.high
        last = high + len(params) * low - sum(params.value)
        a = max(0, low - last)
        b = sum(max(0, low - p) + max(0, p - high) for p in params.value)
        return a + b

    def optimize_column_layout(self, k, equal: bool) -> PlacedContent:
        n = len(self.items)

        LOGGER.info("Stacking %d items  into %d columns: %s", n, k, self.bounds)

        self.available_width = self.bounds.width - (k - 1) * self.padding
        W = self.available_width // k
        initial = tuple([W] * (k - 1))
        if equal:
            column_bounds = OptParams(initial, W, W + 1)
        else:
            column_bounds = OptParams(initial, _MIN_WIDTH, self.available_width - (k - 1) * _MIN_WIDTH)

        LOGGER.info("Initial parameters = %s", column_bounds)
        self.exact_placement = False
        f, opt_col, opt_counts = self.run(column_bounds)
        self.exact_placement = True

        LOGGER.info("Finalizing placement cols=%s, alloc=%s, score=%f", opt_col, opt_counts, f)
        columns = self.place_all_columns(opt_col.value, opt_counts.value)
        return PlacedGroupContent(columns, self.bounds)


def place_in_column(placeables: List, bounds: Rect, padding: int) -> PlacedContent:
    current = bounds.top
    contents = []

    for item in placeables:
        available = Rect(top=current, left=bounds.left, right=bounds.right, bottom=bounds.bottom)
        p = item.place(available)
        contents.append(p)
        current = p.actual.bottom + padding

    return PlacedGroupContent(contents, bounds)


def stack_in_columns(bounds: Rect, placeables: List, padding: int, columns=1, equal=False) -> PlacedContent:
    # Limit column count to child count -- no empty columns
    k = min(int(columns), len(placeables))
    if k == 1:
        return place_in_column(placeables, bounds, padding)

    layout = SectionLayout(placeables, bounds, padding)
    equal = equal in {True, 'True', 'true', 'yes', 'y', '1'}
    return layout.optimize_column_layout(k, equal)
