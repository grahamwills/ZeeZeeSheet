import logging
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, OrderedDict, Union

import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.utils
from docutils.parsers.rst import Directive, directives
from reportlab.lib.units import cm, inch, mm

from sheet.common import configured_logger, parse_options
from sheet.model import Block, Method, Run, Section, Sheet, Spacing
from sheet.style import Style, Stylesheet

LOGGER = configured_logger(__name__)

LOG_UNHANDLED = True


class command(docutils.nodes.important):
    def __init__(self, name: str, options: str):
        super().__init__()
        self.name = name
        self.options = options


class DirectiveHandler(Directive):
    required_arguments = 0
    optional_arguments = 100
    has_content = False

    def run(self):
        return [command(self.name, self.arguments)]


directives.register_directive('page', DirectiveHandler)
directives.register_directive('section', DirectiveHandler)
directives.register_directive('block', DirectiveHandler)
directives.register_directive('title', DirectiveHandler)


def _to_size(txt: str) -> int:
    if txt.endswith('in'):
        return round(float(txt[:-2]) * inch)
    if txt.endswith('mm'):
        return round(float(txt[:-2]) * mm)
    if txt.endswith('cm'):
        return round(float(txt[:-2]) * cm)
    if txt.endswith('px') or txt.endswith('pt'):
        return round(float(txt[:-2]))
    return int(txt)


@dataclass
class Status:
    section: Optional[Section] = None
    block: Optional[Block] = None
    run: Optional[Run] = None
    directives: Dict = field(default_factory=OrderedDict)

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

    def add_to_run(self, txt):
        run = self.run

        # The style is one of these two items for a text string
        if run == self.block.title:
            style = self.block.title_style
        else:
            style = self.block.style
        if self.within('strong'):
            style = style.sub_style('strong')
        elif self.within('emphasis'):
            style = style.sub_style('emphasis')

        run.add(txt, style)

    def directives_for(self, name) -> List[str]:
        return self.directives.get(name, [])


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

    def __init__(self, document):
        super().__init__(document)
        self.styles = Stylesheet()
        self.style_name = None
        self.active = False

    def visit_title(self, node: docutils.nodes.title) -> None:
        if self.active:
            self.style_name = node.astext()
        if node.astext().lower() == 'styles':
            # We are about to process style definitions
            self.active = True
        raise docutils.nodes.SkipChildren

    def unknown_visit(self, node: docutils.nodes.Node) -> None:
        pass

    def unknown_departure(self, node: docutils.nodes.Node) -> None:
        pass

    def visit_term(self, node) -> None:
        if self.active:
            self.style_name = node.astext()
            LOGGER.debug("Style - Defining style '%s' using '%s'", self.style_name, node.__class__.__name__)
        raise docutils.nodes.SkipChildren

    def visit_Text(self, node: docutils.nodes.Text) -> None:
        if self.active:
            txt = node.astext().replace('\n', ' ')
            LOGGER.debug("Style - modifying '%s' with '%s'", self.style_name, txt)
            self.styles.define(self.style_name, **parse_options(txt))
        raise docutils.nodes.SkipChildren


class SheetVisitor(docutils.nodes.NodeVisitor):

    def __init__(self, document, styles: Stylesheet):
        super().__init__(document)
        self.styles = styles
        self.status = Status()
        self.sheet = Sheet()

    def apply_options(self, item: object, options: List[str], prefix=''):
        opts = self._options_as_dict(options)

        # Handle method
        if 'method' in opts:
            method_name = opts.pop('method')
            method_opts = dict()
            for k in list(opts.keys()):
                if k.startswith(method_name + ':'):
                    method_opts[k.split(':')[1]] = opts.pop(k)
            setattr(item, prefix + 'method', Method(method_name, method_opts))

        # Handle styles


        # Handle the rest
        for key, value in opts.items():
            if key == 'padding':
                key = 'spacing'
                value = Spacing(margin=item.spacing.margin, padding=_to_size(value))
            elif key == 'margin':
                key = 'spacing'
                value = Spacing(padding=item.spacing.padding, margin=_to_size(value))


            if key in {'strong', 'emphasis'}:
                # set the substyle for this style
                style = getattr(item, prefix+'style')
                style.sub_styles[key] = self.styles.items[value]
            elif hasattr(item, key):
                setattr(item, prefix + key, value)
            else:
                warnings.warn("Undefined property definition %s=%s ignored while building %s" %
                              (key, value, item.__class__.__name__))
        return item

    def _options_as_dict(self, options) -> Dict[str, Union[str, Style]]:
        opts = dict()
        for txt in options:
            if txt[0] == ':':
                warnings.warn("Not handled yet")
                break
            p = txt.find('=')
            if p >= 0:
                key = txt[:p].strip().lower()
                value = txt[p + 1:].strip()
            else:
                key = txt.strip().lower()
                if txt is options[0]:
                    # The first one can be a method name
                    value = key
                    key = 'method'
                else:
                    value = True
            if key.endswith('style'):
                value = self.styles[value]
            if key == 'size':
                key = 'pagesize'
                value = (_to_size(value.split('x')[0]), _to_size(value.split('x')[1]))
            opts[key] = value

        return opts

    def visit_command(self, node: command):
        LOGGER.debug("Entering '%s'", self.status.enter(node))
        LOGGER.debug("Setting directive '%s' <- %s", node.name, node.options)
        self.status.directives[node.name] = node.options

    def visit_comment(self, node: docutils.nodes.comment) -> None:
        LOGGER.debug("Entering '%s'", self.status.enter(node))
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
            LOGGER.info("***** Style Sheet enocuntered: aborting regular processing")
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

        self.status.add_to_run(txt)

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

    def depart_document(self, node: docutils.nodes.document):
        LOGGER.debug("Departing '%s'", self.status.depart(node))
        sheet = self.status.directives_for('page')
        LOGGER.info("... Applying sheet directives and fixing structure: %s", sheet)
        self.apply_options(self.sheet, sheet)
        self.sheet.fixup()

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

        content_directives = self.status.directives_for('block')
        title_directives = self.status.directives_for('title')
        block = Block(style=self.styles['default'], title_style=self.styles['default-title'])
        self.apply_options(block, content_directives)
        self.apply_options(block, title_directives, prefix='title_')
        self.status.block = block
        LOGGER.info("... Adding block with directives : content=%s, title=%s", block, title_directives)
        self.status.section.add_block(self.status.block)

    def create_section(self):
        assert self.status.section is None

        section_directives = self.status.directives_for('section')
        LOGGER.info("... Adding section with directives = %s", section_directives)
        section = Section(style=self.styles['default-section'])
        self.status.section = self.apply_options(section, section_directives)
        self.sheet.content.append(self.status.section)


def read_sheet(file) -> Sheet:
    with open(file, 'r') as file:
        data = file.read()
    return build_sheet(data)


def build_sheet(data):
    with warnings.catch_warnings(record=True) as warns:
        warnings.simplefilter("always")
        doc = parse_rst(data)

        style_visitor = StyleVisitor(doc)
        doc.walkabout(style_visitor)
        styles = style_visitor.styles

        if LOGGER.getEffectiveLevel() <= logging.DEBUG:
            for k, v in styles.items.items():
                LOGGER.debug('.. style %16s = %s', k, v)

        sheet_visitor = SheetVisitor(doc, styles)
        doc.walkabout(sheet_visitor)
        sheet = sheet_visitor.sheet
        sheet.fixup()

        for w in warns:
            if not str(w.message).startswith('unclosed file'):
                LOGGER.warning("[%s:%s] While reading: %s" % (w.filename, w.lineno, w.message))
        return sheet
