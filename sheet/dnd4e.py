from __future__ import annotations

import json
from collections import namedtuple
from math import ceil
from pathlib import Path
from textwrap import dedent
from typing import Dict, List, NamedTuple, Optional

import xmltodict

Weapon = namedtuple('Weapon', 'name bonus damage attack_stat defense conditions')

USAGE_TYPE = {
    'At-Will':   (1, 'green'),
    'Encounter': (2, 'red'),
    'Daily':     (3, 'black'),
    'Item':      (4, 'orange')
}

ACTION_TYPE = {
    'Standard':            (0, '●', 'Std'),
    'Movement':            (1, '◐', 'Move'),
    'Minor':               (2, '○', 'Minor'),
    'Free':                (3, '◌', 'Free'),
    'Opportunity':         (4, '⚡', 'Opp'),
    'Immediate Interrupt': (5, '⚡', 'Int'),
    'Immediate Reaction':  (6, '⚡', 'React'),
    '':                    (7, '', '--')
}


def read_rules_elements() -> Dict:
    d = xml_file_to_dict('../data/system/dnd4e_rules/combined.dnd40.xml')
    top = d['D20Rules']['RulesElement']
    result = dict((p['@internal-id'], p) for p in top)
    print("Read %d rules" % len(result))
    return result


def _find(txt: str, rule: Dict) -> Optional[str]:
    for item in rule['specific']:
        if item['@name'] == txt:
            return item.get('#text', None)
    return None


def _find_extras(rule: Dict) -> List[(str, str)]:
    pair = []
    for item in rule['specific']:
        if item['@name'].startswith(' '):
            pair.append((item['@name'].strip(), item['#text'].strip()))
    return pair


def _combine(target, range):
    if target:
        target = target.split('\n')[0]
    if range:
        range = range.split('\n')[0]

    if not target and not range:
        return None
    if target and not range:
        return target
    if not target and range:
        return range

    if range == 'Melee Weapon':
        return "%s (melee)" % target
    if range.startswith('Ranged'):
        return "%s within %s" % (target, range[7:].strip())
    if 'burst' in target:
        return target.replace('burst', range.lower())


class Power(NamedTuple):
    name: str
    usage: str
    action: str
    weapons: List[Weapon]

    def to_rst(self, rule: Dict, replacements: List[(str, str)]) -> str:

        source = rule['@source'].replace("Player's Handbook ", 'PHB').replace(" Magazine", '')
        display = _find('Display', rule)
        if display:
            display = display.replace(' Attack', '').replace(' Feature', '').replace(' Racial', '')

        attack_type = _find('Attack Type', rule)
        target = _find('Target', rule)
        keywords = _find('Keywords', rule)
        if keywords:
            keywords = keywords.replace(',', ' •')

        extras = _find_extras(rule)

        box = '' if self.usage == 'At-Will' else ' []'

        act_type = ACTION_TYPE[self.action][2] if len(self.name) + len(self.action) > 36 else self.action
        line_title = (ACTION_TYPE[self.action][1], self.name, act_type, box)

        atk_target = _combine(target, attack_type)
        if atk_target:
            atk_target = atk_target.replace("One, two, or three", "Up to three")

        conditions = None
        if self.weapons:
            wpn = self.weapons[0]
            line_attack = (wpn.bonus, wpn.defense, atk_target)
            conditions = wpn.conditions
        elif atk_target != 'Personal':
            line_attack = (None, None, atk_target)
        else:
            line_attack = None

        lines_main = []
        for key in "Requirement Trigger Hit Miss Effect".split():
            txt = _find(key, rule)
            if txt:
                txt = str(txt)
                for k, v in replacements:
                    txt = txt.replace(k, v)
                lines_main.append((key, txt.split('\n')[0].replace(' + ', '+')))
        lines_main += extras

        line_flavor = rule['Flavor'] if 'Flavor' in rule else None
        line_info = (keywords, display or '', source)
        color = USAGE_TYPE[self.usage][1]

        lines = [
            ".. title: banner style=banner_%s\n.. style: back_%s\n" % (color, color),
            "%s **%s** -- %s%s" % line_title,
            # " - %s -- %s" % line_usage if line_usage[1] else " - %s" % line_usage[0],
        ]

        if not line_attack:
            pass
        elif line_attack[0] and line_attack[2]:
            lines.append(" - **+%s** vs. **%s** -- %s" % line_attack)
        elif line_attack[0]:
            lines.append(" - **+%s** vs. **%s**" % (line_attack[0], line_attack[1]))
        elif line_attack[2]:
            lines.append(" - -- %s" % line_attack[2])

        for line in lines_main:
            lines.append(" - **%s**: %s" % line)
        if conditions:
            lines.append(" - %s" % conditions)

        if line_flavor:
            lines.append(" - *%s*" % line_flavor)

        if line_info[0]:
            lines.append(
                    " - <font size=6 color='gray'>%s • %s</font> -- <font size=6 color='gray'>%s</font>" % line_info)
        else:
            lines.append(" - <font size=6 color='gray'>%s</font> -- <font size=6 color='gray'>%s</font>" % (
                line_info[1], line_info[2]))

        return '\n'.join(line for line in lines if line)

    def order(self):
        return str(USAGE_TYPE[self.usage][0] * 10 + ACTION_TYPE[self.action][0]) + '_' + self.name


def _to_weapon(item) -> Weapon:
    return Weapon(
            item['@name'],
            item['AttackBonus'],
            item['Damage'],
            item['AttackStat'],
            item['Defense'],
            item.get('Conditions', '')
    )


def _to_power(item) -> Power:
    usage = '????'
    action = '????'
    for s in item['specific']:
        if s['@name'] == 'Power Usage':
            usage = s['#text']
        if s['@name'] == 'Action Type':
            action = s['#text'].replace(' Action', '')

    if 'Weapon' in item:
        wlist = item['Weapon']
        try:
            weapons = [_to_weapon(sub) for sub in wlist]
        except:
            # Just one item
            weapons = [_to_weapon(wlist)]
    else:
        weapons = []

    return Power(
            name=item['@name'],
            action=action,
            usage=usage,
            weapons=weapons
    )


def _to_item(item) -> Power:
    try:
        item = item[-1]
    except:
        pass

    return Power(
            name=item['@name'],
            action='',
            usage='Item',
            weapons=[]
    )


def _pair(base, name):
    return name, (base[name])


def _titled(name: str) -> str:
    return name + '\n' + '=' * len(name) + '\n'


def _block(items: []) -> Dict:
    d = dict()

    for item in items:
        value = int(item['@value'])
        alias = item['alias']
        try:
            name = alias['@name']
        except:
            name = alias[0]['@name']
        name = name.replace(' Defense', '')
        d[name] = value

    return d


def _to_rule_tuple(t):
    descr = t['specific']['#text'] if 'specific' in t else ''
    return t['@name'], descr


def _format_tuple_3_as_line(p):
    if len(p) < 2 or not p[2]:
        return " - %s: **%s**" % (p[0], p[1])
    else:
        return " - %s: **%s** -- %s" % p


class DnD4E:
    rule_elements: Dict
    character: Dict
    level: int
    half_level: int
    stats: Dict

    def __init__(self, base: Dict, rule_elements):
        self.rule_elements = rule_elements
        base = base['D20Character']
        self.character = base['CharacterSheet']
        self.level = int(base['CharacterSheet']['Details']['Level'])
        self.half_level = self.level // 2
        self.stats = _block(base['CharacterSheet']['StatBlock']['Stat'])

    def val(self, s) -> int:
        return self.stats[s]

    def print(self):
        print(json.dumps(self.character, indent=2))

    def rule_tuple(self, name):
        rule = self.rule(name)
        return name, rule[0], rule[1]

    def rule_tuple2(self, name):
        value = self.rule(name)
        assert not value[1]
        return name, value[0]

    def rule(self, rule_type: str) -> (str, str):
        targets = self.rules(rule_type)
        assert len(targets) == 1
        return targets[0]

    def rules(self, rule_type: str) -> List[(str, str)]:
        """ Returns a list of matching items, as tuples of name, description"""
        items = self.character['RulesElementTally']['RulesElement']
        return [_to_rule_tuple(t) for t in items if t['@type'] == rule_type]

    def character_title(self) -> str:
        return ".. style: title\n\n" + _titled('**' + self.character['Details']['name'] + '**')

    def character_details(self) -> str:
        base = self.character['Details']
        pairs = [
                    ('Class', self.join_names('CountsAsClass')),
                    _pair(base, 'Level'),
                    self.rule_tuple2('Gender'),
                    self.rule_tuple2('Alignment'),
                    self.rule_tuple2('Deity'),
                    ('Domain', self.join_names('Domain', join=', ')),

                    self.rule_tuple2('Vision'),
                    ('Passive Perception', self.stats['Passive Perception']),
                    ('Passive Insight', self.stats['Passive Insight']),
                    self.rule_tuple2('Size'),

                ] + [_pair(base, key) for key in "Experience Age Height Weight".split()]

        return "Basic Info\n" + "\n".join([" - %-20s: **%s**" % p for p in pairs if p[1]])

    def general(self) -> str:
        profs = [p[0] for p in self.rules('Proficiency')
                 if p[0].startswith('Armor') or p[0].startswith('Implement') or not '(' in p[0]]

        tuples = [self.rule_tuple(p) for p in "Class Race Background Theme".split()] + \
                 [
                     ('Languages', self.join_names('Language'), ''),
                     ('Proficiencies', " • ".join(p.replace('Proficiency ', '') for p in profs), ''),
                 ]

        return "General Information\n" + "\n".join([_format_tuple_3_as_line(p) for p in tuples])

    def stat_block(self):
        stats = "Strength Constitution Dexterity Intelligence Wisdom Charisma".split()
        tuples = [(name, "**%d**" % self.val(name), (self.val(name) - 10) // 2 + self.half_level) for name in stats]
        return 'Ability Scores\n' + "\n".join([" - %-12s | %6s | *+%s*" % p for p in tuples])

    def skills(self):
        skills = []
        for item in self.character['StatBlock']['Stat']:
            value = int(item['@value'])
            try:
                name = item['alias'][0]['@name']
            except:
                name = item['alias']['@name']

            if not name + ' Trained' in self.stats:
                continue

            trained = self.stats[name + ' Trained'] > 0

            skills.append((value, name, trained))
        skills.sort(key=lambda x: x[1])
        skills = [(value, '**%s**' % name if trained else name) for value, name, trained in skills]
        return 'Skills\n' + "\n".join([" - %16s | **%d**" % (s[1], s[0]) for s in skills])

    def class_features(self):
        rules = self.rules('Class Feature')
        rules.sort(key=lambda x: ('A' if x[1] else 'B') + x[0])
        parts = [("**%s**: %s" % (b, c)) for b, c in rules if c]
        return 'Class Features\n' + "\n".join([" - " + s for s in parts])

    def racial_features(self):
        rules = self.rules('Racial Trait')
        rules.sort(key=lambda x: ('A' if x[1] else 'B') + x[0])
        parts = [("**%s**: %s" % (b, c)) for b, c in rules if c]
        return 'Racial Features\n' + "\n".join([" - " + s for s in parts])

    def feats(self):
        rules = self.rules('Feat')
        rules.sort(key=lambda x: ('A' if x[1] else 'B') + x[0])
        parts = [("**%s**: %s" % (b, c)) for b, c in rules if c]
        return 'Feat\n' + "\n".join([" - " + s for s in parts])

    def defenses(self):
        stats = "AC Fortitude Reflex Will Initiative Speed".split()
        tuples = [(name, "**%d**" % self.val(name)) for name in stats]
        return 'Combat\n' + "\n".join([" - %-12s | %6s" % p for p in tuples])

    def hits(self):
        hits = self.val('Hit Points')
        surges = self.val('Healing Surges')

        saves = int(self.stats['Death Saves Count'])
        save_bonus = int(self.stats['Death Saving Throws'])

        return "Combat Information\n" \
               + " - Action Points -- [][][][][]\n" \
               + " - Max HP: **%d** -- *bloodied*: %d\n" % (hits, hits // 2) \
               + " - `_________________________________________________`\n" \
               + " - `_________________________________________________`\n" \
               + " - Surges: " + '[ ]' * 5 + ' ' + '[ ]' * (surges - 5) + " -- value: %d\n" % (hits // 4) \
               + " - Deaths Saving Throws: " + '[]' * saves + ' --  bonus: **+%d**' % save_bonus

    def power_cards(self) -> List[str]:

        power_mapping = self.power_mappings()

        powers = [_to_power(s) for s in self.character['PowerStats']['Power']]
        powers.sort(key=lambda p: p.order())

        items = [p.to_rst(power_mapping.get(p.name), self.make_replacements(p)) for p in powers] \
                + [self.item_to_rst(item) for item in self.item_list()]

        EVERY = 0
        for pages in range(2, 10):
            EVERY = ceil(len(items) / pages)
            if EVERY < 16:
                break
        for p in range(EVERY, len(items), EVERY):
            items.insert(p, self.divider())

        return items

    def to_rst(self):
        front_page = [
            ".. section: stack columns=3\n.. style: title",
            self.character_title(),

            ".. block: default\n.. title: banner style=banner\n.. style: back",
            self.hits(),

            ".. title: hidden\n.. block: key-values style=banner_green rows=100\n.. style: attributes",
            self.stat_block(),

            ".. block: key-values style=banner_red rows=100",
            self.defenses(),

            self.divider(),

            ".. section: stack columns=2\n.. block: default\n.. title: banner style=banner\n.. style: default",

            self.skills(),
            self.character_details(),
            self.general(),

            self.class_features(),
            self.racial_features(),
            self.feats(),
            self.divider(),

            ".. section: stack columns=3 equal=True",

        ]
        return "\n\n\n".join(front_page) \
               + '\n\n\n----------------------------------------\n\n\n' \
               + "\n\n\n".join(self.power_cards()) \
               + '\n\n\n' + self.divider() + '\n\n\n' + self.style_definitions()

    def _stat_of(self, base) -> (str, int, int):
        try:
            value = int(base['@value'])
            alias = base['alias']
            name = alias[0]['@name']
            bonus = (value - 10) // 2 + self.half_level
            return name, '**' + str(value) + '**', bonus
        except:
            return None, None, None

    def join_names(self, rule_type: str, join: str = ' • '):
        return join.join(p[0] for p in self.rules(rule_type))

    def power_mappings(self) -> Dict:
        items = self.character['RulesElementTally']['RulesElement']
        return dict([(t['@name'], self.rule_elements[t['@internal-id']]) for t in items if t['@type'] == 'Power'])

    def item_list(self) -> [List[str]]:
        items = self.character['LootTally']['loot']
        result = []
        for item in items:
            if item['@count'] == '0':
                continue
            element = item['RulesElement']
            try:
                result.append([e['@internal-id'] for e in element])
            except:
                result.append([element['@internal-id']])
        return result

    def divider(self) -> str:
        return '-' * 40

    def style_definitions(self):
        return dedent("""
            Styles
            ------
            
            default
                family=Gotham size=8 align=left
            title
                size=28
            back
                background=#ffe borderColor=#ddc
            
            banner
                background=navy color=white borderColor=navy
            banner_green
                inherit=banner background=green borderColor=#7a7
            banner_red
                inherit=banner background=red borderColor=#f88
            banner_black
                inherit=banner background=black borderColor=#888
            banner_blue
                inherit=banner background=navy borderColor=#88f
            banner_orange
                inherit=banner background=orange borderColor=#fe8
            
            back
                size=8 family=Helvetica
            back_blue
                inherit=back background=#eef
            back_orange
                inherit=back background=#fec
            back_green
                inherit=back background=#efe
            back_red
                inherit=back background=#fee
            back_black
                inherit=back background=#eee

            
            attributes
                color=white family=Helvetica size=10
        """)

    def make_replacements(self, p: Power) -> List[(str, str)]:
        """ replace common text in hits, misses and effects"""

        if p.weapons and p.weapons[0].damage:
            damage = p.weapons[0].damage
            plus = p.weapons[0].attack_stat
            count = int(damage[0])
            full_damage = damage[1:]
            split = full_damage.split('+')
            dice = split[0]
            if len(split) > 1:
                bonus = "+" + split[1]
            else:
                bonus = ''

            reps = []
            for i in range(1, 10):
                reps.append(("%d[W] + %s modifier" % (i, plus), "%d%s%s" % (i * count, dice, bonus)))
                reps.append(("%d[W]" % i, "%d%s%s" % (i * count, dice, bonus)))
            reps.append(("your %s modifier" % plus, bonus[1:]))
            reps.append(("%s modifier" % plus, bonus[1:]))
            return reps

        else:
            stats = "Strength Constitution Dexterity Intelligence Wisdom Charisma".split()
            return [(name + ' modifier', str((self.val(name) - 10) // 2)) for name in stats]

    def item_to_rst(self, ids: List[str]):

        # Merge rules for each ID
        rule = dict()
        for id in ids:
            rule.update(self.rule_elements[id])

        name = rule['@name'].replace(' (heroic tier)', '').strip()
        item_type = _find('Magic Item Type', rule)
        slot = _find('Item Slot', rule)
        line_flavor = rule['Flavor']
        price = _find('Gold', rule)
        rarity = _find('Rarity', rule)

        # Power needs special care, example:
        #   Power (Daily): Free Action. Trigger: You miss with a melee attack using this staff. Effect:
        #   Reroll the attack roll and use the second result, even if it is lower than the first.
        power = _find('Power', rule)
        if power:
            rparen = power.index('):')
            usage = power[7:rparen].strip()
            txt = power[rparen + 2:].strip()
            dot = txt.index('.')
            action = txt[:dot].strip().replace(' Action', '')
            power = (action, txt[dot + 1:].replace('Trigger', '*Trigger*').replace('Effect', '*Effect*'))
            box = '' if usage == 'At-Will' else ' []'
            info = ACTION_TYPE[action]
            line_title = "%s **%s** -- %s/%s%s" % (info[1], name, info[2], usage, box)
        else:
            line_title = "**%s** -- %s" % (name, slot or item_type)

        if '@source' in rule:
            source = rule['@source'].replace("Player's Handbook ", 'PHB').replace(" Magazine", '')
        else:
            source = ''

        line_info = (rarity, price, slot or item_type)

        lines_main = []
        for key in "Enhancement Property Critical".split():
            txt = _find(key, rule)
            if txt:
                lines_main.append((key, txt))
        if power:
            lines_main.append(power)

        color = USAGE_TYPE['Item'][1]

        lines = [
            ".. title: banner style=banner_%s\n.. style: back_%s\n" % (color, color),
            line_title,
            " - %s • %sgp -- %s" % line_info,
        ]

        for line in lines_main:
            lines.append(" - **%s**: %s" % line)
        lines.append(" - *%s*" % line_flavor)

        if source:
            lines.append(" - -- <font size=6 color='gray'>%s</font>" % source)

        return '\n'.join(line for line in lines if line)


def read_dnd4e(f, rules: Dict) -> DnD4E:
    dict = xml_file_to_dict(f)
    return DnD4E(dict, rules)


def xml_file_to_dict(filename):
    with open(filename, 'r') as f:
        data = f.read()
    dict = xmltodict.parse(data, process_namespaces=True, )
    return dict

def convert(file:Path) -> Path:
    rules = read_rules_elements()
    dnd = read_dnd4e(file, rules)
    out = dnd.to_rst()
    out_file = file.parent.joinpath(file.stem+'.rst')

    with open(out_file, 'w') as file:
        file.write(out)
    return out_file


if __name__ == '__main__':

    rules = read_rules_elements()

    dnd = read_dnd4e('../data/import/Grumph-5.dnd4e', rules)

    out = dnd.to_rst()

    with open('../data/characters/Grumph/grumph.rst', 'w') as file:
        file.write(out)
