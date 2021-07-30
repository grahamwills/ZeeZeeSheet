""" Optimize a layout"""
import abc
from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np
from scipy import optimize

from common import configured_logger

LOGGER = configured_logger(__name__)


@dataclass
class OptParams:
    value: Tuple[int]
    bounds: Tuple[(int, int)]

    def __len__(self):
        return len(self.value)


class OptProblem(abc.ABC):

    def score(self, x1: Tuple[int], x2: Tuple[int]) -> float:
        """ score the problem"""
        raise NotImplementedError()

    def stage2parameters(self, stage1params: Tuple[int]) -> OptParams:
        """ Create second set of parameters from the first"""
        raise NotImplementedError()

    def run(self, x1init: OptParams) -> (float, OptParams, OptParams):
        LOGGER.info("Starting optimization using %s", x1init)

        best_combos = dict()

        def stage1func(params1: Tuple[int]) -> float:
            f, params2 = self._stage2optimize(params1)
            if params2:
                best_combos[params1] = (f, params2)
                return f
            else:
                return 9e99

        _, opt1 = self._minimize('stage1', stage1func, x1init)

        if opt1:
            f, opt2 = best_combos[opt1]
            return f, opt1, opt2
        else:
            LOGGER.error("Optimization completely failed")
            return None, None, None

    def _stage2optimize(self, params1: Tuple[int]) -> (float, OptParams):

        params2init = self.stage2parameters(params1)

        def stage2func(x: Tuple[int]) -> float:
            params2 = _array2tuple(x, params2init)
            return self.score(params1, params2)

        return self._minimize('stage2', stage2func, params2init)

    def _minimize(self, name: str, func: Callable[[Tuple[int]], float], x_init: OptParams):

        x0 = _params2array(x_init)
        bounds = [(0.0, 1.0)] * len(x_init)

        def adapter(x: [float]) -> float:
            return func(_array2tuple(x, x_init))

        opt_results = optimize.minimize(adapter, x0=np.asarray(x0), method="powell", bounds=bounds)

        if opt_results.success:
            LOGGER.info("[%s]: Success after %d iterations", name, opt_results.nit)
            return opt_results.fun, _array2params(opt_results.x, x_init)
        else:
            LOGGER.info("[%s]: Success after %d iterations: %s", name, opt_results.nit, opt_results.message)
            return None, None


def _params2array(x: OptParams) -> [float]:
    return [(x.value[i] - x.bounds[i][0]) / (x.bounds[i][1] - x.bounds[i][0]) for i in range(len(x))]


def _array2tuple(x: [float], base: OptParams) -> Tuple[int]:
    return tuple(round(base.bounds[i][0] + x[i] * (base.bounds[i][1] - base.bounds[i][0])) for i in range(len(x)))


def _array2params(x: [float], base: OptParams) -> OptParams:
    return OptParams(_array2tuple(x, base), base.bounds)
