""" Optimize a layout"""
import math
import time
from functools import lru_cache
from typing import Generic, Iterable, Tuple, TypeVar

import numpy as np
import scipy.optimize

from sheet.common import configured_logger

T = TypeVar('T')

LOGGER = configured_logger(__name__)

BAD_PARAMS_FACTOR = 1e12


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

        x, err = params_to_x(p)

        if err:
            return BAD_PARAMS_FACTOR * (1 + err), None
        try:
            item = self.make(x)
        except ValueError:
            return BAD_PARAMS_FACTOR, None

        f = self.score(item) if item else BAD_PARAMS_FACTOR
        LOGGER.fine("[%s] %s -> %s -> %1.3f", self.name, _pretty(x), item, f)
        return f, item

    def run(self, method='COBYLA') -> (T, (float, [float])):
        """
            Run the optimization
            :param method method: Layout method
            :return: the optimal score, created item, and parameters
        """

        x0 = (1.0 / self.k,) * (self.k - 1)
        kwargs = {'method': 'COBYLA', 'constraints': {'type': 'ineq', 'fun': lambda p: params_to_x(p)[1]}}
        LOGGER.info("[%s] Solving with %s, init=%s", self.name, method, _pretty(x0))

        start = time.perf_counter()

        if method == 'basinhopping':
            LOGGER.info("[%s] Solving with basinhopping, init=%s", self.name, _pretty(x0))
            solution = scipy.optimize.basinhopping(lambda x: _score(tuple(x), self), x0=x0, seed=13,
                                                   stepsize=1, niter=10)
        elif method == 'COBYLA':
            solution = scipy.optimize.minimize(lambda x: _score(tuple(x), self), x0=np.asarray(x0), **kwargs)
        elif method.lower() == 'nelder-mead':
            lo = 1 / 3 / self.k
            initial_simplex = [[2 / 3 if j == i else lo for j in range(self.k - 1)] for i in range(self.k)]
            kwargs = {'method':  'Nelder-Mead', 'bounds': [(0, 1)] * (self.k - 1),
                      'options': {'initial_simplex': initial_simplex}}
            solution = scipy.optimize.minimize(lambda x: _score(tuple(x), self), x0=np.asarray(x0), **kwargs)
        else:
            raise ValueError("Unknown optimize method '%s'",method)

        duration = time.perf_counter() - start

        if hasattr(solution, 'success') and not solution.success:
            LOGGER.info("[%s]: Failed in %1.2fs after %d evaluations: %s", self.name, duration, solution.nfev,
                        solution.message)
            results = None, (math.inf, None)
        else:
            f, item = self.score_params(tuple(solution.x))
            assert f == solution.fun
            results = item, (f, params_to_x(solution.x)[0])
            LOGGER.info("[%s]: Success in %1.2fs using %d evaluations: %s -> %s -> %1.3f",
                        self.name, duration, solution.nfev, _pretty(solution.x), item, f)

        if hasattr(_score, 'cache_info'):
            LOGGER.debug("Optimizer cache info = %s", str(_score.cache_info()).replace('CacheInfo', ''))
            _score.cache_clear()

        return results


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
        raise ValueError("Combination of minimum (%s) and total (%s) impossible for k=%d" % (minval, total, k))
    if any(v < 0 for v in x):
        raise ValueError("Input data contained a negative value")

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


def params_to_x(params: Iterable[float]) -> (Tuple[float], float):
    total = sum(params)
    err = max(0.0, total - 1.0) + sum(max(0.0, -v) ** 2 for v in params)
    if err > 0:
        return None, err

    return tuple([1.0 - total] + list(params)), 0
