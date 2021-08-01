"""Items to be placed on a page"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, Image, Paragraph, Table
from reportlab.platypus.paragraph import _SplitWordEnd

from common import Rect
from model import Style
from pdf import PDF


@dataclass
class PlacedContent:
    bounds: Rect
    fit_error: float

    def __init__(self, bounds: Rect, fit_error: float = 0):
        self.fit_error = fit_error
        self.bounds = bounds.round()

    def add_fit_err(self, required: Rect):
        """ Add error based on how badly we fit"""
        dx = max(0, self.bounds.width - required.width)
        dy = max(0, self.bounds.height- required.height)
        self.fit_error += dx + dy

        dx = max(0, required.width - self.bounds.width)
        dy = max(0, - required.height - self.bounds.height)
        self.fit_error += (dx + dy)/50


    def move(self, dx=0, dy=0):
        self.bounds = self.bounds.move(dx=dx, dy=dy)


    def draw(self, pdf: PDF):
        pass


def _count_split_words(item):
    if isinstance(item, Tuple):
        return sum(isinstance(i, _SplitWordEnd) for i in item[1])
    else:
        return 0


def _count_wraps(f, any_wrap_bad=False):
    if isinstance(f, Table):
        rows = f._cellvalues
        flat_list = [item for row in rows for item in row]

        # For a single row table, any wrapping is bad
        single_line_table = len(rows) == 1
        return sum(_count_wraps(f, single_line_table) for f in flat_list)
    elif isinstance(f, (Image, str)):
        return 0
    elif isinstance(f, Paragraph):
        if not hasattr(f, 'blPara'):
            # Failed to place -- terrible
            return 100
        lines = f.blPara.lines
        if len(lines) < 2:
            return 0

        split_words = sum(_count_split_words(line) for line in lines)
        return split_words * 10 + int(any_wrap_bad)
    else:
        return _count_wraps(f[0], any_wrap_bad)


class PlacedFlowableContent(PlacedContent):
    flowable: Flowable

    def __init__(self, flowable: Flowable, bounds: Rect):
        error = 20 * _count_wraps(flowable)
        super().__init__(bounds, error)
        self.flowable = flowable

    def draw(self, pdf: PDF):
        pdf.draw_flowable(self.flowable, self.bounds)


class PlacedRectContent(PlacedContent):
    flowable: Flowable

    def __init__(self, bounds: Rect, style: Style, fill: bool, stroke: bool, rounded=0):
        super().__init__(bounds, 0)
        self.rounded = rounded
        self.stroke = stroke
        self.fill = fill
        self.style = style

    def draw(self, pdf: PDF):
        if self.fill:
            pdf.fill_rect(self.bounds, self.style, self.rounded)

        if self.stroke:
            pdf.stroke_rect(self.bounds, self.style, self.rounded)


class PlacedGroupContent(PlacedContent):
    group: Iterable[PlacedContent]

    def __init__(self, group: Iterable[PlacedContent]):
        unioned_bounds = Rect.union(p.bounds for p in group)
        unioned_issues = sum(p.fit_error for p in group)
        super().__init__(unioned_bounds, unioned_issues)
        self.group = group

    def draw(self, pdf: PDF):
        for p in self.group:
            p.draw(pdf)

    def move(self, dx=0, dy=0):
        super().move(dx=dx, dy=dy)
        for p in self.group:
            p.move(dx=dx, dy=dy)


def build_font_choices() -> [str]:
    user_fonts = []
    install_font('Baskerville', 'Baskerville', user_fonts)
    install_font('Droid', 'DroidSerif', user_fonts)
    install_font('Parisienne', 'Parisienne', user_fonts)
    install_font('PostNoBills', 'PostNoBills', user_fonts)
    install_font('Roboto', 'Roboto', user_fonts)
    install_font('Western', 'Carnevalee Freakshow', user_fonts)
    install_font('LoveYou', 'I Love What You Do', user_fonts)
    install_font('Typewriter', 'SpecialElite', user_fonts)
    install_font('StarJedi', 'Starjedi', user_fonts)
    install_font('28DaysLater', '28 Days Later', user_fonts)
    install_font('CaviarDreams', 'CaviarDreams', user_fonts)
    install_font('MotionPicture', 'MotionPicture', user_fonts)
    install_font('Adventure', 'Adventure', user_fonts)
    install_font('MrsMonster', 'mrsmonster', user_fonts)
    install_font('BackIssues', 'back-issues-bb', user_fonts)
    return sorted(base_fonts() + user_fonts)


def base_fonts():
    cv = canvas.Canvas(io.BytesIO())
    fonts = cv.getAvailableFonts()
    fonts.remove('ZapfDingbats')
    fonts.remove('Symbol')
    return fonts


def create_single_font(name, resource_name, default_font_name, user_fonts):
    loc = Path(__file__).parent.parent.joinpath('data/fonts/', resource_name + ".ttf")
    if loc.exists():
        pdfmetrics.registerFont(TTFont(name, loc))
        user_fonts.append(name)
        return name
    else:
        return default_font_name


def install_font(name, resource_name, user_fonts):
    try:
        pdfmetrics.getFont(name)
    except:
        regular = create_single_font(name, resource_name + "-Regular", None, user_fonts)
        bold = create_single_font(name + "-Bold", resource_name + "-Bold", regular, user_fonts)
        italic = create_single_font(name + "-Italic", resource_name + "-Italic", regular, user_fonts)
        bold_italic = create_single_font(name + "-BoldItalic", resource_name + "-BoldItalic", bold, user_fonts)
        pdfmetrics.registerFontFamily(name, normal=name, bold=bold, italic=italic, boldItalic=bold_italic)
