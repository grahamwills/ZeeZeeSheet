import warnings
from dataclasses import dataclass, field
from typing import List, Optional

import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.utils

from sheet.common import configured_logger, parse_directive, parse_options
from sheet.model import Block, Run, Section, Sheet
from sheet.style import Stylesheet

LOGGER = configured_logger(__name__)

LOG_UNHANDLED = True


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
    sheet: Stylesheet
    style_name: Optional[str]

    def __init__(self, document, sheet: Sheet):
        super().__init__(document)
        self.styles = sheet.stylesheet
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
        self.styles.define(self.style_name, **parse_options(txt))
        raise docutils.nodes.SkipChildren


class SheetVisitor(docutils.nodes.NodeVisitor):

    def __init__(self, document, sheet: Sheet):
        super().__init__(document)
        self.status = Status()
        self.sheet = sheet

        self.block_method = parse_directive('default')
        self.section_method = parse_directive('stack')
        self.title_method = parse_directive("banner style=_banner")

        self.content_style = 'default'
        self.emphasis_style = '_emphasis'
        self.strong_style = '_strong'

    def visit_comment(self, node: docutils.nodes.comment) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        txt = node.astext().strip()
        if not txt:
            return
        command = parse_directive(txt)
        if not command.tag:
            raise ValueError("Comment directive did not have a tag: '%s'", txt)
        if command.tag == 'section':
            LOGGER.info(".. setting section layout method: %s", command)
            self.section_method = command
        elif command.tag == 'block':
            LOGGER.info(".. setting block layout method: %s", command)
            self.block_method = command
        elif command.tag == 'title':
            LOGGER.info(".. setting title display method: %s", command)
            self.title_method = command
        elif command.tag == 'style':
            LOGGER.info(".. setting style: %s", command)
            if command.command:
                self.content_style = command.command
            for k, v in command.options.items():
                if k == 'emphasis' or k.lower() == 'i':
                    self.emphasis_style = v
                elif k == 'strong' or k.lower() == 'b':
                    self.strong_style = v
                else:
                    warnings.warn("Unrecognized style option '%s'" % k)

        elif command.tag == 'page':
            LOGGER.info(".. setting page info: %s", command)
            if command.command:
                self.sheet.layout_method = command
            self.sheet.apply_directive(**command.options)
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
            self.create_block()
            self.status.block.add_title()
            self.status.target_block_title()

    def depart_title(self, node) -> None:
        LOGGER.debug("Departing '%s'", self.status.depart(node))
        self.status.target_nothing()

    def depart_paragraph(self, node) -> None:
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

        if self.status.run is None:
            self.status.block = None
            self.create_block()
            self.status.block.add_title()
            self.status.target_block_title()
            LOGGER.info("... Adding text '%s' as a title to a new block", txt)
        else:
            LOGGER.info("... Adding text '%s'", txt)

        if self.status.within('strong'):
            style = self.strong_style + ":" + self.content_style
        elif self.status.within('emphasis'):
            style = self.emphasis_style + ":" + self.content_style
        else:
            style = self.content_style

        self.status.run.add(txt, style)

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

        if not self.status.section:
            self.create_section()

        title_display = self.title_method
        block_display = self.block_method
        self.status.block = Block(title_method=title_display, block_method=block_display)
        if 'padding' in block_display.options:
            self.status.block.padding = int(block_display.options['padding'])
        LOGGER.info("... Adding block with display = %s, title = %s", block_display, title_display)
        self.status.section.add_block(self.status.block)

    def create_section(self):
        assert self.status.section is None

        layout = self.section_method
        LOGGER.info("... Adding section with layout = %s", layout)
        self.status.section = Section(layout_method=layout)
        self.sheet.content.append(self.status.section)


def read_sheet(file) -> Sheet:
    with open(file, 'r') as file:
        data = file.read()
    return build_sheet(data)


def build_sheet(data):

    with warnings.catch_warnings(record=True) as warns:
        warnings.simplefilter("always")
        doc = parse_rst(data)
        sheet = Sheet()
        doc.walkabout(SheetVisitor(doc, sheet))
        sheet.fixup()
        for w in warns:
            if not str(w.message).startswith('unclosed file'):
                LOGGER.warning("[%s:%s] While reading: %s" % (w.filename, w.lineno, w.message))
        return sheet
