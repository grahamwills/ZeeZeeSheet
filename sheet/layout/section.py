from __future__ import annotations

import itertools
import statistics
from functools import lru_cache
from typing import List, Tuple

import numpy as np
from scipy import optimize
from scipy.optimize import Bounds

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

def score_extents(extents: List[Rect]) -> float:
    extents.sort(key=lambda e: e.bottom)
    dev = statistics.stdev(x.bottom for x in extents)

    # We want to allocate more room to the lowest, so we create a score to help that even if
    # it does not change the lowests right for this configuration
    factor = 0
    wt = 0
    for i, r in enumerate(extents):
        wt += i * i
        factor += i * i * r.width
    width_factor = factor / wt
    return dev - width_factor * 1e-4


class SectionLayout:
    items: List
    bounds: Rect
    padding: int


    def __init__(self, items: List, bounds: Rect, padding: int) -> None:
        self.padding = padding
        self.bounds = bounds
        self.items = items

    def place_in_single_column(self, children, bd: Rect) -> Rect:
        lowest = bd.top
        for child in children:
            available = Rect(top=lowest + self.padding, left=bd.left, right=bd.right, bottom=bd.bottom)
            placed = child.place(available)
            lowest = placed.bottom
        return Rect(top=bd.top, left=bd.left, right=bd.right, bottom=lowest)


    def place_in_columns(self, column_divisions, allocation_divisions) -> Tuple[float, Rect]:
        k = len(column_divisions) - 1
        n = len(self.items)

        extents = []
        for loc, idx in zip(column_divisions, allocation_divisions):
            b = Rect(left=loc[0], right=loc[1], top=self.bounds.top, bottom=self.bounds.bottom)
            items = self.items[idx[0]:idx[1]]
            rect = self.place_in_single_column(items, b)
            # LOGGER.debug("one column (%d ... %d), n=[%d:%d] -> %d", b.left, b.right, idx[0], idx[1], rect.bottom)
            extents.append(rect)

        lowest = max(e.bottom for e in extents)
        r = Rect(left=self.bounds.left, right=self.bounds.right, top=self.bounds.top, bottom=lowest)
        score = score_extents(extents)

        LOGGER.debug("optimize for (wid=%d, n=%d, cols=%d): %s : %s -> %1.3f: %s", self.bounds.width, n, k,
                     column_divisions, allocation_divisions, score, [e.bottom for e in extents])

        return score, r


    def allocate_items_to_fixed_columns(self, column_divisions) -> Tuple[float, Rect]:
        """ Brute force search for best solution"""

        k = len(column_divisions)
        n= len(self.items)

        results = [[i] for i in range(1,n+1)]

        for c in range(2,k):
            step = []
            for r in results:
                available = n - (k-c) - sum(r)
                for i in range(1, available+1):
                    step.append(r + [i])
            results = step

        # Last column is determined by others
        results = [ r + [n-sum(r)] for r in results]

        bscore, balloc = 9e99, None
        for a in results:
            asc = [sum(a[:i]) for i in range(0, k+1)]
            alloc = list(zip(asc, asc[1:]))
            score, rect = self.place_in_columns(column_divisions, alloc)
            if score < bscore:
                bscore, balloc = score, alloc


        return self.place_in_columns(column_divisions, balloc)

    def stack_vertically(self, columns):
        k = int(columns)
        if k == 1:
            return self.place_in_single_column(self.items, self.bounds)

        LOGGER.info("Stacking %d items vertically into %d columns: %s", len(self.items), k, self.bounds)


        def adapter_function(params):
            badness = param_badness(params[:k - 1]) + param_badness(params[k - 1:])
            if badness > 0:
                return 1e12 * (1 + badness * badness)

            cols, items = params_to_splits(params)
            return self.place_in_columns(cols, items)[0]

        def adapter_function_cols(params):
            badness = param_badness(params)
            if badness > 0:
                return 1e12 * (1 + badness * badness)

            cols = divisions(params, self.bounds.left, self.bounds.right, self.padding)
            return self.allocate_items_to_fixed_columns(cols)[0]


        def params_to_splits(params):
            cols = divisions(params[:k - 1], self.bounds.left, self.bounds.right, self.padding)
            items = divisions(params[k - 1:], 0, len(self.items) + 1, 0)
            return cols, items

        # params = [1.0 / k] * (2 * (k - 1))
        # initial = np.asarray(params)

        params = [1.0 / k] * (k - 1)
        initial = np.asarray(params)

        opt = optimize.minimize(adapter_function_cols, x0=initial, bounds=Bounds([0]*(k-1),[1]*(k-1)),method="powell")

        params = opt.x
        cols, items = params_to_splits(params)

        # Clear the cache so the operation does actually perform the placement

        cols = divisions(params, self.bounds.left, self.bounds.right, self.padding)
        return self.allocate_items_to_fixed_columns(cols)[1]


def stack_vertically(bounds: Rect, children: List, padding: int, columns: int = 1):
    return SectionLayout(children, bounds, padding).stack_vertically(columns)
