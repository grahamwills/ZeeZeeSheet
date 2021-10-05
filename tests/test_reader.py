from textwrap import dedent

from model import Sheet
from reader import build_sheet


def test_split_definitions():
    sheet = build_sheet(dedent(
            """
                title
                 - one
                 - two
                
                 - three
            """
    ))
    assert dump(sheet) == 'Section< Block["title": one, two, three] >'


def test_two_blocks():
    sheet = build_sheet(dedent(
            """
                abc
                 - one
                 - two
                def
                 - three
            """
    ))
    assert dump(sheet) == 'Section< Block["abc": one, two], Block["def": three] >'


def test_multiple_simple_blocks():
    sheet = build_sheet(dedent(
            """
                abc
 
                def
                
                ghi
            """
    ))
    assert dump(sheet) == 'Section< Block[abc], Block[def], Block[ghi] >'


def test_two_sections():
    sheet = build_sheet(dedent(
            """
                abc
                 - one
                 - two
                 
                ---------------------------------------------------
                
                def
                 - three
            """
    ))
    assert dump(sheet) == 'Section< Block["abc": one, two] > | Section< Block["def": three] >'


def test_titled():
    sheet = build_sheet(dedent(
            """
                eenie
                -----
                 - one

                meenie
                minie
            """
    ))
    assert dump(sheet) == 'Section< Block["eenie": one], Block[meenie minie] >'


def test_images():
    sheet = build_sheet(dedent(
            """
                Picture
                
                .. image:: im1.jpg
                   :height: 34
                ..
                
                 - abc
                 - def
                 
                Second
                
                .. image:: im2.jpg
                   :height: 34
                ..

                Third
                 - A-B-C
                 
                .. image:: im3.jpg
                ..
                
                Fourth
                            

            """
    ))
    assert dump(
            sheet) == 'Section< Block["Picture": <im1.jpg>abc, def], Block["Second": <im2.jpg>], Block["Third": ' \
                      'A-B-C], ' \
                      'Block[<im3.jpg>], Block[Fourth] >'


def test_bad():
    sheet = build_sheet(dedent(
            """
                eenie
                ----
                 - one
                      - two
                  meenie
                minie
            """
    ))
    assert dump(sheet) == 'Section< Block["eenie": ], Block["one": two], Block[meenie], Block[minie] >'


def dump(sheet: Sheet) -> str:
    seps = (('< ', ' >'), ('[', ']'))
    return " | ".join(_dump(s, seps) for s in sheet.content)


def _dump(item, seps) -> str:
    additional = ''
    if hasattr(item, 'title') and item.title:
        additional += '"%s": ' % item.title
    if hasattr(item, 'image') and item.image:
        additional += '<%s>' % item.image['uri']
    if hasattr(item, 'content'):
        seps2 = seps[1:]
        return ("%s%s%s" % (item.__class__.__name__, seps[0][0], additional)) \
               + ", ".join(_dump(s, seps2) for s in item.content) + seps[0][1]
    else:
        return str(item)
