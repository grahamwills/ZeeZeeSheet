import json
from pathlib import Path
from textwrap import dedent
from typing import Dict, List, Optional

import common

LOGGER = common.configured_logger(__name__)


def titled(name: str) -> str:
    return name + '\n' + '=' * len(name)


def sorted_values(d: Dict) -> List[Dict]:
    def by_number(pair):
        p = pair[0].split('.')
        return int(p[1]), p[0]

    # Handle stored items
    for k, v in list(d.items()):
        if 'items' in v:
            for k1, v1 in v['items'].items():
                if v1.get('containment', '') == 'Stored':
                    d[k1] = v1

    items = d.items()
    all = sorted(items, key=by_number)
    return [pair[1] for pair in all]


def extract_stats(items: List[Dict]) -> Optional[str]:
    stats = pop(items, 'AbilScore')

    if not stats:
        return None
    stat_strings = [" - %-18s | %4s | *+%s*" % ('**' + s['name'] + '**', s.get('stAbScModifier', '0'), s['stNet'])
                    for s in stats]
    return ".. title:: hidden\n.. block:: thermometer thermometer:style=banner_green thermometer:rows=100 " \
           "style=attributes\n\nAbility Scores\n" + "\n".join(stat_strings)


def extract_defenses(items: List[Dict]) -> Optional[str]:
    stats = pop(items, 'ArmorClass') + pop(items, 'Save') + pop(items, 'Derived')
    if not stats:
        return None

    stat_strings = [" - %-18s | %6s" %
                    ('**' + s['name'].replace(' Save', '') + '**', s.get('stDC', None) or s['stNet'])
                    for s in stats]
    return ".. title:: hidden\n.. block:: thermometer thermometer:style=banner_red thermometer:rows=100 " \
           "style=attributes\n\nDefenses\n" + "\n".join(stat_strings)


def trained(txt: str):
    return txt[0].upper()


def skill_tuple(s):
    t = trained(s['ProfLevel'])
    if t == 'U':
        return ('%s' % s['name'], t, s.get('stNet', 0))
    else:
        return ('**%s**' % s['name'], t, s.get('stNet', 0))


def extract_skills(items: List[Dict]) -> Optional[str]:
    stats = pop(items, 'Skill')
    skills = [skill_tuple(s) for s in stats]
    return 'Skills\n' + "\n".join([" - %16s -- **%s** (%s)" % (s[0], s[2], s[1]) for s in skills])


def trait_key(s: Dict) -> str:
    if 'Trait' not in s:
        return "Unknown"
    r = set(s['Trait'].split(','))
    if 'trtArchetype' in r or any(s.startswith('cl') for s in r):
        return "Class Feats"
    if 'trtSkill' in r:
        return "Skill Feats"
    if r == {'trtGeneral'}:
        return 'General Feats'
    else:
        return 'Ancestry Feats'


def extract_feats(items: List[Dict], ) -> Optional[str]:
    all = pop(items, 'Feat', isAction=False) + pop(items, 'Heritage')

    types = sorted(set(trait_key(s) for s in all))

    lines = []
    for t in types:
        lines.append('\n' + t)
        stats = [a for a in all if trait_key(a) == t]
        for s in stats:
            if 'summary' in s:
                lines.append(" - **{0}**: {1}".format(s['name'], s['summary']))
            else:
                LOGGER.info("Ignoring %s: %s", s['name'], s['description'].replace('\n', ' '))
    return "\n".join(lines)


def action_icon(s):
    if not s:
        return '–'
    if s == 'Action1':
        return '▶'
    if s == 'Action2':
        return '▶▶'
    if s == 'Action3':
        return '▶▶▶'
    if s == 'Reaction':
        return '↺'
    if s == 'Free':
        return '◌'

    raise ValueError("unknown action: %s" % s)


def prettify_traits(txt):
    parts = []
    for p in sorted(txt.split(',')):
        if p.startswith('cl') or p.startswith('ss'):
            p = p[2:]
        elif p.startswith('trt') or p.startswith('trd'):
            p = p[3:]
        parts.append(p)
    return " • ".join(parts)


def capitalize(s: str):
    return s[0].upper() + s[1:] if s else s


def to_color(s):
    if s == 'Ability':
        return 'green'
    if s == 'Feat':
        return 'black'
    if s == 'Spell' or s == 'FocSpell':
        return 'red'
    if s == 'MagicItem':
        return 'orange'
    raise ValueError("Unknown color: %s" % s)


def make_usage(target, range, area):
    target = target.replace('in range', '')

    if target and range and area:
        return "**Target**: {0} in {1} located within {2}".format(target, area, range)
    if target and range:
        return "**Target**: {0} within {2}".format(target, area, range)
    if target and area:
        return "**Target**: {0} in {1}".format(target, area, range)
    if target:
        return "**Target**: {0}".format(target)

    if range and area:
        return "**Area**: {0} within {1}".format(area, range)
    if range:
        return "**Range**: {0}".format(range)
    if area:
        return "**Area**: {0}".format(area)

    return None


def action_key(a) -> str:
    traits = "_".join(sorted(a.get('Trait', 'zz').split(',')))
    color = to_color(a['compset'])
    return traits + '_' +color + a['name']


def extract_actions(items: List[Dict]) -> Optional[str]:
    lines = []

    abilities = pop(items, 'Ability', isAction=True) + pop(items, 'FocSpell') + pop(items, 'Spell') + pop(items, 'Feat', isAction=True) \
                + pop(items, 'MagicItem', isAction=True)

    for a in sorted(abilities, key=action_key):
        color = to_color(a['compset'])
        name = a['name']
        level = a.get('spLevelNet', None)
        description = extract_description(a, level)
        trigger = a.get('reTrigger', '')
        frequency = capitalize(a.get('reFrequency', ''))
        action = action_icon(a.get('Action', ''))
        traits = prettify_traits(a.get('Trait', ''))
        levelBase = a.get('spLevelBase', None)
        usage = make_usage(a.get('vaTarget', ''), a.get('vaRangeText', ''), a.get('vaArea', ''))
        duration = a.get('vaDuraText', None) or a.get('spCastTime', None)

        if frequency:
            frequency = '*' + frequency + '*'
        if trigger:
            trigger = '**Trigger**: *' + trigger + '*'

        lines.append(".. title:: banner style=banner_{0}\n.. block:: style=back_{0}\n".format(color))
        if level:
            if level != levelBase:
                lines.append("{0} -- **{1}** -- *{2}→{3}*".format(action, name, levelBase, level))
            else:
                lines.append("{0} -- **{1}** -- *{2}*".format(action, name, level))
        else:
            lines.append("{0} -- **{1}**".format(action, name))

        if usage:
            lines.append(" - {0} ".format(usage))
        if trigger or frequency:
            lines.append(" - {0} -- {1}".format(trigger, frequency))
        if duration:
            lines.append(" - **Duration**: {0}".format(duration))
        lines += description
        if traits:
            lines.append(" - -- <font size=6 color='gray'>{0}</font> -- ".format(traits))
        lines.append('\n')

    return "\n".join(lines)


def embellish_description(p: str, lvl):
    p = p.strip()
    if not p:
        return None
    if p.startswith('{para type:bare below}'):
        # Don't want these extras
        return None

    if p.startswith('{para type:bare}') and p.endswith('{/para}'):
        p = p[16:-7]
    if p.startswith('{para}') and p.endswith('{/para}'):
        p = p[6:-7]

    if p.startswith('Heightened'):
        if p.startswith('Heightened (+') or p.startswith('Heightened ' + _level_heightened(lvl)):
            i = p.index(')')
            p = "**{0}**: {1}".format(p[:i + 1].strip(), p[i + 1:].strip())
        else:
            # Don't care about other levels
            return None

    if p.startswith('• '):
        p = "`• " + p[2:] + "`"
    if p.startswith('Activate'):
        p = "**Activate**: {0}".format(p[9:].strip())
    if p.startswith('Effect'):
        p = "**Effect**: {0}".format(p[7:].strip())
    if p.startswith('Critical Failure'):
        p = "**Critical Failure**: {0}".format(p[17:].strip())
    if p.startswith('Critical Success'):
        p = "**Critical Success**: {0}".format(p[17:].strip())
    if p.startswith('Success'):
        p = "**Success**: {0}".format(p[8:].strip())
    if p.startswith('Failure'):
        p = "**Failure**: {0}".format(p[8:].strip())

    p = p.replace('{icon:action1}', '▶')
    p = p.replace('{icon:action2}', '▶▶')
    p = p.replace('{icon:action3}', '▶▶▶')
    p = p.replace('{icon:reaction}', '↺')
    p = p.replace('{icon:free}', '◌')
    p = p.replace('{Icon:Action1}', '▶')
    p = p.replace('{Icon:Action2}', '▶▶')
    p = p.replace('{Icon:Action3}', '▶▶▶')
    p = p.replace('{Icon:Reaction}', '↺')
    p = p.replace('{Icon:Free}', '◌')
    return p


def _level_heightened(lvl):
    if lvl == 2:
        return '(2nd)'
    if lvl == 5:
        return '(3rd)'
    return "({}th)".format(lvl)


def extract_description(a, level: int) -> List[str]:
    description: str = a.get('description', a.get('summary', None))

    # Remove meta-info within {object} ... {/object} tag
    start = description.find('{object')
    if start >= 0:
        end = description.rfind("{/object}")
        description = description[:start] + description[end + 9:]

    p = description.find('{hdr')
    if p >= 0:
        # Kill this extra info
        description = description[:p]

    # Split effect onto its own line
    description = description.replace("; Effect", "\nEffect")

    lines = description.split('\n')

    # Short lines preceded by a blank and with text after it is a title
    for i in range(1, len(lines) - 1):
        if len(lines[i]) < 40 and not lines[i - 1] and lines[i + 1] and lines[i][0].isalnum():
            lines[i] = '**' + lines[i].title().strip() + '**'

    # A weird description error seems to have some info in twice:
    good = []
    for line in lines:
        line = embellish_description(line, level)
        if line and not line in good:
            good.append(line)

    # Reduce very long descriptions
    while sum(len(x) for x in good) > 1000:
        kill = None
        for line in good[1:]:
            if line[0].isalnum():
                kill = line
        if kill:
            good.remove(kill)
        else:
            break

    return [" - {}".format(line) for line in good]


def extract_weapons(items: List[Dict]) -> Optional[str]:
    lines = []

    for a in pop(items, 'Weapon') + pop(items, 'NaturalWep'):
        name = a['name']

        lines.append("\n\n.. title:: banner style=banner_{0}\n.. block:: style=back_{0}\n".format('black'))
        lines.append("{0}".format(name))

        for t in 'wpMelAttacks wpRngAttacks'.split():
            if t in a:
                for b in a[t].values():
                    lines.append(" - {0} Attack".format(b['name']))
                    attacks = b['attack'].split('|')
                    damages = b['damage'].split('|')
                    names = '#1 #2 #3'.split()
                    for name, atk, dam in zip(names, attacks, damages):
                        lines.append(" - *{0}*: **{1}** doing **{2}**".format(name, atk, dam))
        if 'items' in 'a':
            aspects = [v['name'] for v in a['items'].values()]
            if aspects:
                lines.append(" - Properties: {0}".format(" • ".join(aspects)))

    return "\n".join(lines)


def extract_abilities(items: List[Dict], type: str, title: str) -> Optional[str]:
    stats = pop(items, type, isAction=False)
    if not stats:
        return None

    return make_block_from(stats, title)


def extract_items(items: List[Dict], ) -> Optional[str]:
    stats = pop(items, 'Armor') + pop(items, 'Wand') + pop(items, 'MagicItem') + pop(items, 'Ammunition') \
            + pop(items, 'AlchemicalItem') + pop(items, 'NormalGear')
    if not stats:
        return None

    # Don't need the usual bolding
    return make_block_from(stats, "Items").replace('**', '')


def make_block_from(stats, title):
    txts = []
    for s in stats:
        if 'summary' in s:
            txts.append(" - **{0}**: {1}".format(s['name'], s['summary']))
        elif 'stNet' in s:
            txts.append(" - **{0}**: {1}".format(s['name'], s['stNet']))
        else:
            txts.append(" - **{0}**".format(s['name']))
    return title + '\n' + "\n".join(txts)


def extract_languages(items):
    stats = pop(items, 'Language')
    return " • ".join(sorted(s['name'] for s in stats))


def pop(items, type, isAction=None):
    stats = [i for i in items if i['compset'] == type]
    if isAction is not None:
        stats = [s for s in stats if isAction == ('Action' in s)]
    for s in stats:
        items.remove(s)
    return stats


def pop_item(items: List[Dict], type: str, name: str = None) -> Dict:
    for item in items:
        if item['compset'] == type and (name is None or item['name'] == name):
            items.remove(item)
            return item
    return {'name': ''}


def to_rst(actor: Dict, dir, main) -> str:
    gamevals = actor['gameValues']
    level = gamevals['actLevelNet']

    name = actor['name'].replace('-{0}'.format(level), '')  # Kill name suffix if any

    # Items in known order
    items = sorted_values(actor['items'])

    basic = basic_info(actor, items)

    stats = extract_stats(items)
    defenses = extract_defenses(items)
    skills = extract_skills(items)
    general = extract_abilities(items, 'Ability', 'General Abilities')
    movement = extract_abilities(items, 'Movement', 'Movement')
    feats = extract_feats(items)
    actions = extract_actions(items)
    weapons = extract_weapons(items)

    magic_items = extract_items(items)

    for item in items:
        print(item)

    results = [
        '-' * 40,
        ".. section:: stack stack:columns=3 padding=8\n.. title:: hidden\n.. block:: style=title",
        "{0}\n - **{1}** -- {2}".format(titled(name), name, level),
        ".. block:: default style=default",
        basic,
        stats, defenses,
        '-' * 40,
        ".. section:: stack padding=8 stack:columns=3\n.. block:: default style=default",
        portrait(dir, main),
        ".. title:: banner style=banner",
        movement, weapons, skills,
        '-' * 40,
        ".. section:: stack padding=8 stack:columns=3 stack:equal\n.. block:: default style=default",
        actions,
        '-' * 40,
        ".. section:: stack padding=8 stack:columns=2\n.. block:: default\n.. title:: banner style=banner\n"
        ".. block:: default style=default",
        magic_items,
        general, feats
    ]

    return "\n\n\n".join(s for s in results if s) + "\n\n\n"


def basic_info(actor, items):
    ancestry = pop_item(items, 'Ancestry')['name']
    character_class = pop_item(items, 'Class')['name']
    languages = extract_languages(items)
    align = actor['gameValues']['actAlignment']
    deity = pop_item(items, 'Deity')['name']
    focus_points = pop_item(items, 'Reserves', 'Focus Points').get('rvMax', 0)

    player = actor.get('player', None)
    socID = actor['gameValues'].get('actSocietyID', None)
    socChar = actor['gameValues'].get('actSocietyChar', None)

    hits = pop_item(items, 'Reserves', 'Hit Points')['rvMax']

    # Just remove them from the list
    _ = pop_item(items, 'Reserves', 'Hero Points')['rvMax']

    lines = []
    if player and socID and socChar:
        lines.append("**Player**: {} -- **Society ID**: {}-{}".format(player, socID, socChar))
    elif player:
        lines.append("**Player**: {}".format(player))
    elif socID and socChar:
        lines.append("**Society ID**: {}-{}".format(socID, socChar))

    lines.append("**Ancestry**: {0} -- **Class**: {1}".format(ancestry, character_class))

    if deity:
        lines.append("**Alignment**: {0} -- **Deity**: {1}".format(align, deity))
    else:
        lines.append("**Alignment**: {0}".format(align))

    lines.append("**Languages**: {0}".format(languages))
    lines.append("**Hero Points**: [X] [ ] [ ]")

    if focus_points:
        lines.append("**Focus Points**: " + "[X]" * int(focus_points))

    lines.append("**Hits [{0}]**: `".format(hits) + '_' * 50 + '`')
    lines.append('`' + '_' * 60 + '`')
    lines.append('`' + '_' * 60 + '`')

    return "Basic Information\n - " + "\n - ".join(lines)


def portrait(dir, main):
    files = list(dir.glob("_portrait.*"))
    if main and len(files) > 0:
        portrait = ".. image:: %s\n..\n" % files[0].name
    else:
        portrait = None
    return portrait


def watermark(dir):
    files = list(dir.glob("_watermark.*"))
    if len(files) > 0:
        return ' watermark=' + files[0].name
    else:
        return ''


def convert(input: Path) -> Path:
    with open(input, 'r') as f:
        base = json.load(f)
    actors = base['actors']

    characters = []
    for i in range(1, 2):
        actor = actors.get('actor.{}'.format(i), '')
        if not actor:
            break
        else:
            txt = to_rst(actor, input.parent, i == 1)
            characters.append(txt)

    out_file = input.parent.joinpath(input.stem + '.rst')
    with open(out_file, 'w') as out:
        out.write(".. page:: stack margin=0.333in%s\n\n" % watermark(input.parent)),
        for character in characters:
            out.write(character)
        # Style info
        out.write('-' * 40)
        out.write('\n\n\n')
        out.write(style_definitions())
    return out_file


def style_definitions():
    return dedent("""
        Styles
        ------

        default
            family=Gotham size=8 align=left 
        quote
            family=Baskerville size=7 align=center italic color=#020 opacity=0.8
        heavy
            bold color=black opacity=1
        title
            size=28 color=navy 

        banner
            background=#88c color=white
        banner_green
            inherit=banner background=green=
        banner_red
            inherit=banner background=red
        banner_black
            inherit=banner background=black
        banner_orange
            inherit=banner background=orange

        back
            size=8 family=Helvetica opacity=0.75 align=fill
        back_blue
            inherit=back background=#eef  borderColor=#88f
        back_orange
            inherit=back background=#fec borderColor=#fe8
        back_green
            inherit=back background=#efe borderColor=#7a7
        back_red
            inherit=back background=#fee borderColor=#f88
        back_black
            inherit=back background=#eee borderColor=#888


        attributes
            color=white family=Helvetica size=10
    """)
