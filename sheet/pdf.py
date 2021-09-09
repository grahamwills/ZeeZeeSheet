import contextlib
import io
from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Optional

import reportlab.lib.colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.pdfgen.pathobject import PDFPathObject
from reportlab.platypus import Flowable

from roughen import Roughener
from common import Rect, configured_logger
from model import Element, ElementType, Run
from style import DEFAULT, Style

LOGGER = configured_logger(__name__)

_CHECKED_BOX = '../data/system/images/checked.png'
_UNCHECKED_BOX = '../data/system/images/unchecked.png'
_LEADING_MAP = defaultdict(lambda: 1.2)

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
        self.base_dir = output_file.parent
        self.page_height = int(pagesize[1])
        self.debug = debug
        self._name_index = 0
        self.style = None

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

    def draw_rect(self, r: Rect, method: DrawMethod, rounded=0):
        method = self._set_drawing_styles(method)
        roughener = self._make_roughener()
        top = self.page_height - r.bottom
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

    def _make_roughener(self, style=None) -> Optional[Roughener]:
        style = style or self.style
        if style:
            if style.roughness:
                return Roughener(self, 'rough', style.roughness)
            if style.teeth:
                return Roughener(self, 'teeth', style.teeth)
        return None

    def rect_to_path(self, b:Rect, style:Style):
        roughener = self._make_roughener(style)
        if roughener:
            return roughener.rect_to_path(b.left, b.top, b.width, b.height)
        path = self.beginPath()
        path.rect(b.left, b.top, b.width, b.height)
        path.close()
        return path


def _element_to_html(e: Element, pdf: PDF, base_style: Style):
    if e.which == ElementType.TEXT or e.which == ElementType.SYMBOL:
        txt = e.value
    else:
        txt = str(e)

    style = e.style

    if style.italic:
        txt = '<i>' + txt + '</i>'
    if style.bold:
        txt = '<b>' + txt + '</b>'

    if style.size and style.size != base_style.size:
        size = " size='%d'" % style.size
    else:
        size = ''

    if style.font and style.font != base_style.font:
        face = " face='%s'" % style.font
    else:
        face = ''

    if style.color and (style.color != base_style.color or style.opacity != base_style.opacity):
        opacity = style.opacity if style.opacity is not None else 1.0
        color = " color='rgba(%d, %d, %d, %1.2f)'" % (
            round(255 * style.color.get_red()),
            round(255 * style.color.get_green()),
            round(255 * style.color.get_blue()),
            opacity
        )
    else:
        color = ''

    if e.which == ElementType.CHECKBOX:
        target = _UNCHECKED_BOX if e.value in {'O', 'o', ' ', '0'} else _CHECKED_BOX
        return "<img height=%d width=%d src='%s'/>" % (style.size, style.size, target)
    if e.which != ElementType.TEXT:
        face = " face='Symbola'"
    if face or size or color:
        return "<font %s%s%s>%s</font>" % (face, size, color, txt)
    else:
        return txt


def install_fonts() -> [str]:
    user_fonts = []
    install_font('Gotham', 'Gotham', user_fonts)
    install_font('Baskerville', 'Baskerville', user_fonts)

    install_font('Adventure', 'Adventure', user_fonts, 1.0)
    install_font('Steampunk', 'Steamwreck', user_fonts, 0.9)
    install_font('Steamship', 'Starship', user_fonts, 1.15)
    install_font('LoveYou', 'I Love What You Do', user_fonts, 1.2)
    install_font('Comics', 'back-issues-bb', user_fonts)
    install_font('Jedi', 'Starjedi', user_fonts)
    install_font('Western', 'Carnevalee Freakshow', user_fonts, 1.0)
    install_font('ArtDeco', 'CaviarDreams', user_fonts, 1.1)
    install_font('Radioactive', '28 Days Later', user_fonts, 1.0)
    install_font('Typewriter', 'SpecialElite', user_fonts)
    install_font('Monster', 'mrsmonster', user_fonts, 1.0)
    install_font('Script', 'Parisienne', user_fonts, 1.1)

    install_font('MotionPicture', 'MotionPicture', user_fonts, 1.0)
    install_font('Symbola', 'Symbola', user_fonts)
    return sorted(base_fonts() + user_fonts)


def base_fonts():
    cv = canvas.Canvas(io.BytesIO())
    fonts = cv.getAvailableFonts()
    fonts.remove('ZapfDingbats')
    fonts.remove('Symbol')
    return fonts


def create_single_font(name, resource_name, default_font_name, user_fonts):
    loc = Path(__file__).parent.parent.joinpath('data/system/fonts/', resource_name + ".ttf")
    if loc.exists():
        font = TTFont(name, loc)
        pdfmetrics.registerFont(font)
        user_fonts.append(name)
        return name
    else:
        return default_font_name


def install_font(name, resource_name, user_fonts, leading: float = None):
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
