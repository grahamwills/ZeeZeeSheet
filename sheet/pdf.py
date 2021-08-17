import io
from collections import defaultdict
from pathlib import Path

import reportlab.lib.colors
from colour import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.pdfgen.pathobject import PDFPathObject
from reportlab.platypus import Flowable

from sheet import common
from sheet.model import Element, ElementType, Run
from style import Style, Stylesheet

LOGGER = common.configured_logger(__name__)

_CHECKED_BOX = '../data/system/images/checked.png'
_UNCHECKED_BOX = '../data/system/images/unchecked.png'

_LEADING_MAP = defaultdict(lambda: 1.2)


class PDF(canvas.Canvas):
    working_dir: Path
    page_height: int
    _stylesheet: Stylesheet
    debug: bool

    _name_index: int

    def __init__(self, output_file: Path, styles: Stylesheet, pagesize: (int, int), debug: bool = False) -> None:
        super().__init__(str(output_file.absolute()), pagesize=pagesize)
        fonts = install_fonts()
        LOGGER.info("Installed fonts = %s", fonts)
        self.working_dir = output_file.parent
        self.page_height = int(pagesize[1])
        self._stylesheet = styles

        self.debug = debug
        self._name_index = 0

    def drawImage(self, image, x, y, width=None, height=None, mask=None, preserveAspectRatio=False, anchor='c',
                  anchorAtXY=False, showBoundary=False):
        fileName = image.fileName if hasattr(image, 'fileName') else str(image)
        if fileName == _UNCHECKED_BOX:
            return self.add_checkbox(x, y, width, height, False)
        elif fileName == _CHECKED_BOX:
            return self.add_checkbox(x, y, width, height, True)
        else:
            return super().drawImage(image, x, y, width, height, mask, preserveAspectRatio, anchor, anchorAtXY,
                                     showBoundary)

    def add_checkbox(self, rx, ry, width, height, state) -> (int, int):
        x, y = self.absolutePosition(rx, ry)
        self._name_index += 1
        name = "f%d" % self._name_index
        LOGGER.debug("Adding checkbox name='%s' with state=%s ", name, state)
        self.acroForm.checkbox(name=name, x=x - 0.5, y=y - 0.5, size=min(width, height) + 1,
                               fillColor=reportlab.lib.colors.Color(1, 1, 1),
                               buttonStyle='cross', borderWidth=0.5, checked=state)
        return width, height

    def style(self, style):
        if isinstance(style, Style):
            return style
        else:
            return self._stylesheet[style]

    def fillColor(self, color: Color, alpha=None):
        self.setFillColorRGB(*color.rgb, alpha=alpha)

    def strokeColor(self, color: Color, alpha=None):
        self.setStrokeColorRGB(*color.rgb, alpha=alpha)

    def fill_rect(self, r: common.Rect, style: Style, rounded=0):
        if style.background:
            self.fillColor(style.background, alpha=style.opacity)
            self.setLineWidth(0)

            if rounded > 0:
                self.roundRect(r.left, self.page_height - r.bottom, r.width, r.height, rounded, fill=1, stroke=0)
            else:
                self.rect(r.left, self.page_height - r.bottom, r.width, r.height, fill=1, stroke=0)

    def stroke_rect(self, r: common.Rect, style: Style, rounded=0):
        if style.borderColor and style.borderWidth:
            self.strokeColor(style.borderColor, alpha=style.opacity)
            self.setLineWidth(style.borderWidth)
            if rounded > 0:
                self.roundRect(r.left, self.page_height - r.bottom, r.width, r.height, rounded, fill=0, stroke=1)
            else:
                self.rect(r.left, self.page_height - r.bottom, r.width, r.height, fill=0, stroke=1)

    def fill_path(self, path: PDFPathObject, style: Style):
        if style.background:
            self.fillColor(style.background, alpha=style.opacity)
            self.setLineWidth(0)
            self.drawPath(path, fill=1, stroke=0)

    def stroke_path(self, path: PDFPathObject, style: Style):
        if style.borderColor and style.borderWidth:
            self.strokeColor(style.borderColor, alpha=style.opacity)
            self.setLineWidth(style.borderWidth)
            self.drawPath(path, fill=0, stroke=1)

    def draw_flowable(self, flowable: Flowable, bounds):
        try:
            flowable.drawOn(self, bounds.left, self.page_height - bounds.bottom)
        except:
            LOGGER.error("Error trying to draw %s into %s", flowable.__class__.__name__, bounds)

    def paragraph_style_for(self, run: Run) -> (Style, float):
        styles = [self.style(e.style) for e in run.items]
        style = styles[0]
        max_size = max(s.size for s in styles)
        max_leading = max(self.leading_for(s) for s in styles)
        if max_size != style.size:
            style = style.modify(size=max_size)
        return style, max_leading

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


def _element_to_html(e: Element, pdf: PDF, base_style: Style):
    if e.which == ElementType.TEXT or e.which == ElementType.SYMBOL:
        txt = e.value
    else:
        txt = str(e)

    style = pdf.style(e.style)

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


def install_font(name, resource_name, user_fonts, leading:float=None):
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
