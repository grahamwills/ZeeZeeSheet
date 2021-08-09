import math

import pytest

from optimize import Optimizer


def test_multiple_minima_d():
    opt = Optimizer(1, "Simple 1D")
    opt.score = lambda x: math.sin(x) + math.sin((10.0 / 3.0) * x)
    opt.make = lambda x: x[0] * 10 - 3

    optx, (optv, c) = opt.run(fast=False)
    assert optv == pytest.approx(opt.score(5.145735), 1e-3, 1e-3)
    assert optx == pytest.approx(5.145735, 1e-3, 1e-3)
    assert c[0] == pytest.approx((5.145735 + 3) / 10, 1e-3, 1e-3)
