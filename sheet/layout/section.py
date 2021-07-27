from __future__ import annotations

from typing import List

import numpy as np
from scipy import optimize
from scipy.optimize import Bounds

from common import Rect, configured_logger

LOGGER = configured_logger(__name__)


def _single_stack(bd: Rect, children, padding: int) -> Rect:
    lowest = bd.top
    for child in children:
        available = Rect(top=lowest + padding, left=bd.left, right=bd.right, bottom=bd.bottom)
        placed = child.place(available)
        lowest = placed.bottom
    return Rect(top=bd.top, left=bd.left, right=bd.right, bottom=lowest)





E = 0.1


def _stack_vertical(bounds: Rect, children, padding: int, k, array: np.ndarray) -> Rect:
    params = list(array)
    column_divisions = params[:k - 1]
    col_w_fraction = column_divisions + [1.0 - sum(column_divisions)]

    num_divisions = params[k - 1:]
    n_fraction = num_divisions + [1.0 - sum(num_divisions)]

    # Sum up any badness and return
    badness = 0
    for v in col_w_fraction + n_fraction:
        if v < E:
            badness += (v - E) ** 2
        if v > 1 - E:
            badness += (v - (1 - E)) ** 2
    if badness > 0:
        LOGGER.debug("Parameters outside bounds: cols = %s, n = %s", col_w_fraction, n_fraction)
        return Rect(left=bounds.left, right=bounds.right, top=bounds.top, bottom=10000 * (1 + badness))

    lowest = bounds.top
    left = bounds.left
    f_first = 0
    n = len(children)
    for c in range(0, k):
        right = left + bounds.width * col_w_fraction[c]
        column_bounds = Rect(left=left, right=right, top=bounds.top, bottom=bounds.bottom)

        f_last = f_first + n_fraction[c]
        a = round(n * f_first)
        b = round(n * f_last)
        column_children = children[a:b]

        LOGGER.debug("Column %d: Placing [%d:%d]  into %s", c, a, b, column_bounds)
        column_result = _single_stack(column_bounds, column_children, padding)
        lowest = max(lowest, column_result.bottom)

        # Set up for next column
        left = right
        f_first = f_last

    print(array, '->', lowest)

    return Rect(left=bounds.left, right=bounds.right, top=bounds.top, bottom=lowest)


def stack_vertically(bounds, children, padding, columns=1):
    k = int(columns)
    if k == 1:
        LOGGER.info("Simple stacking of %d items", len(children))
        return _single_stack(bounds, children, padding)

    LOGGER.info("Stacking %d items vertically into %d columns: %s", len(children), k, bounds)


    # First k-1 parameters determine the column widths, second k-1 param determines allocation of items to columns
    params = [1.0 / k] * (2 * (k - 1))

    xtol = 1/bounds.width
    ftol = 1/bounds.height

    def target_func(params):
        return _stack_vertical(bounds, children, padding, k, params).bottom

    param_bounds = Bounds([E] * len(params), [1 - E] * len(params), keep_feasible=True)
    opt = optimize.minimize(target_func, x0=np.asarray(params), bounds=param_bounds, method="powell",
                            options={'xtol':xtol, 'ftol':0.0001})
    result = opt.x
    return _stack_vertical(bounds, children, padding, k, result)
