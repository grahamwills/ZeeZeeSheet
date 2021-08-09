""" Optimize a layout"""
import math
import time
from functools import lru_cache
from typing import Generic, Tuple, TypeVar

import numpy as np
import scipy.optimize

from sheet.common import configured_logger

T = TypeVar('T')

LOGGER = configured_logger(__name__)

BAD_PARAMS_FACTOR = 1e6


class Optimizer(Generic[T]):
    """
        Solve an optimization problem

        Fields
        ------

        name
            For debugging and logging

        k
            The number of dimensions (number of parameters)
            Parameters are in the range [0,1]

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

    def score_params(self, x: [float]) -> (float, T):
        """ scoring function, also returns created object """

        t = _params_invalid(x)
        if t:
            return BAD_PARAMS_FACTOR * (1 + t), None
        item = self.make(x)
        f = self.score(item) if item else BAD_PARAMS_FACTOR
        LOGGER.fine("[%s] %s -> %s -> %1.3f", self.name, _pretty(x), item, f)
        return f, item

    def run(self, x0: [float] = None, fast=True) -> (T, (float, [float])):
        """
            Run the optimization
            :param float[] x0: Optional starting value (defaults to 0.5s)
            :return: the optimal score, created item, and parameters
        """

        x0 = x0 or [0.5] * self.k

        if _params_invalid(x0) > 0:
            LOGGER.score_error("[%s] Initial parameters were invalid: %s", self.name, _pretty(x0))
            x0 = [0.5] * self.k

        cobyla_kwargs = {'method': 'COBYLA', 'constraints': {'type': 'ineq', 'fun': _params_invalid}}

        start = time.perf_counter()
        if fast:
            LOGGER.info("[%s] Solving with COBYLA, init=%s", self.name, _pretty(x0))
            solution = scipy.optimize.minimize(lambda x: _score(tuple(x), self), x0=np.asarray(x0), **cobyla_kwargs)
        else:
            LOGGER.info("[%s] Solving with basinhopping and COBYLA, init=%s", self.name, _pretty(x0))
            solution = scipy.optimize.basinhopping(lambda x: _score(tuple(x), self), x0=x0,
                                                   stepsize=1, niter=10, minimizer_kwargs=cobyla_kwargs)
        duration = time.perf_counter() - start

        if hasattr(solution, 'success') and not solution.success:
            LOGGER.info("[%s]: Failed in %1.2fs after %d evaluations: %s", self.name, duration, solution.nfev,
                        solution.message)
            results = None, (math.inf, None)
        else:
            f, item = self.score_params(solution.x)
            assert f == solution.fun
            results = item, (f, solution.x)
            LOGGER.info("[%s]: Success in %1.2fs using %d evaluations: %s -> %s -> %1.3f",
                        self.name, duration, solution.nfev, _pretty(solution.x), item, f)

        LOGGER.debug("Optimizer cache info = %s", str(_score.cache_info()).replace('CacheInfo', ''))
        _score.cache_clear()

        return results


def divide_space(x: [float], width: int) -> [int]:
    """ Utility to divide up space according to the parameters """
    t = width / sum(x)
    result = [round(v * t) for v in x]

    # Adjust for round-off error
    err = width - sum(result)
    result[0] += err
    return result


@lru_cache(maxsize=1024)
def _score(x: [float], optimizer: Optimizer) -> (float, T):
    return optimizer.score_params(x)


def _pretty(x: [float]) -> str:
    return '[' + ", ".join(["%1.3f" % v for v in x]) + ']'


def _params_invalid(x: Tuple[float]) -> float:
    return sum(max(0.0, -v) ** 2 + max(0.0, v - 1.0) ** 2 for v in x)
