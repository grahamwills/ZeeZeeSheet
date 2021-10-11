import functools
import math
import random
from copy import copy
from typing import Callable, List, Sequence

from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfgen.pathobject import PDFPathObject

from .common import Point


class LineModifier:

    def __init__(self, canvas: Canvas, method: str = 'rough', σ=1):
        """
            Class used to add a rough effect to drawing constructs
            :param str method:'rough' or 'teeth'
            :param float σ: The size of the roughness effect. The range (0, 3] is generally good
        """

        self.canvas = canvas
        self.method = method
        self.σ = σ / 2
        if method == 'teeth':
            self.step = self.σ * 10
        else:
            self.step = 10
        self.rand = random.Random()

    def rect_to_path(self, x, y, width, height, rounded=0, inset=False) -> PDFPathObject:
        p = self.canvas.beginPath()
        if inset:
            d = min(self.σ * 2, width / 4, height / 4)
        else:
            d = 0
        if rounded > 0:
            p.roundRect(x + d, y + d, width - 2 * d, height - 2 * d, rounded)
        else:
            p.moveTo(x + d, y + d)
            p.lineTo(x + width - d, y + d)
            p.lineTo(x + width - d, y + height - d)
            p.lineTo(x + d, y + height - d)
            p.close()
        return self.mangle(p)

    # noinspection PyProtectedMember
    def mangle(self, path: PDFPathObject) -> PDFPathObject:
        path._code = self._mangle_path_code(path._code)
        return path

    def roughen_path(self, path: PDFPathObject) -> PDFPathObject:
        return self.mangle(copy(path))

    def _mangle_path_code(self, path: Sequence[str]) -> List[str]:
        self._offset = Point(*self.canvas.absolutePosition(0, 0))
        result = []
        start = None
        last = None
        for term in path:
            parts = term.split()
            code = parts[-1]
            coords = [Point(float(parts[i]), float(parts[i + 1])) for i in range(0, len(parts) - 1, 2)]
            if code == 'm':
                if self.method == 'teeth':
                    start = last = coords[0]
                else:
                    start = last = self.jitter(coords[0])
                result.append(join(code, last))
            elif not coords and code not in {'h', 's', 'b', 'b*'}:
                # Drawing operations that do not close the path
                result.append(code)
            else:
                if code == 'l':
                    f = functools.partial(linear, last, coords[0])
                elif code in {'h', 's', 'b', 'b*'}:
                    # These all close the path
                    f = functools.partial(linear, last, start)
                elif code == 'c':
                    f = functools.partial(bezier, last, coords[0], coords[1], coords[2])
                elif code == 'v':
                    f = functools.partial(bezier, last, last, coords[0], coords[1])
                elif code == 'y':
                    f = functools.partial(bezier, last, coords[0], coords[1], coords[1])
                else:
                    raise ValueError("Unhandled PDF path code: '%s'" % code)

                if self.method == 'teeth':
                    pts, _ = self.interpolate(f, min_steps=1)
                    for pt in pts:
                        result += self.teeth(last, pt)
                        last = pt
                else:
                    pts, factor = self.interpolate(f)
                    self.σ /= factor
                    for pt in pts:
                        p = self.jitter(pt)
                        result.append(join('l', p))
                    last = pts[-1]
                    self.σ *= factor

                # Need to add close after the other interpolations
                if code == 'h':
                    result.append('h')

        return result

    def jitter(self, p: Point):
        # Randomize the seed based on the absolute location, so any new values at this location get the same amount
        self.rand.seed(round(p + self._offset))
        return Point(p[0] + self._noise(), p[1] + self._noise())

    def _noise(self):
        return min(2 * self.σ, max(-2 * self.σ, self.rand.gauss(0, self.σ)))

    def interpolate(self, func: Callable, min_steps=5) -> (Sequence[Point], float):
        v = [func(i / 5) for i in range(0, 6)]
        d = sum(abs(v[i] - v[i + 1]) for i in range(0, 5))
        if d < 1:
            return v[:-1:], 1
        steps = max(min_steps, round(d / self.step))

        # This is the factor by which our steps are smaller than expected
        # We use this to reduce the sigma value proportionally
        factor = steps * self.step / d

        return [func(i / steps) for i in range(1, steps + 1)], factor

    def teeth(self, a: Point, b: Point) -> List[str]:
        θ, d = (b - a).to_polar()
        c1 = 0.95 * a + 0.05 * b
        c2 = 0.55 * a + 0.45 * b
        c3 = 0.45 * a + 0.55 * b
        c4 = 0.05 * a + 0.95 * b
        v = Point.from_polar(θ - math.pi / 2, self.σ)
        return [
            join('l', c1 + v),
            join('l', c2 + v),
            join('l', c3 - v),
            join('l', c4 - v),
            join('l', b),
        ]


def join(code, *args):
    return ' '.join("{0:0.1f} {1:0.1f}".format(p.x, p.y) for p in args) + ' ' + code


def linear(a, b, t) -> Point:
    return a * (1 - t) + b * t


def bezier(a, c1, c2, b, t) -> Point:
    return (1 - t) ** 3 * a + 3 * t * (1 - t) * (1 - t) * c1 + 3 * t * t * (1 - t) * c2 + t ** 3 * b
