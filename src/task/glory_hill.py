"""Visible PC board geometry and basic planning for Peaks of Prestige."""
from dataclasses import dataclass, replace
from collections.abc import Callable
import re

import cv2
import numpy as np


WIDTH, HEIGHT = 1600, 900
SLOTS = (330, 483, 637, 800, 964, 1117, 1269)
FRONT_FIRST = (2, 1, 0, 4, 5, 6)
SLOT_Y = 603
MORPH = (800, SLOT_Y)
HAND_Y = 870
RECYCLE = (1545, 449)
ROUND_RE = re.compile(r"回合\s*[:：]?\s*([1-8])\s*[/／]\s*8$")
COUNT_RE = re.compile(r"^([0-4])\s*[/／]\s*4$")
ENERGY_RE = re.compile(r"^([0-9]{1,2})\s*[/／]\s*[0-9]{1,2}$")
SPEED_RE = re.compile(r"^([1-9](?:[.．][0-9])?|10(?:[.．]0)?)\s*[Xx×]$")


@dataclass(frozen=True)
class Card:
    x: int
    cost: int | None
    damage: int
    name: str = ""


@dataclass(frozen=True)
class Board:
    round: int
    count: int
    energy: int
    occupied: tuple[bool, ...]
    hand: tuple[Card, ...]
    stages: tuple[int | None, ...] = ()
    field_names: tuple[str, ...] = ()
    wing_guard: frozenset[int] = frozenset()
    tough: frozenset[int] = frozenset()
    taunt: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Move:
    kind: str
    card: Card | None
    slot: int | None = None


def board_image(frame):
    if frame is None or abs(frame.shape[1] / frame.shape[0] - 16 / 9) > .008:
        return None
    return cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)


def hand_headers(image, header_y=825):
    """Return top-border centers and heights. A partially obscured row is rejected."""
    left, right = 105, 1495
    candidates = []
    for y in range(header_y, header_y + 10):
        bright = image[y, left:right].min(axis=1) > 132
        edges = np.flatnonzero(np.diff(np.r_[False, bright, False])).reshape(-1, 2)
        runs = [(left + a, b - a) for a, b in edges if 132 <= b - a <= 161]
        if not runs:
            continue
        centers = tuple(int(x + width // 2) for x, width in runs)
        # In this layout a settled hand is symmetric around the game center.
        # Partial matches also occur just below the top edge of several cards.
        if abs(centers[0] + centers[-1] - WIDTH) > 9:
            continue
        if any(not 157 <= b - a <= 168 for a, b in zip(centers, centers[1:])):
            continue
        candidates.append((len(runs), sum(width for _, width in runs), -y, centers))
    if not candidates:
        return ()
    _, _, neg_y, centers = max(candidates)
    return tuple((x, -neg_y) for x in centers)


def hand_is_empty(image):
    # A truly empty tray exposes the dark background, even with the hand raised.
    # Do not treat a failed header match on a raised or moving card as empty.
    tray = image[834:890, 240:1220].max(axis=2)
    return bool(np.count_nonzero(tray > 95) < 40)


def cost_image(image, x, y):
    # Isolate the beige center numeral from the rest of the card header.
    region = image[y + 2:y + 18, x - 8:x + 8].max(axis=2)
    glyph = np.where(region > 110, 0, 255).astype(np.uint8)
    glyph = cv2.resize(glyph, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    padded = cv2.copyMakeBorder(glyph, 16, 16, 28, 28, cv2.BORDER_CONSTANT, value=255)
    return cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)


def damage_pips(image, x, y):
    region = image[y + 26:y + 34, x - 29:x + 30].astype(np.int16)
    blue, green, red = np.moveaxis(region, 2, 0)
    gold = (red >= 200) & (green >= 168) & (red - blue >= 45) & (green - blue >= 24)
    count, _, stats, _ = cv2.connectedComponentsWithStats(gold.astype(np.uint8))
    return sum(10 <= int(stats[i, cv2.CC_STAT_AREA]) <= 60 for i in range(1, count))


def occupied_slots(image, header_y=504):
    # Occupied slots have light card corners above an opaque dark stat header.
    # Empty slots show the pale board all the way across that region.
    occupied = []
    for x in SLOTS:
        header = image[header_y:header_y + 12, x - 56:x + 56]
        dark = (header.max(axis=2) < 100).mean()
        pale = (header.min(axis=2) > 145).mean()
        occupied.append(bool(dark > .44 and pale > .025))
    return tuple(occupied)


PIG = '碎獠猪'
LIZARD = '绿熔蜥（稚形）'
ROCK = '裂变幼岩'
BEAR = '箭簇熊'
KNIGHT = '幻昼骑士'
SCORPION = '晶螯蝎'
CLERIC = '赦罪节使'
WARRIOR = '鸣泣战士'
CHOP = '咔嚓嚓'
VANGUARD = '先锋幼岩'
CORE = '燎照之骑'
CONSTRUCT = '异构武装'
MACHINE = '游鳞机枢'
NOBLE = '毒冠贵族'
PUFFER = '咕咕河豚'
CHIME = '叮咚咚'
RIPPER = '车刃镰'
APE = '飞廉之猩'
HERON = '青羽鹭'
HUNTER = '巡徊猎手'
PUPPET = '工头布偶'
TURTLE = '寒霜陆龟'
RIPPER_CARDS = (RIPPER, APE, HERON, HUNTER, PUPPET, TURTLE, BEAR, MACHINE, VANGUARD, PIG, PUFFER)
RIPPER_FRONT, RIPPER_BACK = FRONT_FIRST[:3], FRONT_FIRST[3:]
FUSION_CARDS = (CONSTRUCT, MACHINE, NOBLE, BEAR, PUFFER, CHIME, WARRIOR, LIZARD, VANGUARD, PIG, SCORPION)
CARD_NAMES = (PIG, LIZARD, ROCK, BEAR, KNIGHT, SCORPION, CLERIC, WARRIOR, CHOP, VANGUARD, CORE)
DEPLOY_ORDER = (LIZARD, WARRIOR, CLERIC, SCORPION, VANGUARD, CHOP, ROCK, PIG)
TUNING_MATERIAL = (ROCK, CHOP, LIZARD, WARRIOR, SCORPION, VANGUARD, CLERIC, PIG)
WING_BASES = (LIZARD, WARRIOR)


def unsupported_cards(board, allowed=CARD_NAMES):
    names = [card.name for card in board.hand]
    names.extend(name for name, occupied in zip(board.field_names, board.occupied) if occupied)
    return set(names).difference(allowed)


def choose_move(board):
    """Plan one action for the observed Inferno Rider deck, then read the board again."""
    if len(board.field_names) != len(SLOTS) or unsupported_cards(board):
        raise ValueError('card profile is incomplete or unsupported')

    def find(name, cost=None):
        return next((card for card in board.hand if card.name == name and
                     (cost is None or card.cost == cost)), None)

    empty = next((slot for slot in FRONT_FIRST if not board.occupied[slot]), None)
    can_deploy = empty is not None and board.count < 4
    core = find(CORE)
    if core and CORE not in board.field_names:
        if can_deploy:
            # Core summons are free regardless of the number printed on the card.
            return Move('core', core, empty)
        low_value_back_slot = next((slot for slot in reversed(FRONT_FIRST[3:])
                                    if board.stages[slot] == 1 and board.field_names[slot] in
                                    (SCORPION, ROCK, PIG)), None)
        if low_value_back_slot is not None:
            return Move('recycle_board', None, low_value_back_slot)

    pig, bear, knight = find(PIG, 1), find(BEAR, 3), find(KNIGHT, 3)
    material = next((card for name in TUNING_MATERIAL if name != PIG
                     if (card := find(name, 1)) is not None), None)
    wing_stage_two = next((slot for slot in FRONT_FIRST if board.stages[slot] == 2
                           and slot in board.wing_guard), None)
    wing_base = next((slot for slot in FRONT_FIRST if board.stages[slot] == 1
                      and board.field_names[slot] in WING_BASES), None)

    if bear and wing_stage_two is not None:
        if board.energy >= 3:
            return Move('tune', bear, wing_stage_two)
        if pig and board.energy >= 1:
            return Move('morph', pig)
    if bear and wing_base is not None and material:
        if pig and 1 <= board.energy < 4:
            return Move('morph', pig)
        if board.energy >= 4:
            return Move('tune', material, wing_base)

    deploy = next((card for name in DEPLOY_ORDER if (card := find(name, 1)) is not None), None)
    if can_deploy and deploy and board.energy >= 1:
        if pig and deploy != pig and board.energy < 4:
            return Move('morph', pig)
        return Move('summon', deploy, empty)

    # Consider higher-value upgrades once the spaces have been filled.
    stage_two = next((slot for slot in FRONT_FIRST if board.stages[slot] == 2), None)
    upgrade = bear or knight
    if upgrade and stage_two is not None:
        if board.energy >= 3:
            return Move('tune', upgrade, stage_two)
        if pig and board.energy >= 1:
            return Move('morph', pig)
        if board.energy == 2 and material:
            return Move('recycle', material)
    if material and board.energy >= 1:
        front_taunt = next((slot for slot in FRONT_FIRST[:3] if board.stages[slot] == 1
                            and board.field_names[slot] == SCORPION), None)
        base = next((slot for slot in (wing_base, front_taunt) if slot is not None), None)
        if base is not None:
            return Move('tune', material, base)
    if material and not board.energy and (can_deploy or stage_two is not None and upgrade):
        # Use a spare card only if a later action stays available after recycling.
        if pig or can_deploy and deploy and deploy != material:
            return Move('recycle', material)
    return None


def choose_fusion_move(board, excluded_tunes=frozenset()):
    """Deploy the Ice/Fusion deck against early enemy pressure."""
    if len(board.field_names) != len(SLOTS) or unsupported_cards(board, FUSION_CARDS):
        raise ValueError('card profile is incomplete or unsupported')

    def first(names):
        return next((card for name in names for card in board.hand if card.name == name), None)

    front, back = FRONT_FIRST[:3], FRONT_FIRST[3:]
    front_space = next((slot for slot in front if not board.occupied[slot]), None)
    back_space = next((slot for slot in back if not board.occupied[slot]), None)
    empty = front_space if front_space is not None else back_space
    core = first((CONSTRUCT,))
    if core and CONSTRUCT not in board.field_names:
        if board.count < 4 and empty is not None:
            return Move('core', core, empty)
        expendable = next((slot for slot in (*back, *front) if board.stages[slot] == 1
                           and board.field_names[slot] != WARRIOR), None)
        if expendable is not None:
            return Move('recycle_board', None, expendable)

    pig = first((PIG,))
    has_upgrade = first((NOBLE, BEAR, MACHINE)) is not None
    cheap_cards = sum(card.cost == 1 and card != pig for card in board.hand)
    can_spend_pig_energy = (cheap_cards >= 2 or cheap_cards and board.count > 0
                            or has_upgrade and 2 in board.stages)
    if pig and 1 <= board.energy < 6 and can_spend_pig_energy:
        return Move('morph', pig)

    stage_two = [slot for slot in FRONT_FIRST if board.stages[slot] == 2]
    stage_one = [slot for slot in FRONT_FIRST if board.stages[slot] == 1]
    if stage_two:
        def upgrade_score(card, slot):
            wing = slot in board.wing_guard or board.field_names[slot] in WING_BASES
            taunt = slot in board.taunt or board.field_names[slot] in (PUFFER, SCORPION)
            tough = slot in board.tough or board.field_names[slot] == PIG
            if card.name == MACHINE:
                return 12 if taunt and tough and slot in front else 5 + 2 * tough
            if card.name == BEAR:
                return 10 if wing else 5
            return 9 if board.round <= 4 else 6

        upgrades = [(upgrade_score(card, slot), card, slot) for slot in stage_two for card in board.hand
                    if card.name in (MACHINE, NOBLE, BEAR) and (card.name, slot) not in excluded_tunes]
        if upgrades:
            _, upgrade, slot = max(upgrades, key=lambda entry: entry[0])
            if board.energy >= 3:
                return Move('tune', upgrade, slot)
            if board.energy == 2:
                spare = next((card for card in board.hand if card != upgrade and card.cost == 3), None)
                if spare is None and board.round <= 4 and not stage_one:
                    spare = first((VANGUARD, CHIME, SCORPION, PUFFER))
                if spare:
                    return Move('recycle', spare)

    if board.energy >= 1 and stage_one:
        def tune_score(card, slot):
            base = board.field_names[slot]
            value = {CHIME: 5, PIG: 5, PUFFER: 5, SCORPION: 5, LIZARD: 4, WARRIOR: 3,
                     VANGUARD: 1}.get(base, 0)
            if base == WARRIOR:
                value -= 3  # Preserve the recurring draw until worthwhile to replace.
            if base in (PUFFER, SCORPION, CHIME) and slot not in front:
                value -= 1
            value += {LIZARD: 5, PUFFER: 3, SCORPION: 3, WARRIOR: 3, VANGUARD: 3}.get(card.name, 0)
            if base == PIG and card.name in (PUFFER, SCORPION):
                value += 3
            return value

        tunes = [(tune_score(card, slot), card, slot) for slot in stage_one for card in board.hand
                 if card.cost == 1 and card.name != PIG and (card.name, slot) not in excluded_tunes]
        if tunes:
            score, material, slot = max(tunes, key=lambda entry: entry[0])
            if score >= 7 or board.count == 1 and empty is not None and cheap_cards == 1 and has_upgrade or board.count >= 4 or has_upgrade and board.energy >= 4:
                return Move('tune', material, slot)

    if board.count < 4 and empty is not None and board.energy >= 1:
        if not any(board.occupied[slot] for slot in front):
            order = (CHIME, PUFFER, LIZARD, SCORPION, PIG, VANGUARD, WARRIOR)
            if pig and cheap_cards == 1 and has_upgrade:
                order = (PIG, *order)
        else:
            order = (WARRIOR, LIZARD, CHIME, PUFFER, SCORPION, VANGUARD, PIG)
        deploy = first(order)
        if deploy:
            slot = back_space if deploy.name == WARRIOR and back_space is not None else empty
            return Move('summon', deploy, slot)
    return None


def choose_ripper_move(board, life=None, deck_count=None, used_turtle=False, prioritize_rippers=False):
    """Build the rear Ripper stack and keep adjacent front slots available for the core."""
    if len(board.field_names) != len(SLOTS) or unsupported_cards(board, RIPPER_CARDS):
        raise ValueError('card profile is incomplete or unsupported')
    can_draw_three = deck_count is None or deck_count >= 3

    def first(*names):
        return next((card for name in names for card in board.hand if card.name == name), None)

    def empty(slots):
        return next((s for s in slots if not board.occupied[s]), None)

    front, back = empty(RIPPER_FRONT), empty(RIPPER_BACK)
    space = front if front is not None else back
    ape, ripper, pig = first(APE), first(RIPPER), first(PIG)
    can_deploy = board.count < 4 and space is not None
    if ape:
        if can_deploy:
            return Move('core', ape, front if front is not None else space)
        disposable = next((s for s in (*RIPPER_FRONT, *RIPPER_BACK) if board.stages[s] in (1, 2)), None)
        if disposable is not None:
            return Move('recycle_board', None, disposable)
    if not board.energy:
        return None
    heron = first(HERON)
    if board.energy >= 3 and life is not None and life <= 18 and heron:
        return Move('morph', heron)
    if pig and board.energy <= 4 and (len(board.hand) >= 3 or prioritize_rippers and ripper):
        return Move('morph', pig)
    rear_material = [s for s in RIPPER_BACK if board.stages[s] in (1, 2)]
    rear_ready = next((s for s in rear_material if board.stages[s] == 2), None)
    if ripper and rear_ready is not None:
        if board.energy >= 3:
            return Move('tune', ripper, rear_ready)
        spare_order = (BEAR, HERON, PUPPET, MACHINE)
        if prioritize_rippers:
            spare_order += (PUFFER, TURTLE)
        if board.energy == 2:
            spare = first(*spare_order)
            if spare:
                return Move('recycle', spare)
        if prioritize_rippers and board.energy == 1:
            # Commit to a two-card recovery only if both spares are already visible.
            if sum(card.name in spare_order for card in board.hand) >= 2:
                return Move('recycle', first(*spare_order))
    if prioritize_rippers and not ripper and board.field_names.count(RIPPER) == 1:
        # Use a front-row taunt and draw two cards while looking for the second Ripper.
        front_puffer = next((s for s in RIPPER_FRONT
                             if board.field_names[s] == PUFFER and board.stages[s] == 1), None)
        material = first(HUNTER, VANGUARD)
        if front_puffer is not None and material:
            return Move('tune', material, front_puffer)
        puffer = first(PUFFER)
        if puffer and material and board.energy >= 2 and can_deploy and all(
            not board.occupied[s] for s in RIPPER_FRONT
        ):
            return Move('summon', puffer, front)
    rear_base = next((s for s in rear_material if board.stages[s] == 1), None)
    if rear_base is not None:
        base = board.field_names[rear_base]
        material = first(HUNTER, VANGUARD, TURTLE, PUFFER, PUPPET) if base == VANGUARD else first(VANGUARD)
        if material:
            return Move('tune', material, rear_base)
    if back is not None and can_deploy and not rear_material and board.field_names.count(RIPPER) < 2:
        if prioritize_rippers and first(VANGUARD) and (base := first(HUNTER, PIG)):
            # Preserve toughness from the base and inherit stealth from Vanguard when tuning.
            return Move('summon', base, back)
        vanguard = first(VANGUARD)
        if vanguard:
            return Move('summon', vanguard, back)
        base = first(HUNTER, PUPPET, PUFFER, TURTLE)
        if base and (ripper or not any(board.occupied[s] for s in RIPPER_BACK)):
            if base.name == PUPPET and can_draw_three and not ripper and board.energy >= 2:
                return Move('morph', base)
            return Move('summon', base, back)
    machine, bear = first(MACHINE), first(BEAR)
    front_ready = next((s for s in RIPPER_FRONT if board.stages[s] == 2), None)
    if board.energy >= 3 and front_ready is not None and (machine or bear):
        return Move('tune', machine or bear, front_ready)
    front_base = next((s for s in RIPPER_FRONT if board.stages[s] == 1), None)
    if front_base is not None:
        base = board.field_names[front_base]
        material = first(HUNTER, PUFFER, VANGUARD, PUPPET) if base == PUFFER else first(PUFFER, HUNTER, VANGUARD)
        if material and (machine or bear or board.count >= 3 or base == PUFFER):
            return Move('tune', material, front_base)
    turtle = first(TURTLE)
    if turtle and not used_turtle and board.round <= 5 and (board.round <= 3 or life is None or life <= 22):
        return Move('morph', turtle)
    puppet = first(PUPPET)
    if puppet and can_draw_three and len(board.hand) <= 5 and board.energy >= 1:
        return Move('morph', puppet)
    front_deploy_limit = 2 if APE not in board.field_names else 3
    if prioritize_rippers and board.field_names.count(RIPPER) < 2 and board.round <= 3:
        front_deploy_limit = 1
    if can_deploy and front is not None and board.count <= front_deploy_limit:
        base = first(PUFFER, HUNTER, TURTLE, PUPPET, VANGUARD, PIG)
        if base:
            return Move('summon', base, front)
    return None


@dataclass(frozen=True)
class DuelPlan:
    profile: str
    deck: str
    duelist: str
    duelist_tile: tuple[int, int]
    doctrine: str
    doctrine_tile: tuple[int, int]


RIPPER_PLAN = DuelPlan('双镰坚守（坎特蕾拉）', '双镰坚守', '坎特蕾拉', (263, 278), '适者生存', (1513, 237))
BRANT_PLAN = replace(RIPPER_PLAN, profile='双镰坚守（布兰特）')
FUSION_PLAN = DuelPlan('冰火调谐（珂莱塔）', '冰火调谐', '珂莱塔', (263, 556), '致命弱点', (1513, 237))

# These choices refer to saved decks. They never create or overwrite a deck.
OPPONENT_PLANS = {'布兰特': BRANT_PLAN, '夏空': FUSION_PLAN, '露帕': RIPPER_PLAN}


def challenge_plan(opponent, current_deck):
    return OPPONENT_PLANS.get(opponent) or next(
        (plan for plan in (RIPPER_PLAN, FUSION_PLAN) if plan.deck == current_deck), None)


@dataclass(frozen=True)
class DuelRules:
    round_limit: int
    round_pattern: re.Pattern
    verify_move: Callable[[Board, Move, Board | None], bool]


def classic_move_verified(before, move, after):
    if not after or after.round != before.round:
        return False
    if move.kind == 'recycle_board':
        return after.energy == before.energy + 1 and after.count == before.count - 1 and not after.occupied[move.slot]
    if move.kind == 'core':
        return after.energy == before.energy and after.count == before.count + 1 and after.occupied[move.slot]
    if move.kind == 'recycle':
        return after.energy == before.energy + 1 and after.count == before.count
    if move.kind == 'morph':
        delta = 2 if move.card.name == PIG else -move.card.cost
        return after.energy == before.energy + delta and after.count == before.count
    if move.kind == 'tune':
        return (after.energy == before.energy - move.card.cost and after.count == before.count
                and after.stages[move.slot] == before.stages[move.slot] + move.card.cost)
    return (after.energy == before.energy - move.card.cost and after.count == before.count + 1
            and after.occupied[move.slot])


CLASSIC_RULES = DuelRules(8, ROUND_RE, classic_move_verified)
RULES_BY_EVENT = {'classic': CLASSIC_RULES}


def detect_duel_event(text):
    if any(marker in text for marker in ('激斗重燃', '领域', '奇藏')):
        return 'rekindled'
    if re.search(r'第\s*8\s*回合', text):
        return 'classic'
    return None


def card_fingerprint(image, x, y, field=False):
    """Read the center of the illustration without the hover border or stats."""
    artwork = image[y + 40:y + (117 if field else 64), x - 42:x + 42]
    if not artwork.size:
        return None
    return cv2.resize(artwork, (28, 8), interpolation=cv2.INTER_AREA)


def same_card_art(first, second):
    if first is None or second is None:
        return False
    difference = cv2.absdiff(first, second)
    return float(difference.mean()) <= 4 and float(np.quantile(difference, .95)) <= 14
