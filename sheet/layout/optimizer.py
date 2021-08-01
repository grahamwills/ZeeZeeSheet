""" Optimize a layout"""
import abc
from functools import lru_cache
from typing import Callable, NamedTuple, Optional, Tuple

import numpy as np
from scipy import optimize

from common import configured_logger

LOGGER = configured_logger(__name__)


class OptParams(NamedTuple):
    value: Tuple[int]
    low: int
    high: int

    def __len__(self):
        return len(self.value)

    def __str__(self):
        return "{(%s) bounds=(%d:%d)}" % (",".join(str(x) for x in self.value), self.low, self.high)

class OptimizeProblem(abc.ABC):

    def score(self, x1: Tuple[int], x2: Tuple[int]) -> float:
        """ score the problem"""
        raise NotImplementedError()

    def stage2parameters(self, stage1params: Tuple[int]) -> Optional[OptParams]:
        """ Create second set of parameters from the first"""
        raise NotImplementedError()

    def validity_error(self, params: OptParams):
        """ How far past valididyt these params are"""
        raise NotImplementedError()

    def run(self, x1init: OptParams) -> (float, OptParams, OptParams):
        LOGGER.info("Starting optimization using %s", x1init)

        best_combos = dict()

        def stage1func(params1: Tuple[int]) -> float:
            f, params2 = self._stage2optimize(params1)
            best_combos[params1] = (f, params2)
            return f

        _, opt1 = self._minimize('stage-1', stage1func, x1init)

        LOGGER.debug("Optimizer cache info = %s", str(_score.cache_info()).replace('CacheInfo', ''))
        _score.cache_clear()

        if opt1:
            f, opt2 = best_combos[opt1.value]
            return f, opt1, opt2
        else:
            LOGGER.error("Optimization completely failed")
            return None, None, None

    def _stage2optimize(self, params1: Tuple[int]) -> (float, OptParams):
        params2init = self.stage2parameters(params1)

        err = self.validity_error(params2init)
        if err > 0:
            LOGGER.info("[stage-2] out-of-bounds initial stage1 parameters %s: err = %s", params1, err)
            return 1e6 * (1 + err * err), None

        def stage2func(x2: Tuple[int]) -> float:
            err = self.validity_error(OptParams(x2, params2init.low, params2init.high))
            if err > 0:
                LOGGER.debug("Out-of-bounds stage2 parameters %s: err = %s", x2, err)
                return 1e6 * (1 + err * err)
            return _score(self, params1, x2)

        return self._minimize('stage-2', stage2func, params2init)

    def _minimize(self, name: str, func: Callable[[Tuple[int]], float], initp: OptParams) -> (float, OptParams):

        if initp.low == initp.high:
            # Degenerate, so no need to do anything tricky
            LOGGER.info("[%s]: Degenerate bounds: %s", name, initp)
            return func(initp.value), initp

        LOGGER.info("[%s] initial parameters = %s", name, initp)

        def adapter(x: [float]) -> float:
            return func(_array2tuple(x, initp))

        x0 = _params2array(initp)
        opt_results = optimize.minimize(adapter, x0=np.asarray(x0), method='COBYLA', bounds=None)

        if opt_results.success:
            LOGGER.info("[%s]: Success using %d evaluation", name, opt_results.nfev)
            return float(opt_results.fun), _array2params(opt_results.x, initp)
        else:
            LOGGER.info("[%s]: Failed after using %d evaluation: %s", name, opt_results.nfev, opt_results.message)
            return None, None

    def __hash__(self):
        return id(self)


@lru_cache(maxsize=1024)
def _score(optimizer, params1, params2) -> float:
    return optimizer.score(params1, params2)


def _from_fraction(x: float, a: int, b: int) -> int:
    if a == b:
        return a
    if a < b:
        return round(a + x * (b - a))
    raise ValueError("Negative width bounds: %d, %d", a, b)


def _to_fraction(x: int, a: int, b: int) -> float:
    if a == b:
        return 0.5
    if a < b:
        return (x - a) / (b - a)
    raise ValueError("Negative width bounds: %d, %d", a, b)


def _params2array(x: OptParams) -> [float]:
    return [_to_fraction(v, x.low, x.high) for v in x.value]


def _array2tuple(x: [float], base: OptParams) -> Tuple[int]:
    return tuple(_from_fraction(v, base.low, base.high) for v in x)


def _array2params(x: [float], base: OptParams) -> OptParams:
    return OptParams(_array2tuple(x, base), base.low, base.high)
