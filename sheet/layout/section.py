from __future__ import annotations

import statistics
from functools import lru_cache
from typing import List, NamedTuple, Tuple

import numpy as np
from scipy import optimize

from common import Rect, configured_logger

LOGGER = configured_logger(__name__)


def divisions(fractions: [float], low: int, high: int, spacing: int) -> Tuple[Tuple[int]]:
    """ Divide up a space according to the fractions given """

    W = (high - low) - len(fractions) * spacing

    result = []
    left = low
    running = 0
    for i, v in enumerate(fractions):
        running += v
        right = round(running * W) + i * spacing
        result.append((left, right))
        left = right + spacing

    result.append((left, high))

    return tuple(result)


def param_badness(params: np.ndarray) -> float:
    last = 1.0 - sum(params)
    return sum(max(0.0, v - 1) + max(0.0, -v) for v in list(params)) + sum(v == 0 for v in list(params)) * 1e-2 \
           + max(0.0, -last) + (last == 0) * 1e-2


@lru_cache(maxsize=2048)
def estimate_single_size(layout: SectionLayout, index: int, width: int) -> float:
    r = Rect(left=0, top=0, width=width, height=100000)
    return layout.items[index].place(r).bottom


def place_single(layout: SectionLayout, index: int, r: Rect) -> float:
    return layout.items[index].place(r).bottom


def score_extents(extents: [float], column_divs: [(int, int)]) -> float:
    dev = statistics.stdev(extents)

    pairs = list(zip(extents, column_divs))
    pairs.sort(key=lambda x: x[0])

    # We want to allocate more room to the lowest, so we create a score to help that even if
    # it does not change the lowests right for this configuration
    factor = 0
    wt = 0
    for i, r in enumerate(pairs):
        wt += i
        factor += i * (r[1][1] - r[1][0])
    width_factor = factor / wt
    return dev - width_factor * 1e-4


class LayoutDetails(NamedTuple):
    column_divisions: Tuple[(int, int)]
    allocation_divisions: Tuple[(int, int)]
    bounds: Rect
    score: float

    def __str__(self):
        a = " ".join("%d…%d" % s for s in self.column_divisions)
        b = " ".join("%d…%d" % s for s in self.allocation_divisions)
        return "cols=(%s) alloc=(%s) -> extent = %d (%1.2f)" % (a, b, self.bounds.height, self.score)


class SectionLayout:
    items: List
    bounds: Rect
    padding: int

    def __init__(self, items: List, bounds: Rect, padding: int):
        self.padding = padding
        self.bounds = bounds
        self.items = items

    def place_in_single_column(self, start: int, end: int, bd: Rect, exact_placement) -> float:
        lowest = bd.top - self.padding
        for i in range(start, end):
            if exact_placement:
                available = Rect(top=lowest + self.padding, left=bd.left, right=bd.right, bottom=bd.bottom)
                lowest = place_single(self, i, available)
            else:
                lowest += estimate_single_size(self, i, bd.width) + self.padding
        return lowest

    def place_in_columns(self, column_divisions, allocation_divisions, exact_placement: bool) -> LayoutDetails:
        extents = []
        for loc, idx in zip(column_divisions, allocation_divisions):
            b = Rect(left=loc[0], right=loc[1], top=self.bounds.top, bottom=self.bounds.bottom)
            ext = self.place_in_single_column(idx[0], idx[1], b, exact_placement)
            extents.append(ext)

        r = Rect(left=self.bounds.left, right=self.bounds.right, top=self.bounds.top, bottom=max(extents))
        score = score_extents(extents, column_divisions)

        details = LayoutDetails(column_divisions, allocation_divisions, r, score)
        LOGGER.debug("Optimized Step: %s", details)
        return details


    def allocate_items_to_fixed_columns(self, column_divisions) -> LayoutDetails:
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

        best = LayoutDetails((),(), Rect(left=0, top=0, width=1000, height=9e99), 9e99)
        for a in results:
            asc = [sum(a[:i]) for i in range(0, k + 1)]
            alloc = list(zip(asc, asc[1:]))
            trial = self.place_in_columns(column_divisions, alloc, exact_placement=False)
            if trial.bounds.height < best.bounds.height:
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

        best = LayoutDetails((),(), Rect(left=0, top=0, width=1000, height=9e99), 9e99)
        for a in results:
            asc = [sum(a[:i]) for i in range(0, k + 1)]
            alloc = list(zip(asc, asc[1:]))
            trial = self.place_in_columns(column_divisions, alloc, exact_placement=False)
            if trial.score < best.score:
                best = trial

        return best


    def stack_in_columns(self, columns):
        k = int(columns)
        n = len(self.items)
        if k == 1:
            height = self.place_in_single_column(0, n, self.bounds, exact_placement=True)
            b = self.bounds
            return Rect(left=b.left, right=b.right, top=b.top, height=height)

        LOGGER.info("Stacking %d items vertically into %d columns: %s", n, k, self.bounds)

        optimal = dict()

        def adapter_function_cols(params):
            badness = param_badness(params)
            if badness > 0:
                return 1e12 * (1 + badness * badness)

            cols = divisions(params, self.bounds.left, self.bounds.right, self.padding)
            details = self.allocate_items_to_fixed_columns(cols)
            optimal[details.column_divisions] = details.allocation_divisions
            return details.score


        opt = optimize.minimize(
                adapter_function_cols,
                x0=(np.asarray([1 / k] * (k - 1))),
                method="powell",
                bounds=[(0,1)] * (k-1),
                options={}
        )

        params = opt.x
        LOGGER.debug("Final layout = %s, cache = %s", opt.x, estimate_single_size.cache_info())

        cols = divisions(params, self.bounds.left, self.bounds.right, self.padding)
        return self.place_in_columns(cols, optimal[cols], exact_placement=True).bounds


def stack_in_columns(bounds: Rect, children: List, padding: int, columns: int = 1):
    return SectionLayout(children, bounds, padding).stack_in_columns(columns)
