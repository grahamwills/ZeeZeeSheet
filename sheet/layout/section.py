from __future__ import annotations

from copy import copy
from functools import lru_cache
from typing import List, NamedTuple, Tuple

import numpy as np
from scipy import optimize

from common import Rect, configured_logger
from render import PlacedContent, PlacedGroupContent

LOGGER = configured_logger(__name__)


def score_placement(columns: [PlacedContent]) -> float:
    column_bounds = [c.bounds for c in columns]
    max_height = max(c.height for c in column_bounds)
    tot_area = sum(c.height*c.width for c in column_bounds)
    issues = sum(c.issues for c in columns)
    wasted_space = sum((max_height - r.height) * r.width for r in column_bounds)
    return 20 * issues + wasted_space ** 0.5


def divisions(fractions: [float], low: int, high: int, spacing: int) -> Tuple[Tuple[int]]:
    """ Divide up a space according to the fractions given """

    W = (high - low) - len(fractions) * spacing

    result = []
    left = low
    running = 0
    for i, v in enumerate(fractions):
        running += v
        right = low + round(running * W) + i * spacing
        result.append((left, right))
        left = right + spacing

    result.append((left, high))

    return tuple(result)


_MIN_WIDTH = 20


@lru_cache(maxsize=2048)
def estimate_single_size(layout: SectionLayout, index: int, width: int) -> PlacedContent:
    r = Rect(left=0, top=0, width=width, height=100000)
    place = layout.items[index].place(r)
    return place


def place_single(layout: SectionLayout, index: int, r: Rect) -> PlacedContent:
    return layout.items[index].place(r)


class LayoutDetails(NamedTuple):
    column_divisions: Tuple[(int, int)]
    allocation_divisions: Tuple[(int, int)]
    placed: PlacedContent
    score: float

    def __str__(self):
        a = " ".join("%d…%d" % s for s in self.column_divisions)
        b = " ".join("%d…%d" % s for s in self.allocation_divisions)
        return "cols=(%s) alloc=(%s) -> extent = %d (%1.2f)" % (a, b, self.placed.bounds.height, self.score)

    def height(self):
        return self.placed.bounds.height


class SectionLayout:
    items: List
    bounds: Rect
    padding: int

    def __init__(self, items: List, bounds: Rect, padding: int):
        self.padding = padding
        self.bounds = bounds
        self.items = items

    def place_in_single_column(self, start: int, end: int, bd: Rect, exact_placement) -> PlacedContent:
        current = bd.top
        all = []
        for i in range(start, end):
            available = Rect(top=current, left=bd.left, right=bd.right, bottom=bd.bottom)
            if exact_placement:
                p = place_single(self, i, available)
            else:
                p = copy(estimate_single_size(self, i, bd.width))
                p.bounds = p.bounds.move(dy=current)
            all.append(p)
            current = p.bounds.bottom + self.padding
        return PlacedGroupContent(all)

    def place_in_columns(self, column_divisions, allocation_divisions, exact_placement: bool) -> LayoutDetails:
        placed_columns = []
        for loc, idx in zip(column_divisions, allocation_divisions):
            b = Rect(left=loc[0], right=loc[1], top=self.bounds.top, bottom=self.bounds.bottom)
            placed = self.place_in_single_column(idx[0], idx[1], b, exact_placement)
            placed_columns.append(placed)

        score = score_placement(placed_columns)

        details = LayoutDetails(column_divisions, allocation_divisions, PlacedGroupContent(placed_columns), score)
        LOGGER.debug("Optimized Step: %s", details)
        return details

    def allocate_items_to_fixed_columns(self, column_divisions) -> LayoutDetails:
        """ Brute force search for best solution"""

        k = len(column_divisions)
        n = len(self.items)

        results = [[i] for i in range(1, n)]

        for c in range(2, k):
            step = []
            for r in results:
                available = n - (k - c) - sum(r)
                for i in range(1, available + 1):
                    step.append(r + [i])
            results = step

        # Last column is determined by others
        results = [r + [n - sum(r)] for r in results]

        best = None
        for a in results:
            asc = [sum(a[:i]) for i in range(0, k + 1)]
            alloc = list(zip(asc, asc[1:]))
            trial = self.place_in_columns(column_divisions, alloc, exact_placement=False)
            if not best or trial.score < best.score:
                best = trial

        return best

    def brute_allocate_items_to_fixed_columns(self, column_divisions) -> LayoutDetails:
        """ Brute force search for best solution"""

        k = len(column_divisions)
        n = len(self.items)

        results = [[i] for i in range(1, n + 1)]

        for c in range(2, k):
            step = []
            for r in results:
                available = n - (k - c) - sum(r)
                for i in range(1, available + 1):
                    step.append(r + [i])
            results = step

        # Last column is determined by others
        results = [r + [n - sum(r)] for r in results]

        best = None
        for a in results:
            asc = [sum(a[:i]) for i in range(0, k + 1)]
            alloc = list(zip(asc, asc[1:]))
            trial = self.place_in_columns(column_divisions, alloc, exact_placement=False)
            if not best or trial.score < best.score:
                best = trial

        return best

    def stack_in_columns(self, columns) -> PlacedContent:
        k = int(columns)
        n = len(self.items)
        if k == 1:
            return self.place_in_single_column(0, n, self.bounds, exact_placement=True)

        LOGGER.info("Stacking %d items vertically into %d columns: %s", n, k, self.bounds)

        optimal = dict()

        def adapter_function_cols(params):

            cols = divisions(params, self.bounds.left, self.bounds.right, self.padding)

            badness = sum(max(0, (_MIN_WIDTH - (pair[1] - pair[0]))) ** 2 for pair in cols)
            if badness > 0:
                return 1e12 * (1 + badness)

            details = self.allocate_items_to_fixed_columns(cols)
            optimal[details.column_divisions] = details.allocation_divisions
            return details.score

        opt = optimize.minimize(
                adapter_function_cols,
                x0=(np.asarray([1 / k] * (k - 1))),
                method="powell",
                bounds=[(0, 1)] * (k - 1),
                options={}
        )

        params = opt.x
        LOGGER.warning("Final layout = %s, cache = %s", opt.x, estimate_single_size.cache_info())

        cols = divisions(params, self.bounds.left, self.bounds.right, self.padding)
        return self.place_in_columns(cols, optimal[cols], exact_placement=True).placed


def stack_in_columns(bounds: Rect, children: List, padding: int, columns: int = 1) -> PlacedContent:
    return SectionLayout(children, bounds, padding).stack_in_columns(columns)
