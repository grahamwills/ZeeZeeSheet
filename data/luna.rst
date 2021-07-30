.. section: stack columns=3
.. title: banner style=title

**Lunathien Calenmaethor**
==========================

.. title: hidden

.. image:: data/images/13thAgelogo.png
   :height: 40
   :align: left
..


- Race     | Wood Elf
- Class     | Druid
- Gender    | Female
- Age       | 62

.. block: stat-circles style=heading-blue

Attributes
 - Strength     | 8  | -1
 - Constitution | 12 | +1
 - Dexterity    | 18 | +4
 - Intelligence | 8  | -1
 - Wisdom       | 18 | +1
 - Charisma     | 12 | +1

Defenses
 - AC | 18
 - PD | 14
 - MD | 14

---------------------------------------------------------------

.. title: banner style=heading_blue
.. section: stack columns=2

Level **2**
 - [X] Class: *Aspect - Bear*
 - [X] Feat:  *Ruination Spell*
 - [ ]

Hits: **28**        --  Staggered: **14**
 - Recoveries: [ ][ ][ ][ ][ ][ ][ ][ ] -- **2d6+1**

---------------------------------------------------------------

.. section: stack columns=3
.. title: hidden


Picture

.. image:: data/images/luna.jpg
..

.. title: banner style=heading_blue
.. style: blue


One Unique Thing
 - My firstborn will be the next Elf Queen

Icon Relationships
 - Elf Queen  | ♡ ♡
 - High Druid | ♡


Backgrounds
 - Princess of the Elven Courts     --  3
 - Inventive Explorer               --  4
 - Madly In Love with a Stupid Guy  --  4
 - -- *Further backgrounding (2 extra)*

Druid Talents
 - **Warrior Druid Initiate**: You are trained to survive the wilds and fight in combat.
   Your AC in light armor is 12 instead of 10 like most other druids.

 - **Terrain Caster Initiate**: Access to daily spells that you can only cast in one of the
   eight specific types of terrain

 - **Shifter Initiate**: Enables you to shift your form in two ways: scout form
   transformations into quick-moving animals for out of combat reconnaissance,
   and beast form transformations into combat-ready predators.

Druid Features
 - **Nature Talking**: Everybody knows that druids can talk with plants and animals.
   It may not always work, but druids won't admit it. The DC of speaking to nature
   depends on the information you are requesting and who you are speaking with.

 - **Wilderness Survival**: You never suffer from natural weather-related cold, heat,
   or exposure. You can go longer than most people without eating or drinking,
   but only a couple days longer.

.. title: banner style=heading_orange
.. style: orange

Elemental Pivot -- Encounter []
 - **Flexible Attack**      --      **Trigger**: Natural 18+
 - **Effect**: During your next turn, you can cast an Elemental Mastery
   at-will feat spell of your choice once as a quick action, even if
   you don’t normally know that spell.

Nature's Fury -- Encounter []
 - **Flexible Attack**      --      **Trigger**: Natural 2-5
 - **Effect**: Deal half damage

.. title: banner style=heading_red
.. style: red

Frost Touch (1) -- Encounter []
 - **Close Quarters Terrain Feat Spell**    --      **Nearby**
 - **Target**: One Creature                 --      **Attack**: +6 vs PD
 - **Hit**: 2d6+4 (3d6+4 to engaged enemy)
 - **Natural Even Miss**: Half damage
 - **Natural Odd Miss**: Level damage

Ruination (3) -- Encounter []
 - **Ranged Terrain Feat Spell**            --      **Nearby**
 - **Target**: All nearby enemies           --      **Attack**: +6 vs MD
 - **Hit**: 4d6 to all nearby enemies (once to each mook group)
 - **Note**: Targets the highest MD of all nearby enemies
   (don't have to be able to see them)

Elven Grace -- Wood Elf
 - At the beginning of each of your turns, roll a d6 to see if you get an extra
   standard action. If your roll is equal or lower than the escalation die,
   you get an extra standard action. Every time you gain a standard action,
   increase the die size

.. title: banner style=heading_green
.. style: green

Melee Basic Attack -- At-Will
 - **Standard Action**      --      **Nearby**
 - **Target**: One Creature --      **Attack**: +6 vs AC
 - **Hit**: d6+4 (axe)      --      **Miss**: level damage

Ranged Basic Attack -- At-Will
 - **Standard Action**      --      **Nearby**
 - **Target**: One Creature --      **Attack**: +6 vs AC
 - **Hit**: d6+4 (bow, axe) --      **Miss**: level damage

.. title: banner style=heading_black
.. style: black

Terrain Spell -- Daily per terrain
 - Various spells; each one is a separate daily, so a druid can cast
   each one once a day so long as they are in that sort of terrain

Beast Form -- Daily []
 - **Quick action**: You leave your humanoid form behind and assume the form of a deadly
   predator such as a wolf, panther, tiger, bear, wolverine or lion.

Beast Form Attack
 - **Melee Attack**:    -- +6 vs AC
 - *Natural Even Hit*: 2d10+4
 - *Natural Odd Hit*: 2d6+4
 - *Miss*: Repeat the attack against the same or a different target.
   This has no miss effect.

Aspect of the Bear -- Daily []
 - **Quick action**: Until the end of the battle, while in beast form,
   gain +2 to attack and damage against mooks and enemies of lower level

Scout Form Reconnaissance -- Daily []
 - **Retrospective Action**    -- DC 15/20/25
 - Scout Form Background: **d4+1**
 - *Normal success*: Gain +4 bonus to initiative this battle.
 - *Hard success*: As a free action at some point during the battle,
   you can grant one of your allies a re-roll on an attack roll or save.
 - *Ridiculously hard success*: GM chooses between giving a re-roll
   at some point during the battle, or a floating icon
   relationship result of 6 with a random icon.


---------------------------------------------------------------


Styles
------

default
  family=Baskerville size=8 align=fill
title
  size=44 color=darkGreen family=LoveYou

heading
  color=white background=black family=Helvetica
heading_blue
  inherit=heading background=navy borderColor=navy
heading_black
  inherit=heading background=black borderColor=black
heading_green
  inherit=heading background=green borderColor=green
heading_red
  inherit=heading background=red  borderColor=red
heading_orange
  inherit=heading background=orange  borderColor=orange

blue
  background=#eef
black
  background=#eee
green
  background=#efe
red
  background=#fee
orange
  background=#fec
