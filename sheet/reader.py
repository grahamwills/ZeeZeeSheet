import enum

import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.utils

import common
from model import Block, Section, Sheet

LOGGER = common.configured_logger(__name__)


class ReadState(enum.Enum):
    READY = 0
    STARTING_SECTION = 1
    IN_TITLE = 2
    IN_CONTENT = 3
    IN_CONTENT_ITEM = 4


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


class SheetVisitor(docutils.nodes.NodeVisitor):

    def __init__(self, document, sheet: Sheet):
        super().__init__(document)
        self.content_renderer = 'flow cols=1'
        self.border_renderer = 'banner'
        self.style = 'default'
        self.state = ReadState.READY
        self.sheet = sheet

        self.current_section = None
        self.current_block = None

        self.processing_styles = False
        self.current_style_def_name = None

        self.next_is_bold = False
        self.next_is_italic = False

    def visit_comment(self, node: docutils.nodes.comment) -> None:
        txt = node.astext().split(':')
        if len(txt) != 2:
            raise ValueError("Bad comment directive: '%s'", node.astext())
        command = txt[0].strip()
        value = txt[1].strip()
        if command == 'layout':
            self.content_renderer = value
        elif command == 'title':
            self.border_renderer = value
        elif command == 'style':
            self.style = value
        else:
            raise ValueError("Unknown comment directive: '%s', line=%d", command, line_of(node))

        LOGGER.info("Processed comment name='%s' value='%s'", command, value)
        raise docutils.nodes.SkipChildren

    def visit_title(self, node: docutils.nodes.title) -> None:
        # Check to see if we are about to process style definitions
        if self.state == ReadState.STARTING_SECTION and len(node.children) == 1 and node.astext().lower() == 'styles':
            LOGGER.info("Starting style definition section")
            self.processing_styles = True
            raise docutils.nodes.SkipChildren
        else:
            self.state = ReadState.READY

    def visit_transition(self, node: docutils.nodes.Node) -> None:
        self.visit_section(node)

    def visit_section(self, node: docutils.nodes.Node) -> None:
        if self.state == ReadState.STARTING_SECTION:
            return
        if self.processing_styles:
            raise FormatError("Styles must be the last section, but found new section on line %d" % line_of(node))
        LOGGER.debug("Starting new section")
        self.state = ReadState.STARTING_SECTION
        self.current_section = None
        self.current_block = None

    def visit_paragraph(self, _) -> None:
        if self.state == ReadState.IN_CONTENT_ITEM:
            LOGGER.debug("Finished content item")
            self.state = ReadState.IN_CONTENT
        else:
            LOGGER.debug("Ignoring paragraph marker")

    def visit_definition_list(self, _) -> None:
        self.current_block = None
        self.state = ReadState.READY

    def visit_definition_list_item(self, _) -> None:
        self.current_block = None
        self.state = ReadState.READY

    def visit_term(self, _) -> None:
        self.current_block = None
        self.state = ReadState.READY

    def visit_definition(self, _) -> None:
        self.state = ReadState.IN_CONTENT

    def visit_bullet_list(self, node: docutils.nodes.bullet_list) -> None:
        if not self.current_block:
            raise FormatError("List without preceeding text to define a block title, line=%d", line_of(node))
        self.state = ReadState.IN_CONTENT

    def visit_list_item(self, node: docutils.nodes.list_item) -> None:
        if not self.state in {ReadState.IN_CONTENT, ReadState.IN_CONTENT_ITEM}:
            raise FormatError("Unexpected list item outside of list, line=%d" % line_of(node))
        self.state = ReadState.IN_CONTENT

    def visit_Text(self, node: docutils.nodes.Text) -> None:
        txt = node.astext().replace('\n', ' ')

        if self.processing_styles:
            if self.state in {ReadState.IN_CONTENT_ITEM, ReadState.IN_CONTENT}:
                self.sheet.modify_style(self.current_style_def_name, txt)
            else:
                self.current_style_def_name = txt
            return

        modifiers = self._text_modifiers()
        if self.state in {ReadState.READY, ReadState.STARTING_SECTION}:
            self.current_block = Block()
            self.current_block.set_renderers(self.border_renderer, self.content_renderer)
            self._ensure_section().add_block(self.current_block)
            LOGGER.info("Defining title '%s', style=%s, mods=%s", txt, self.style, modifiers)
            self.current_block.add_title()
            self.current_block.add_txt_to_title(txt, self.style, modifiers)
        elif self.state == ReadState.IN_TITLE:
            LOGGER.info("Adding to title '%s', style=%s, mods=%s", txt, self.style, modifiers)
            self.current_block.add_txt_to_title(txt, self.style, modifiers)
        elif self.state == ReadState.IN_CONTENT:
            LOGGER.info("Creating new run : '%s', style=%s, mods=%s", txt, self.style, modifiers)
            self.current_block.add_content()
            self.current_block.add_txt_to_run(txt, self.style, modifiers)
            self.state = ReadState.IN_CONTENT_ITEM
        elif self.state == ReadState.IN_CONTENT_ITEM:
            LOGGER.info("Adding to run: '%s', style=%s, mods=%s", txt, self.style, modifiers)
            self.current_block.add_txt_to_run(txt, self.style, modifiers)
        else:
            print('UNPROCESSED TEXT:', txt)

    def visit_strong(self, _) -> None:
        self.next_is_bold = True

    def visit_emphasis(self, _) -> None:
        self.next_is_italic = True

    def visit_image(self, node: docutils.nodes.image) -> None:
        LOGGER.info("Ignoring image '%s'", node.attributes.get('uri'))
        pass

    def unknown_visit(self, node: docutils.nodes.Node) -> None:
        """Called for all other node types."""
        node_name = node.__class__.__name__
        print(node_name, node.__class__)

    def _ensure_section(self) -> Section:
        if not self.current_section:
            self.current_section = Section()
            self.sheet.content.append(self.current_section)
        return self.current_section

    def _text_modifiers(self):
        if self.next_is_bold and self.next_is_italic:
            self.next_is_bold = False
            self.next_is_italic = False
            return 'BI'
        if self.next_is_bold:
            self.next_is_bold = False
            return 'B'
        if self.next_is_italic:
            self.next_is_italic = False
            return 'I'
        return None


def read(file) -> Sheet:
    with open(file, 'r') as file:
        data = file.read()

    doc = parse_rst(data)

    sheet = Sheet()
    doc.walk(SheetVisitor(doc, sheet))

    sheet.print()
    return sheet
