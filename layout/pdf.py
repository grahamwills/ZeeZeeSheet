import contextlib
import io
from collections import defaultdict, namedtuple
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Optional

import reportlab
import reportlab.lib.colors
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.pdfgen.pathobject import PDFPathObject
from reportlab.platypus import Flowable
from reportlab.platypus.paragraph import _SplitFrag, _SplitWord

from structure.model import Run
from structure.style import DEFAULT, Style
from util.common import Rect, configured_logger
from util.roughen import LineModifier

LOGGER = configured_logger(__name__)

_CHECKED_BOX = '../resources/images/checked.png'
_UNCHECKED_BOX = '../resources/images/unchecked.png'
_TEXTFIELD = '../resources/images/blank.png'
_LEADING_MAP = defaultdict(lambda: 1.2)
_MULTIPLIER_MAP = defaultdict(lambda: 1)

DrawMethod = namedtuple('DrawMethod', 'fill stroke')


class PDF(canvas.Canvas):
    FILL = DrawMethod(True, False)
    STROKE = DrawMethod(False, True)
    BOTH = DrawMethod(True, True)

    def __init__(self, output_file: Path, pagesize: (int, int), debug: bool = False) -> None:
        super().__init__(str(output_file.absolute()), pagesize=pagesize)
        self.setLineJoin(1)
        self.setLineCap(1)
        fonts = install_fonts()


        LOGGER.info("Installed fonts = %s", fonts)
        # self._fonts_for_documentation(fonts)
        self.base_dir = output_file.parent
        self.page_height = int(pagesize[1])
        self.debug = debug
        self._name_index = 0
        self.style = None

    def _fonts_for_documentation(self, fonts):
        fonts = [f for f in fonts if 'talic' not in f.lower() and 'bold' not in f.lower()]
        for i in fonts:
            print('font_sample_{0}\n\tinherit=font_sample_base family={0}\n'.format(i))
        sample = dedent(
                """
                    .. block:: style=font_sample_{0}

                    {0}
                     - The five boxing wizards jump quickly | *Pack my box with five dozen liquor jugs* | **How 
                     vexingly quick daft zebras jump**
                """
        ).strip()
        for i in fonts:
            print(sample.format(i))
            print()

    @contextlib.contextmanager
    def using_style(self, style: Style):
        old_style = self.style
        self.style = style
        yield self
        self.style = old_style

    def drawImage(self, image, x, y, width=None, height=None, mask=None, preserveAspectRatio=False, anchor='c',
                  anchorAtXY=False, showBoundary=False):
        fileName = image.fileName if hasattr(image, 'fileName') else str(image)
        if fileName == _UNCHECKED_BOX:
            return self._add_checkbox(x, y, width, height, False)
        elif fileName == _CHECKED_BOX:
            return self._add_checkbox(x, y, width, height, True)
        elif fileName == _TEXTFIELD:
            return self._add_textfield(x, y, width, height)
        else:
            self.saveState()
            roughener = self._make_roughener()
            if roughener:
                clip = roughener.rect_to_path(x, y, width, height, inset=True)
                self.clipPath(clip, 0, 0)
            tup = super().drawImage(image, x, y, width, height, mask, preserveAspectRatio, anchor, anchorAtXY,
                                    showBoundary)
            self.restoreState()
            return tup

    def _add_checkbox(self, rx, ry, width, height, state) -> (int, int):
        x, y = self.absolutePosition(rx, ry)
        self._name_index += 1
        name = "f%d" % self._name_index
        LOGGER.debug("Adding checkbox name='%s' with state=%s ", name, state)
        self.acroForm.checkbox(name=name, x=x - 0.5, y=y, size=min(width, height) + 1,
                               fillColor=reportlab.lib.colors.Color(1, 1, 1),
                               buttonStyle='cross', borderWidth=0.5, checked=state)
        return width, height

    def _add_textfield(self, rx, ry, width, height) -> (int, int):
        style = self.style
        x, y = self.absolutePosition(rx, ry)
        self._name_index += 1
        name = "f%d" % self._name_index
        LOGGER.debug("Adding text field name='%s'", name)
        fname = 'Helvetica'
        if 'Times' in style.fontName:
            fname = 'Times-Roman'

        self.acroForm.textfield(name=name, x=x-1, y=y - 1, relative=False, width=width, height=height,
                                fontName=fname, fontSize=style.fontSize, textColor=style.textColor,
                                fillColor=reportlab.lib.colors.HexColor(0xFFFFFF00, hasAlpha=True),
                                borderWidth=0.25, borderColor=reportlab.lib.colors.HexColor(0xA0A0A010, hasAlpha=True))

    def draw_rect(self, r: Rect, method: DrawMethod, rounded=None):
        method = self._set_drawing_styles(method)
        roughener = self._make_roughener()
        top = self.page_height - r.bottom

        if rounded is None:
            if self.style.rounded is not None:
                rounded = self.style.rounded
            else:
                rounded = 0

        if roughener:
            path = roughener.rect_to_path(r.left, top, r.width, r.height, rounded=rounded)
            self.drawPath(path, fill=method.fill, stroke=method.stroke)
        elif rounded > 0:
            self.roundRect(r.left, top, r.width, r.height, rounded, fill=method.fill, stroke=method.stroke)
        else:
            self.rect(r.left, top, r.width, r.height, fill=method.fill, stroke=method.stroke)

    def draw_path(self, path: PDFPathObject, x, y, method: DrawMethod):
        method, self._set_drawing_styles(method)
        roughener = self._make_roughener()
        if roughener:
            path = roughener.roughen_path(path)
        self.saveState()
        self.transform(1, 0, 0, -1, x, self.page_height - y)
        self.drawPath(path, fill=method.fill, stroke=method.stroke)
        self.restoreState()

    def _set_drawing_styles(self, method: DrawMethod) -> DrawMethod:
        style = self.style or DEFAULT
        if method.fill and style.background:
            self.setFillColorRGB(*style.background.rgb, alpha=style.opacity)
            self.setLineWidth(0)
            fill = True
        else:
            fill = False
        if method.stroke and style.borderColor and style.borderWidth:
            self.setStrokeColorRGB(*style.borderColor.rgb, alpha=style.opacity)
            self.setLineWidth(style.borderWidth)
            stroke = True
        else:
            stroke = False
        return DrawMethod(fill, stroke)

    def draw_flowable(self, flowable: Flowable, bounds):
        flowable.drawOn(self, bounds.left, self.page_height - bounds.bottom)

    def paragraph_style_for(self, run: Run) -> Style:
        styles = [e.style for e in run.items]
        style = styles[0]
        max_size = max(s.size for s in styles)
        if max_size != style.size:
            style = style.clone(size=max_size)
        return style

    def paragraph_leading_for(self, run: Run) -> float:
        styles = (e.style for e in run.items)
        max_leading = max(self.leading_for(s) for s in styles)
        return max_leading

    def descender(self, style) -> float:
        try:
            return -pdfmetrics.getDescent(style.font, style.size)
        except:
            return -pdfmetrics.getDescent(style.fontName, style.fontSize)

    def leading_for(self, item) -> float:
        try:
            return _LEADING_MAP[item.font.lower()] * item.size
        except AttributeError:
            return _LEADING_MAP[item.fontName.lower()] * item.fontSize

    def __hash__(self):
        return id(self)

    def _make_roughener(self, style=None) -> Optional[LineModifier]:
        style = style or self.style
        if style:
            if style.roughness:
                return LineModifier(self, 'rough', style.roughness)
            if style.teeth:
                return LineModifier(self, 'teeth', style.teeth)
        return None

    def rect_to_path(self, b: Rect, style: Style):
        if style and style.rounded is not None:
            rounded = style.rounded
        else:
            rounded = 0

        roughener = self._make_roughener(style)
        if roughener:
            return roughener.rect_to_path(b.left, b.top, b.width, b.height, rounded=rounded)
        path = self.beginPath()
        if rounded:
            path.roundRect(b.left, b.top, b.width, b.height, rounded)
        else:
            path.rect(b.left, b.top, b.width, b.height)
        path.close()
        return path


def install_fonts() -> [str]:
    user_fonts = []
    install_font('Gotham', 'Gotham', user_fonts, multiplier=0.9)
    install_font('Baskerville', 'Baskerville', user_fonts)

    install_font('Adventure', 'Adventure', user_fonts, leading=1.0)
    install_font('Steampunk', 'Zalora', user_fonts, leading=1.1, multiplier=0.95)
    install_font('Steamship', 'Starship', user_fonts, leading=1.15)
    install_font('LoveYou', 'I Love What You Do', user_fonts, leading=1.1, multiplier=1.2)
    install_font('Comics', 'back-issues-bb', user_fonts, multiplier=0.9)
    install_font('Tech', 'oceanicdrift', user_fonts, leading=0.8, multiplier=1.2)
    install_font('Space', 'Starjedi', user_fonts,  leading=1.1)
    install_font('Western', 'Carnevalee Freakshow', user_fonts, leading=1.0, multiplier=1.15)
    install_font('ArtDeco', 'CaviarDreams', user_fonts, leading=1.1)
    install_font('Radioactive', '28 Days Later', user_fonts, leading=1.1)
    install_font('Typewriter', 'SpecialElite', user_fonts)
    install_font('Monster', 'mrsmonster', user_fonts, leading=1.1)
    install_font('Script', 'Parisienne', user_fonts, leading=1.1)
    install_font('Medieval', 'Seagram', user_fonts, leading=1.25, multiplier=1.1)

    install_font('MotionPicture', 'MotionPicture', user_fonts, leading=1.0, multiplier=1.2)
    install_font('Symbola', 'Symbola', user_fonts)

    # Leading adjustments to standard fonts
    _LEADING_MAP['courier'] = 1.1

    return sorted(base_fonts() + user_fonts)


def base_fonts():
    cv = canvas.Canvas(io.BytesIO())
    fonts = cv.getAvailableFonts()
    fonts.remove('ZapfDingbats')
    fonts.remove('Symbol')
    return fonts


def create_single_font(name, resource_name, default_font_name, user_fonts):
    loc = Path(__file__).parent.parent.joinpath('resources/fonts/', resource_name + ".ttf")
    if loc.exists():
        font = TTFont(name, loc)
        pdfmetrics.registerFont(font)
        user_fonts.append(name)
        return name
    else:
        return default_font_name


def install_font(name, resource_name, user_fonts, leading: float = None, multiplier=None):
    try:
        pdfmetrics.getFont(name)
    except:
        regular = create_single_font(name, resource_name + "-Regular", None, user_fonts)
        bold = create_single_font(name + "-Bold", resource_name + "-Bold", regular, user_fonts)
        italic = create_single_font(name + "-Italic", resource_name + "-Italic", regular, user_fonts)
        bold_italic = create_single_font(name + "-BoldItalic", resource_name + "-BoldItalic", bold, user_fonts)
        pdfmetrics.registerFontFamily(name, normal=name, bold=bold, italic=italic, boldItalic=bold_italic)
        if leading:
            _LEADING_MAP[name.lower()] = leading
        if multiplier:
            _MULTIPLIER_MAP[name.lower()] = multiplier


def line_info(p):
    """ Calculate line break info for a paragraph"""
    frags = p.blPara
    if frags.kind == 0:
        unused = min(entry[0] for entry in frags.lines)
        bad_breaks = sum(type(c) == _SplitWord for entry in frags.lines for c in entry[1])
        ok_breaks = len(frags.lines) - 1 - bad_breaks
        LOGGER.fine("Fragments = " + " | ".join(str(c) + ":" + type(c).__name__
                                                for entry in frags.lines for c in entry[1]))
    elif frags.kind == 1:
        unused = min(entry.extraSpace for entry in frags.lines)
        bad_breaks = sum(type(frag) == _SplitFrag for frag in p.frags)
        specified_breaks = sum(item.lineBreak for item in frags.lines)
        ok_breaks = len(frags.lines) - 1 - bad_breaks - specified_breaks
        LOGGER.fine("Fragments = " + " | ".join((c[1][1] + ":" + type(c).__name__) for c in p.frags))
    else:
        raise NotImplementedError()
    return bad_breaks, ok_breaks, unused


@lru_cache
def make_paragraph_style(align, font, size, leading, opacity, rgb):
    alignment = {'left': 0, 'center': 1, 'right': 2, 'fill': 4, 'justify': 4}[align]
    opacity = float(opacity) if opacity is not None else 1.0
    color = reportlab.lib.colors.Color(*rgb, alpha=opacity)
    leading *= _MULTIPLIER_MAP[font.lower()]
    size *= _MULTIPLIER_MAP[font.lower()]
    return ParagraphStyle(name='_tmp', spaceShrinkage=0.1,
                          fontName=font, fontSize=size, leading=leading,
                          allowWidows=0, embeddedHyphenation=1, alignment=alignment,
                          hyphenationMinWordLength=1,
                          textColor=color)
