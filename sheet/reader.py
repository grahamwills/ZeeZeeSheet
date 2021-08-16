from dataclasses import dataclass, field
from typing import List, Optional

import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.utils
from colour import Color

from sheet import common
from sheet.model import BLACK, Block, Run, Section, Sheet, Style

LOGGER = common.configured_logger(__name__)

LOG_UNHANDLED = False


@dataclass
class Status:
    section: Optional[Section] = None
    block: Optional[Block] = None
    run: Optional[Run] = None

    stack: List[str] = field(default_factory=list)

    def _name(self, node):
        return node.__class__.__name__

    def _report(self) -> str:
        return " < ".join(self.stack[::-1])

    def enter(self, node: docutils.nodes.Node) -> str:
        self.stack.append(self._name(node))
        return self._report()

    def depart(self, node: docutils.nodes.Node) -> str:
        report = self._report()
        last = self.stack.pop()
        if last is not self._name(node):
            raise ValueError("Inconsistent departure: expected '%s', but was '%s'"
                             % (last, self._name(node)))
        return report

    def style_modifiers(self):
        bold = self.within('strong')
        italic = self.within('emphasis')
        if bold and italic:
            return 'BI'
        if bold:
            return 'B'
        if italic:
            return 'I'
        return None

    def within(self, name):
        return name in self.stack

    def parent(self):
        return self.stack[-2]

    def target_block_title(self):
        LOGGER.info("... Text target set to block title")
        self.run = self.block.title

    def target_block_content(self):
        LOGGER.info("... Text target set to block content")
        self.run = self.block.content[-1]

    def target_nothing(self):
        LOGGER.info("... Clearing text target")
        self.run = None


class FormatError(RuntimeError):
    pass


def parse_rst(text: str) -> docutils.nodes.document:
    parser = docutils.parsers.rst.Parser()
    components = (docutils.parsers.rst.Parser,)
    settings = docutils.frontend.OptionParser(components=components).get_default_values()
    document = docutils.utils.new_document('<rst-doc>', settings=settings)
    parser.parse(text, document)
    return document


def line_of(node: docutils.nodes.Node):
    if node.line is None:
        return line_of(node.parent)
    else:
        return node.line


# noinspection PyPep8Naming
class StyleVisitor(docutils.nodes.NodeVisitor):
    sheet: Sheet
    style_name: Optional[str]

    def __init__(self, document, sheet: Sheet):
        super().__init__(document)
        self.sheet = sheet
        self.style_name = None

    def unknown_visit(self, node: docutils.nodes.Node) -> None:
        pass

    def unknown_departure(self, node: docutils.nodes.Node) -> None:
        pass

    def visit_title(self, node: docutils.nodes.title) -> None:
        self.style_name = node.astext()
        LOGGER.debug("Defining style '%s' using '%s'", self.style_name, node.__class__.__name__)
        raise docutils.nodes.SkipChildren

    def visit_term(self, node) -> None:
        self.style_name = node.astext()
        LOGGER.debug("Style - Defining style '%s' using '%s'", self.style_name, node.__class__.__name__)
        raise docutils.nodes.SkipChildren

    def visit_Text(self, node: docutils.nodes.Text) -> None:
        txt = node.astext().replace('\n', ' ')
        LOGGER.debug("Style - modifying '%s' with '%s'", self.style_name, txt)
        _modify_style(self.sheet.styles, self.style_name, txt)
        raise docutils.nodes.SkipChildren


class SheetVisitor(docutils.nodes.NodeVisitor):

    def __init__(self, document, sheet: Sheet):
        super().__init__(document)
        self.block_layout_method = common.parse_directive('default')
        self.section_layout_method = common.parse_directive('stack')
        self.title_display_method = common.parse_directive("banner style=_banner")
        self.style = 'default'
        self.current_style_def_name = None

        self.status = Status()
        self.sheet = sheet

    def visit_comment(self, node: docutils.nodes.comment) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        txt = node.astext().strip()
        if not txt:
            return
        command = common.parse_directive(txt)
        if not command.tag:
            raise ValueError("Comment directive did not have a tag: '%s'", txt)
        if command.tag == 'section':
            LOGGER.info(".. setting section layout method: %s", command)
            self.section_layout_method = command
        elif command.tag == 'block':
            LOGGER.info(".. setting block layout method: %s", command)
            self.block_layout_method = command
        elif command.tag == 'title':
            LOGGER.info(".. setting title display method: %s", command)
            self.title_display_method = command
        elif command.tag == 'style':
            LOGGER.info(".. setting style: %s", command)
            self.style = command.command
        elif command.tag == 'page':
            LOGGER.info(".. setting page info: %s", command)
            if command.command:
                self.sheet.layout_method = command
            self.sheet.apply_styles(**command.options)
        else:
            raise ValueError("Unknown comment directive: '%s', line=%d" % (command, line_of(node)))
        raise docutils.nodes.SkipChildren

    def visit_definition_list_item(self, node) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        self.status.block = None
        self.create_block()

    def depart_definition_list_item(self, node) -> None:
        LOGGER.debug("Departing '%s'", self.status.depart(node))
        assert self.status.block is not None
        self.status.block = None

    def visit_term(self, node) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        self.status.block.add_title()
        self.status.target_block_title()

    def depart_term(self, node) -> None:
        LOGGER.debug("Departing '%s'", self.status.depart(node))
        self.status.target_nothing()

    def visit_title(self, node: docutils.nodes.title) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        # Check to see if we are about to process style definitions
        if node.astext().lower() == 'styles':
            LOGGER.info("***** Starting style definition section and aborting regular processing")
            node.parent.walkabout(StyleVisitor(self.document, self.sheet))
            raise docutils.nodes.StopTraversal
        else:
            assert self.status.block is None
            self.create_block()
            self.status.block.add_title()
            self.status.target_block_title()

    def depart_title(self, node) -> None:
        LOGGER.debug("Departing '%s'", self.status.depart(node))
        self.status.target_nothing()

    def visit_transition(self, node: docutils.nodes.Node) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        LOGGER.debug("... Finishing Current Section")
        self.status.block = None
        self.status.section = None

    def visit_list_item(self, node: docutils.nodes.list_item) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        LOGGER.info("... Creating new content in %s", self.status.block)
        self.status.block.add_content()
        self.status.target_block_content()

    def depart_list_item(self, node: docutils.nodes.list_item) -> None:
        LOGGER.debug("Departing '%s'", self.status.depart(node))
        self.status.target_nothing()

    def visit_Text(self, node: docutils.nodes.Text) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        txt = node.astext().replace('\n', ' ')
        modifiers = self.status.style_modifiers()

        if self.status.run is None:
            self.status.block = None
            self.create_block()
            self.status.block.add_title()
            self.status.target_block_title()
            LOGGER.info("... Adding text '%s' as a title to a new block", txt)
        else:
            LOGGER.info("... Adding text '%s'", txt)

        self.status.run.add(txt, self.style, modifiers)

    def visit_image(self, node: docutils.nodes.image) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))

        if self.status.block is None:
            # New block for the image
            self.create_block()
        LOGGER.info("... Adding image '%s'", node)
        self.status.block.image = node.attributes

    def visit_system_message(self, node: docutils.nodes.system_message) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        LOGGER.debug("System warning: %s", node.astext())
        raise docutils.nodes.SkipChildren

    def unknown_visit(self, node: docutils.nodes.Node) -> None:
        txt = self.status.enter(node)
        if LOG_UNHANDLED:
            LOGGER.debug("Entering '%s' (no special handling)", txt)

    def unknown_departure(self, node: docutils.nodes.Node) -> None:
        txt = self.status.depart(node)
        if LOG_UNHANDLED:
            LOGGER.debug("Departing '%s'", txt)

    def create_block(self):
        assert self.status.block is None

        if not self.status.section:
            self.create_section()

        title_display = self.title_display_method
        block_display = self.block_layout_method
        self.status.block = Block(title_method=title_display, block_method=block_display)
        if 'padding' in block_display.options:
            self.status.block.padding = int(block_display.options['padding'])
        LOGGER.info("... Adding block with display = %s, title = %s", block_display, title_display)
        self.status.section.add_block(self.status.block)

    def create_section(self):
        assert self.status.section is None

        layout = self.section_layout_method
        LOGGER.info("... Adding section with layout = %s", layout)
        self.status.section = Section(layout_method=layout, padding=self.sheet.padding)
        self.sheet.content.append(self.status.section)


def _modify_style(styles, key, txt):
    if not styles:
        # Ensure there is a default style
        styles['default'] = Style(font='Times', size=10, color=BLACK, align='left')

    s = styles.get(key, None)
    if not s:
        s = Style()
    items = dict((k.strip(), v.strip()) for k, v in tuple(pair.split('=') for pair in txt.split()))
    if not 'inherit' in items:
        items['inherit'] = 'default'
    for k, v in items.items():
        if k == 'inherit':
            parent = styles[v]
            s.color = s.color or parent.color
            s.size = s.size or parent.size
            s.font = s.font or parent.font
            s.align = s.align or parent.align
            s.background = s.background or parent.background
        elif k in {'color', 'foreground', 'fg'}:
            s.color = Color(v)
        elif k in {'background', 'bg'}:
            s.background = Color(v)
        elif k in {'size', 'fontSize', 'fontsize'}:
            s.size = float(v)
        elif k in {'font', 'family', 'face'}:
            s.font = str(v)
        elif k in {'align', 'alignment'}:
            s.align = str(v)
        elif k in {'border', 'borderColor'}:
            s.borderColor = Color(v) if v and v not in {'none', 'None'} else None
        elif k in {'width', 'borderWidth'}:
            s.borderWidth = float(v)
        else:
            raise ValueError("Illegal style definition: %s" % k)
    styles[key] = s


def read_sheet(file) -> Sheet:
    with open(file, 'r') as file:
        data = file.read()
    return build_sheet(data)


def build_sheet(data):
    doc = parse_rst(data)
    sheet = Sheet()
    doc.walkabout(SheetVisitor(doc, sheet))
    sheet.fixup()
    return sheet
