""" Optimize a layout"""
import abc
from functools import lru_cache
from typing import Callable, NamedTuple, Optional, Tuple

import numpy as np
from scipy import optimize

from sheet.common import configured_logger

LOGGER = configured_logger(__name__)


class OptParams(NamedTuple):
    value: Tuple[int]
    low: int
    high: int

    def __len__(self):
        return len(self.value)

    def __str__(self):
        return "[%d <= %s <= %d]" % (self.low, ",".join(str(x) for x in self.value), self.high)


class OptimizeProblem(abc.ABC):

    def score(self, x1: OptParams, x2: OptParams) -> float:
        """ score the problem"""
        raise NotImplementedError()

    def stage2parameters(self, stage1params: OptParams) -> Optional[OptParams]:
        """ Create second set of parameters from the first"""
        raise NotImplementedError()

    def validity_error(self, params: OptParams) -> float:
        """ How far past validity these params are"""
        raise NotImplementedError()

    def run(self, x1init: OptParams) -> (float, OptParams, OptParams):

        if self.validity_error(x1init) > 0:
            LOGGER.score_error("Initial parameters were invalid")
            raise ValueError("Initial parameters were invalid")

        LOGGER.info("Starting optimization using %s", x1init)

        best_combos = dict()

        def stage1func(params1: OptParams) -> float:
            f, params2 = self._stage2optimize(params1)
            best_combos[params1] = (f, params2)
            return f

        _, opt1 = self._minimize('stage-1', stage1func, x1init)

        LOGGER.debug("Optimizer cache info = %s", str(_score.cache_info()).replace('CacheInfo', ''))
        _score.cache_clear()

        if opt1:
            f, opt2 = best_combos[opt1]
            return f, opt1, opt2
        else:
            LOGGER.score_error("Optimization completely failed")
            return None, None, None

    def _stage2optimize(self, params1: OptParams) -> (float, OptParams):
        params2init = self.stage2parameters(params1)

        init_err = self.validity_error(params2init)
        if init_err > 0:
            LOGGER.info("[stage-2] out-of-bounds initial stage1 parameters %s: err = %s", params1, init_err)
            return 1e90 * (1 + init_err * init_err), None

        def stage2func(x2: OptParams) -> float:
            err = self.validity_error(x2)
            if err > 0:
                LOGGER.debug("Out-of-bounds stage2 parameters %s: err = %s", x2, err)
                return 1e90 * (1 + err * err)
            return _score(self, params1, x2)

        return self._minimize('stage-2', stage2func, params2init)

    def _minimize(self, name: str, func: Callable[[OptParams], float], initp: OptParams) -> (float, OptParams):

        if initp.low == initp.high:
            # Degenerate, so no need to do anything tricky
            LOGGER.info("[%s]: Degenerate bounds: %s", name, initp)
            return func(initp), initp

        LOGGER.info("[%s] initial parameters = %s", name, initp)

        def adapter(x: [float]) -> float:
            err = self.validity_error(_array2params(x, initp))
            if err > 0:
                LOGGER.debug("Out-of-bounds stage2 parameters %s: err = %s", x, err)
                return 1e90 * (1 + err * err)
            return func(_array2params(x, initp))

        def constraint(x: [float]) -> float:
            return self.validity_error(_array2params(x, initp))

        x0 = _params2array(initp)
        opt_results = optimize.minimize(adapter, x0=np.asarray(x0), method='COBYLA',
                                        constraints={'type': 'ineq', 'fun': constraint})

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
