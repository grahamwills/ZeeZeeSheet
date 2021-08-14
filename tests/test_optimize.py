import math

import pytest

from sheet.optimize import Optimizer, divide_space


def test_multiple_minima_d():
    opt = Optimizer(2, "Simple 1D")
    opt.score = lambda x: math.sin(x) + math.sin((10.0 / 3.0) * x)
    opt.make = lambda x: x[0] * 10 - 3

    optx, (optv, c) = opt.run(method='basinhopping')
    assert optv == pytest.approx(opt.score(5.145735), 1e-3, 1e-3)
    assert optx == pytest.approx(5.145735, 1e-3, 1e-3)


@pytest.mark.parametrize("input,total,min,output", [
    ([1, 1, 1, 1], 4, 1, (1, 1, 1, 1)),
    ([20, 20, 20, 20], 4, 1, (1, 1, 1, 1)),
    ([1, 1, 1, 1], 36, 1, (9, 9, 9, 9)),
    ([1], 36, 1, (36,)),
    ([100, 200], 36, 1, (13, 23)),
    ([0, 1], 36, 3, (3, 33)),
    ([1, 1, 1, 1], 7, 1, (2, 2, 2, 1)),
    ([1, 1, 10, 1], 7, 1, (2, 1, 3, 1)),
    ([0, 10, 10.001], 8, 1, (2, 3, 3,)),
    ([0, 0, 0], 8, 1, (3, 3, 2,)),
], ids=str)
def test_divide_space(input, total, min, output):
    assert divide_space(input, total, min) == output


def test_divide_space_errors():
    with pytest.raises(ValueError) as excinfo:
        divide_space([1, 1, 1], 10, 4)
    assert "Combination of minimum" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        divide_space([1, -1, 1], 10, 0)
    assert "negative value" in str(excinfo.value)
