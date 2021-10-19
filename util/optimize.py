""" Optimize a layout"""
import math
import time
from functools import lru_cache
from typing import Generic, Iterable, Tuple, TypeVar

import numpy as np
import scipy.optimize

from util import configured_logger

T = TypeVar('T')

LOGGER = configured_logger(__name__)

BAD_PARAMS_FACTOR = 1e12


class BadParametersError(RuntimeError):
    def __init__(self, message: str, badness: float) -> None:
        super().__init__(message)
        assert badness > 0
        self.badness = badness


class Optimizer(Generic[T]):
    """
        Solve an optimization problem

        The base idea is that we maintain a vector in [0,1]^(k-1) that must sum to < 1
        This generates a k-dimensional point where all the values sum to one
        That is then used to optimize allocation

        Fields
        ------

        name
            For debugging and logging

        k
            The number of dimensions (number of parameters-1)

    """
    name: str
    k: int

    def __init__(self, k: int, name: str = None):
        self.name = name or self.__class__.__name__
        self.k = k

    def make(self, x: [float]) -> T:
        """ Create an item for the given parameters """
        raise NotImplementedError()

    def score(self, t: T) -> float:
        """ Score the item """
        raise NotImplementedError()

    def score_params(self, p: Tuple[float]) -> (float, T):
        """ scoring function, also returns created object """

        try:
            x = params_to_x(p)
            item = self.make(x)
        except BadParametersError as err:
            return BAD_PARAMS_FACTOR * (1 + err.badness), None

        f = self.score(item) if item else BAD_PARAMS_FACTOR
        LOGGER.fine("[%s] %s -> %s -> %1.3f", self.name, _pretty(x), item, f)
        return f, item

    def run(self) -> (T, (float, [float])):
        x0 = np.asarray((1.0 / self.k,) * (self.k - 1))

        start = time.perf_counter()

        initial_simplex = self._unit_simplex()
        solution = scipy.optimize.minimize(lambda x: _score(tuple(x), self), method='Nelder-Mead', x0=x0,
                                           options={'initial_simplex': initial_simplex})
        duration = time.perf_counter() - start

        if hasattr(solution, 'success') and not solution.success:
            LOGGER.info("[%s]: Failed using nelder-mead in %1.2fs after %d evaluations: %s", self.name, duration,
                        solution.nfev, solution.message)
            results = None, (math.inf, None)
        else:
            f, item = self.score_params(tuple(solution.x))
            assert f == solution.fun
            results = item, (f, params_to_x(solution.x))
            LOGGER.info("[%s]: Solved using nelder-mead in %1.2fs with %d evaluations: %s -> %s -> %1.3f",
                        self.name, duration, solution.nfev, _pretty(solution.x), item, f)

        if hasattr(_score, 'cache_info'):
            LOGGER.fine("Optimizer cache info = %s", str(_score.cache_info()).replace('CacheInfo', ''))
            _score.cache_clear()

        return results

    def _unit_simplex(self):
        if self.k == 2:
            initial_simplex = [[0.4], [0.6]]
        elif self.k == 3:
            initial_simplex = [[0.3, 0.3], [0.4, 0.3], [0.3, 0.4]]
        else:
            lo = 1 / 1.2 / self.k
            initial_simplex = [[2 / 3 if j == i else lo for j in range(self.k - 1)] for i in range(self.k)]
        return initial_simplex


def divide_space(x: [float], total: int, minval: int, granularity=1) -> Tuple[int]:
    """
        Maps parameters to integer values that sum to a given total

        :param [float] x: non-negative parameters
        :type float total: the resulting values will sum to this
        :param float minval: A value of zero maps to this
        :granularity: divide space up in multiples of this
        :return: an array of integers, all at least 'min' size, that sum to the total
    """

    total = int(total)
    k = len(x)

    if minval * k > total:
        raise BadParametersError("Combination of minimum (%s) and total (%s) impossible for k=%d"
                                 % (minval, total, k), minval * k - total)
    if any(v < 0 for v in x):
        raise BadParametersError("Input data contained a negative value", -min(x))

    wt_total = sum(x)

    available = (total - k * minval) // granularity

    wt = 0
    result = [0] * k

    # Scan across columns (except the last)
    for i in range(0, k - 1):
        last = round(available * wt / wt_total)
        wt += x[i]
        this = round(available * wt / wt_total) - last

        result[i] = this * granularity + minval

    result[-1] = total - sum(result)
    assert result[-1] >= minval
    return tuple(result)


@lru_cache
def _score(x: [float], optimizer: Optimizer) -> float:
    return optimizer.score_params(x)[0]


def _pretty(x: [float]) -> str:
    return '[' + ", ".join(["%1.3f" % v for v in x]) + ']'


def params_to_x(params: Iterable[float]) -> Tuple[float]:
    total = sum(params)
    err = max(0.0, total - 1.0) + sum(max(0.0, -v) ** 2 for v in params)
    if err > 0:
        raise BadParametersError("parameter values lies outside bounds", err)
    else:
        return tuple([1.0 - total] + list(params))
