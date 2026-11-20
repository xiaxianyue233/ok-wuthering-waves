from dataclasses import replace
import re
from time import monotonic

from ok import BaseTask
from ok.device.interaction_methods.pynput import PynputInteraction

from src.task.glory_hill import (
    APE, BEAR, Board, CARD_NAMES, COUNT_RE, Card, ENERGY_RE, FUSION_CARDS, HAND_Y, HEIGHT, MACHINE,
    MORPH, PIG, RECYCLE, RIPPER, RIPPER_BACK, RIPPER_CARDS, RIPPER_FRONT, SLOT_Y, SLOTS,
    SPEED_RE, TURTLE, WIDTH, board_image, choose_fusion_move, choose_move, choose_ripper_move,
    cost_image, damage_pips, hand_headers, hand_is_empty, occupied_slots, unsupported_cards,
    BRANT_PLAN, FUSION_PLAN, RIPPER_PLAN, CLASSIC_RULES, RULES_BY_EVENT, card_fingerprint, challenge_plan,
    detect_duel_event, same_card_art,
)
from src.task.task_icons import task_icon


START = re.compile(r"^开始战斗$")
RESULT = re.compile(r"^(?:(?:决斗|对决|挑战)(?:胜利|失败)|挑战成功)$")
ROUND_REGION = (.735, .030, .865, .086)
COUNT_REGION = (.466, .449, .534, .536)
ENERGY_REGION = (.910, .474, .951, .525)
START_REGION = (0, .45, .163, .535)
SPEED_REGION = (.830, .037, .880, .077)
TIMER_REGION = (.452, .112, .552, .164)
TIMER = re.compile(r"\d{2}[:：]\d{2}[:：]\d{2}")
MAX_SPEED = 2.0
KNOWN_CORE = re.compile(r"^(?:燎照之骑|异构武装|飞廉之猩)$")
MULLIGAN = re.compile(r"^选择要替换的声骸$")
CONFIRM = re.compile(r"^确认$")
START_PROMPT = re.compile(r"本回合尚有可操作空间.*确认开始战斗")
START_PROMPT_REGION = (.31, .448, .69, .511)
START_CONFIRM_REGION = (.595, .600, .75, .656)
CARD_LABELS = re.compile(r"^(?:伤害|力量|耐久)$")
CARD_DETAIL_REGION = (.128, .095, .357, .162)
BOARD_NEUTRAL = (610, 448)
SKILL_TITLE_REGION = (.035, .027, .17, .079)
SKILL_TARGET_REGION = (.408, .835, .603, .883)
SKILL_TITLE = re.compile(r'^致命弱点$')
SURVIVAL_TITLE = re.compile(r'^适者生存$')
DECK_CONFIG = '卡组策略'
RIPPER_PROFILE = RIPPER_PLAN.profile
FUSION_PROFILE = FUSION_PLAN.profile
BRANT_PROFILE = BRANT_PLAN.profile
DEFAULT_PROFILE = '燎照之骑'
DECK_PROFILES = {RIPPER_PROFILE: RIPPER_CARDS, BRANT_PROFILE: RIPPER_CARDS,
                 FUSION_PROFILE: FUSION_CARDS, DEFAULT_PROFILE: CARD_NAMES}
CHALLENGE_HEADER = (.022, .036, .146, .102)
CHALLENGE_BUTTON = (.805, .89, .985, .966)
OPPONENT_REGION = (.72, .105, .996, .163)
CURRENT_DECK = (.015, .477, .145, .530)
CURRENT_DUELIST = (.018, .208, .18, .275)
SELECTOR_TITLE = (.020, .035, .185, .108)
SELECTOR_CONFIRM = (.805, .88, .985, .97)
KNOWN_DUELIST = (.84, .127, .960, .186)
DOCTRINE_NAME = (.699, .371, .887, .438)
DECK_NAMES = re.compile(r'^(?:双镰坚守|冰火调谐)$')
SKILL_TARGETED = re.compile(r"选择\s*1\s*个目标\s*[（(]\s*1\s*[/／]\s*1\s*[）)]")


class GloryHillTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "荣耀之丘·自动对战（实验）"
        self.description = ("可从 NPC「选择挑战」页启动，按对手选用已保存的双镰坚守或冰火调谐，"
                            "也可从换牌或对局中继续。支持简体中文 16:9 PC 客户端，操作时需保持游戏在前台。")
        self.default_config[DECK_CONFIG] = RIPPER_PROFILE
        self.config_type[DECK_CONFIG] = {'type': 'drop_down', 'options': list(DECK_PROFILES)}
        self.group_name = "Daily Activities"
        self.group_icon = task_icon("category-daily")
        self.supported_languages = ["zh_CN"]
        self._drag_input = None
        self.fusion_deck = False
        self._rules = CLASSIC_RULES
        self._prepared_profile = None
        self._reset_inspections()

    def _reset_inspections(self):
        self._inspections_round = None
        self._hand_inspections = []
        self._field_inspections = {}

    def _exact(self, region, text):
        return self._read(region, re.compile(re.escape(text)))[1]

    def _challenge_button(self):
        button = self._exact(CHALLENGE_BUTTON, '前往决斗')
        return button if button and self._exact(CHALLENGE_HEADER, '选择挑战') else None

    def _wait_visible(self, condition, timeout=5):
        return self.wait_until(condition, time_out=timeout)

    def _click_visible(self, box):
        if not box or not self._drag_input.clickable():
            raise RuntimeError('荣耀之丘操作前请将鸣潮保持在前台。')
        self.click_box(box, after_sleep=.30)
        self.next_frame()

    def _select_saved_deck(self, plan):
        if not self._inspection_click(552, 449):
            raise RuntimeError('无法打开我方卡组。')
        if not self._wait_visible(lambda: self._exact(SELECTOR_TITLE, '卡组构筑')):
            raise RuntimeError('未识别到卡组选择界面。')
        candidates = [box for box in self.ocr(.074, .16, .94, .825) if box.name.strip() == plan.deck]
        if len(candidates) != 1:
            raise RuntimeError(f'卡组列表中未唯一识别到已保存卡组「{plan.deck}」。')
        self._click_visible(candidates[0])
        self._click_visible(self._wait_visible(lambda: self._exact(SELECTOR_CONFIRM, '选择卡组')))
        if not self._wait_visible(lambda: self._challenge_button() and self._exact(CURRENT_DECK, plan.deck)):
            raise RuntimeError(f'未能确认已选中「{plan.deck}」。')

    def _select_duelist(self, plan):
        if not self._inspection_click(552, 222):
            raise RuntimeError('无法打开我方战术选择。')
        if not self._wait_visible(lambda: self._exact(SELECTOR_TITLE, '战术选择')):
            raise RuntimeError('未识别到战术选择界面。')
        if not self._exact(KNOWN_DUELIST, plan.duelist):
            if not self._inspection_click(*plan.duelist_tile) or not self._wait_visible(
                lambda: self._exact(KNOWN_DUELIST, plan.duelist)
            ):
                raise RuntimeError(f'未能确认决斗家「{plan.duelist}」。')
        if not self._exact(DOCTRINE_NAME, plan.doctrine):
            if not self._inspection_click(*plan.doctrine_tile) or not self._wait_visible(
                lambda: self._exact(DOCTRINE_NAME, plan.doctrine)
            ):
                raise RuntimeError(f'未能确认战术「{plan.doctrine}」。')
        self._click_visible(self._wait_visible(lambda: self._exact(SELECTOR_CONFIRM, '确认')))
        if not self._wait_visible(lambda: self._challenge_button() and self._exact(CURRENT_DUELIST, plan.duelist)):
            raise RuntimeError(f'未能确认已选中「{plan.duelist}」。')

    def _prepare_duel(self):
        if not self._drag_input.clickable() and not self._wait_visible(self._drag_input.clickable, timeout=8):
            raise RuntimeError('请将鸣潮切回前台以配置并开始决斗。')
        self.next_frame()
        if not self._challenge_button():
            raise RuntimeError('决斗准备页已变化。')
        opponent = ''.join(box.name for box in self.ocr(*OPPONENT_REGION)).replace(' ', '')
        name = re.split(r'[·・•]', opponent)[-1].strip()
        clues = ''.join(box.name for box in self.ocr(.645, .452, .995, .672))
        event_title = ''.join(box.name for box in self.ocr(.646, .027, .875, .085))
        event = detect_duel_event(event_title + opponent + clues)
        rules = RULES_BY_EVENT.get(event)
        if rules is None:
            if event == 'rekindled':
                raise RuntimeError('已识别《荣耀之丘：激斗重燃》，当前版本还需要适配它的领域与奇藏规则。')
            raise RuntimeError('当前挑战规则未确认，请检查活动和对手的胜利条件。')
        self._rules = rules
        current = self._read(CURRENT_DECK, DECK_NAMES)[0]
        plan = challenge_plan(name, current[0] if current else '')
        if plan is None:
            raise RuntimeError(f'「{name or "当前对手"}」没有已验证的出战方案，请先选用双镰坚守或冰火调谐。')
        self.log_info(f'荣耀之丘对手 {name}，使用 {plan.deck} / {plan.duelist} / {plan.doctrine}')
        if not current or current[0] != plan.deck:
            self._select_saved_deck(plan)
        self._select_duelist(plan)
        if not self._exact(CURRENT_DECK, plan.deck):
            raise RuntimeError('出战配置变化，未确认当前卡组。')
        self._click_visible(self._challenge_button())
        if not self._wait_visible(self._mulligan, timeout=20):
            raise RuntimeError('进入决斗后未识别到换牌界面。')
        return plan.profile

    def _read(self, region, pattern):
        for box in self.ocr(*region):
            match = pattern.fullmatch(box.name.strip())
            if match:
                return match, box
        return None, None

    def _number(self, region, pattern):
        match, _ = self._read(region, pattern)
        return int(match[1]) if match else None

    def _start_button(self):
        return self._read(START_REGION, START)[1]

    def _result(self):
        # The compact combat-phase banner also uses bare labels such as 平局.
        return self._read((.405, .175, .595, .36), RESULT)[1]

    def _mulligan(self):
        if self._read((.39, .13, .61, .24), MULLIGAN)[1]:
            return self._read((.41, .77, .59, .855), CONFIRM)[1]
        return None

    def _confirm_opening(self):
        # The confirmation label appears before the initial dealing animation finishes.
        self.sleep(1.2)
        self.next_frame()
        for _ in range(2):
            if not self._mulligan():
                break
            if not self._inspection_click(800, 732):
                raise RuntimeError('换牌确认需要鸣潮保持在前台。')
            if self._wait_visible(lambda: not self._mulligan(), timeout=2):
                break
        if not self._wait_visible(lambda: self._read_board(require_hand=False) or self._core_reveal(), timeout=15):
            raise RuntimeError('确认起手后未识别到第一回合棋盘。')

    def _start_confirmation(self):
        if any(START_PROMPT.search(box.name) for box in self.ocr(*START_PROMPT_REGION)):
            return self._read(START_CONFIRM_REGION, CONFIRM)[1]
        return None

    def _cost(self, image, x, y):
        for box in self.ocr(frame=cost_image(image, x, y), threshold=.65):
            numeral = box.name.strip('.· ')
            if len(numeral) == 1 and numeral in '0123456789':
                return int(numeral)
        return None

    def _speed(self):
        match, box = self._read(SPEED_REGION, SPEED_RE)
        if match and self._read(TIMER_REGION, TIMER)[0]:
            return float(match[1].replace('．', '.')), box
        return None, None

    def _read_board(self, require_hand=True, read_stages=False):
        image = board_image(self.frame)
        if image is None or not self._start_button():
            return None
        turn = self._number(ROUND_REGION, self._rules.round_pattern)
        count = self._number(COUNT_REGION, COUNT_RE)
        energy = self._number(ENERGY_REGION, ENERGY_RE)
        if turn is None or count is None or energy is None:
            return None
        occupied = occupied_slots(image)
        if count != sum(occupied):
            return None
        if not require_hand:
            stages = tuple(self._cost(image, x, 499) if active else None for x, active in zip(SLOTS, occupied)) if read_stages else ()
            return Board(turn, count, energy, occupied, (), stages)
        headers = hand_headers(image)
        if not headers and not hand_is_empty(image):
            return None
        cards = tuple(Card(x, self._cost(image, x, y), damage_pips(image, x, y)) for x, y in headers)
        stages = tuple(self._cost(image, x, 499) if active else None for x, active in zip(SLOTS, occupied))
        return Board(turn, count, energy, occupied, cards, stages)

    def _detail_open(self):
        labels = {box.name.strip() for box in self.ocr(*CARD_DETAIL_REGION) if CARD_LABELS.fullmatch(box.name.strip())}
        return len(labels) >= 2

    def _inspection_click(self, x, y):
        interaction = self._drag_input
        if not interaction.clickable():
            return False
        interaction.click(*self._screen_point(x, y), down_time=.07)
        self.sleep(.42)
        self.next_frame()
        return True

    def _close_details(self):
        if self._core_reveal():
            return False
        if self._detail_open() and not self._inspection_click(*BOARD_NEUTRAL):
            return False
        if not self._detail_open():
            return True
        return self._inspection_click(*BOARD_NEUTRAL) and not self._detail_open()

    def _read_card_details(self, x, y, hand=False):
        if not self._inspection_click(x, y) or self._core_reveal():
            return None
        if hand and not self._detail_open():
            # A collapsed hand first expands, then accepts clicks on the card face.
            if not self._inspection_click(x, 750) or self._core_reveal():
                return None
        if not self._detail_open():
            if hand:
                self._inspection_click(*BOARD_NEUTRAL)
            return None
        names = [box.name.replace('(', '（').replace(')', '）').replace(' ', '')
                 for box in self.ocr(.129, .052, .370, .105)]
        name = next((name for name in names if name in (*RIPPER_CARDS, *FUSION_CARDS, *CARD_NAMES)), '')
        if not name:
            name = next((name for name in names if re.search(r'[\u4e00-\u9fff]{2}', name)), '')
        skills = set()
        if not hand:
            text = ''.join(box.name for box in self.ocr(.125, .29, .375, .69))
            skills = {skill for skill in ('翼守', '嘲讽', '坚韧')
                      if re.search(rf'{skill}[】\]]\s*[-—－]', text)}
        if not self._close_details():
            return None
        return name, skills

    def _name_board(self, board):
        if self._inspections_round != board.round:
            # Combat can change on-field skills. Hand names still require matching art and stats.
            self._field_inspections.clear()
            self._inspections_round = board.round
        image = board_image(self.frame)
        if image is None:
            return None
        named = []
        hand_entries = []
        for card, (x, y) in zip(board.hand, hand_headers(image)):
            art = card_fingerprint(image, x, y)
            matches = {name for old_art, cost, damage, name in self._hand_inspections
                       if (cost, damage) == (card.cost, card.damage) and same_card_art(old_art, art)}
            if len(matches) == 1:
                name = matches.pop()
            else:
                details = self._read_card_details(card.x, HAND_Y, hand=True)
                if details is None:
                    return None
                name = details[0]
            hand_entries.append((art, card.cost, card.damage, name))
            named.append(replace(card, name=name))
        if len(named) != len(board.hand):
            return None
        field_names = [''] * len(SLOTS)
        field_entries = {}
        skills = {skill: set() for skill in ('翼守', '嘲讽', '坚韧')}
        for slot, (x, active) in enumerate(zip(SLOTS, board.occupied)):
            if not active:
                continue
            art = card_fingerprint(image, x, 504, field=True)
            cached = self._field_inspections.get(slot)
            if cached and cached[1] == board.stages[slot] and same_card_art(cached[0], art):
                details = cached[2]
            else:
                details = self._read_card_details(x, SLOT_Y)
                if details is None:
                    return None
            field_entries[slot] = art, board.stages[slot], details
            field_names[slot], active_skills = details
            for skill in active_skills:
                skills[skill].add(slot)
        if self._core_reveal() or self._detail_open():
            return None
        fresh = self._read_board()
        # Recheck both board state and card art after interacting with details.
        if not fresh or (fresh.round, fresh.energy, fresh.count, fresh.stages, fresh.occupied) != (
            board.round, board.energy, board.count, board.stages, board.occupied
        ) or len(fresh.hand) != len(board.hand) or any(
            abs(a.x - b.x) > 3 or (a.cost, a.damage) != (b.cost, b.damage) for a, b in zip(fresh.hand, board.hand)
        ):
            return None
        fresh_image = board_image(self.frame)
        fresh_headers = hand_headers(fresh_image)
        if len(fresh_headers) != len(hand_entries) or any(
            not same_card_art(entry[0], card_fingerprint(fresh_image, x, y))
            for entry, (x, y) in zip(hand_entries, fresh_headers)
        ):
            return None
        self._hand_inspections = [entry for entry in hand_entries if entry[3]]
        self._field_inspections = {slot: entry for slot, entry in field_entries.items() if entry[2][0]}
        return replace(fresh, hand=tuple(replace(card, name=known.name) for card, known in zip(fresh.hand, named)),
                       field_names=tuple(field_names), wing_guard=frozenset(skills['翼守']),
                       taunt=frozenset(skills['嘲讽']), tough=frozenset(skills['坚韧']))

    def _invalidate_after_move(self, move):
        if move.kind in ('morph', 'core'):
            self._field_inspections.clear()
        elif move.slot is not None:
            self._field_inspections.pop(move.slot, None)

    def _screen_point(self, x, y):
        return round(x * self.width / WIDTH), round(y * self.height / HEIGHT)

    def _expanded_source(self, card):
        if not self._inspection_click(card.x, HAND_Y):
            return None
        image = board_image(self.frame)
        if image is not None and not self._detail_open():
            for x, y in hand_headers(image, header_y=666):
                if abs(x - card.x) <= 4 and self._cost(image, x, y) == card.cost:
                    return x, 750
        self._close_details()
        return None

    def _drag(self, source, target):
        interaction = self._drag_input
        # Never bring another window forward in the middle of the task.
        if not interaction.clickable():
            self.log_info("出牌需要鸣潮回到前台，等待窗口切换。")
            if not self.wait_until(interaction.clickable, time_out=60):
                raise RuntimeError("鸣潮窗口仍在后台，已暂停当前对局。")
            return False  # Reread the board after focus changes.

        sx, sy = source
        tx, ty = target
        interaction.move(*self._screen_point(sx, sy))
        self.sleep(.24)
        if not interaction.clickable():
            return False
        interaction.mouse_down(*self._screen_point(sx, sy))
        try:
            self.sleep(.14)
            for step in range(1, 13):
                if not interaction.clickable():
                    raise RuntimeError("拖牌时鸣潮窗口失去焦点。")
                interaction.move(*self._screen_point(sx + (tx - sx) * step / 12,
                                                    sy + (ty - sy) * step / 12))
                self.sleep(.036)
            self.sleep(.23)
        finally:
            if interaction.clickable():
                interaction.mouse_up()
            else:
                from pynput import mouse
                mouse.Controller().release(mouse.Button.left)
        interaction.move(*self._screen_point(540, 445))
        self.sleep(.65)
        self.next_frame()
        return True

    def _use_fatal_weakness(self, board):
        if not board.count or board.energy < 2 or not self._drag_input.clickable():
            return False
        image = board_image(self.frame)
        if image is None:
            return False
        targets = []
        enemy_occupied = occupied_slots(image, header_y=190)
        for slot, x in enumerate(SLOTS):
            if slot == 3 or not enemy_occupied[slot]:
                continue
            power = self._cost(image, x - 42, 184)
            if power is not None and power >= 2:
                stage = self._cost(image, x, 184) or 0
                targets.append((power, stage, -slot))
        if not targets:
            return False

        previous_power, _, negative_slot = max(targets)
        x = SLOTS[-negative_slot]
        self._drag_input.send_key('e', down_time=.12)
        if not self.wait_until(self._fatal_weakness_prompt, time_out=4):
            if self._start_button():
                return False
            raise RuntimeError('未能识别致命弱点的选目标界面，已暂停当前对局。')
        return self._confirm_fatal_weakness(board.round, board.energy, x, previous_power)

    def _fatal_weakness_prompt(self):
        return (self._read(SKILL_TITLE_REGION, SKILL_TITLE)[1] and
                any('个目标' in box.name for box in self.ocr(*SKILL_TARGET_REGION)))

    def _confirm_fatal_weakness(self, turn, energy_before, x, previous_power):
        if not self._inspection_click(x, 282):
            raise RuntimeError('无法选择致命弱点的目标，已暂停当前对局。')
        if not any(SKILL_TARGETED.search(box.name) for box in self.ocr(*SKILL_TARGET_REGION)):
            if not self._inspection_click(650, 840):
                raise RuntimeError('决斗家技能界面未关闭，已暂停当前对局。')
            return False
        if not self._inspection_click(948, 840):
            raise RuntimeError('无法确认致命弱点，已暂停当前对局。')
        energy = self.wait_until(lambda: self._start_button() and
                                 self._number(ENERGY_REGION, ENERGY_RE) == energy_before - 2, time_out=5)
        if not energy:
            raise RuntimeError('致命弱点的能量消耗未得到确认，已暂停当前对局。')
        updated = board_image(self.next_frame())
        power = self._cost(updated, x - 42, 184) if updated is not None else None
        self.log_info(f'荣耀之丘第 {turn} 回合致命弱点，敌方槽位 {SLOTS.index(x) + 1}，'
                      f'力量 {previous_power}→{power if power is not None else "未读到"}，'
                      f'能量 {energy_before}→{energy_before - 2}')
        return True

    def _use_survival(self, board, protect_ripper=False):
        if board.energy < 3 or not self._drag_input.clickable():
            return False
        targets = [slot for slot in RIPPER_FRONT
                   if board.field_names[slot] in (MACHINE, APE, BEAR) or slot in board.taunt]
        rippers = [slot for slot in RIPPER_BACK if board.field_names[slot] == RIPPER]
        if protect_ripper or not targets:
            targets = rippers or targets
        if not targets:
            return False

        self._drag_input.send_key('e', down_time=.12)
        if not self.wait_until(lambda: self._read(SKILL_TITLE_REGION, SURVIVAL_TITLE)[1], time_out=4):
            if self._start_button():
                return False
            raise RuntimeError('未能识别适者生存的选目标界面，已暂停当前对局。')
        slot = targets[0]
        if not self._inspection_click(SLOTS[slot], SLOT_Y):
            raise RuntimeError('无法选择适者生存的目标，已暂停当前对局。')
        if not any(SKILL_TARGETED.search(box.name) for box in self.ocr(*SKILL_TARGET_REGION)):
            if not self._inspection_click(650, 840) or not self.wait_until(self._start_button, time_out=4):
                raise RuntimeError('适者生存界面未关闭，已暂停当前对局。')
            return False
        if not self._inspection_click(948, 840) or not self.wait_until(
            lambda: self._start_button() and self._number(ENERGY_REGION, ENERGY_RE) == board.energy - 3,
            time_out=8,
        ):
            raise RuntimeError('适者生存的能量消耗未得到确认，已暂停当前对局。')
        self.log_info(f'荣耀之丘第 {board.round} 回合适者生存，目标 {board.field_names[slot]}，'
                      f'能量 {board.energy}→{board.energy - 3}')
        return True

    def _ripper_move(self, board, used_turtle, prioritize_rippers=False):
        life = self._number((.874, .947, .948, .983), re.compile(r'^(\d{1,2})\s*[/／]\s*30$'))
        deck_count = self._number((.067, .953, .119, .998), re.compile(r'^(\d{1,2})$'))
        return choose_ripper_move(board, life, deck_count, used_turtle, prioritize_rippers)

    def _max_speed(self):
        current, _ = self._speed()
        if current is None or current >= MAX_SPEED or not self._drag_input.clickable():
            return current
        # The speed button only accepts clicks with the battle cursor displayed.
        from pynput import keyboard
        self._drag_input.send_key_down('lalt')
        try:
            self.sleep(.28)
            for _ in range(2):
                current, _ = self._speed()
                if current is None or current >= MAX_SPEED or not self._drag_input.clickable():
                    break
                self._drag_input.click(*self._screen_point(1380, 51), down_time=.06)
                self.sleep(.42)
                self.next_frame()
                observed, _ = self._speed()
                if observed is None or observed <= current:
                    return observed
            return self._speed()[0]
        finally:
            keyboard.Controller().release(keyboard.Key.alt_l)

    def _core_reveal(self):
        return (self._read((.43, .735, .58, .805), KNOWN_CORE)[1]
                if self._number(ROUND_REGION, self._rules.round_pattern) is not None else None)

    def _dismiss_core_reveal(self):
        if not self._core_reveal():
            return False
        self.click_relative(.50, .53, after_sleep=.85)
        self.next_frame()
        return True

    def _stable_board(self):
        first = self._read_board()
        if not first or any(card.cost is None for card in first.hand):
            return None
        self.sleep(.20)
        self.next_frame()
        second = self._read_board()
        return second if second == first else None

    def _ready_board(self):
        self._dismiss_core_reveal()
        if self._core_reveal():
            return None
        if self._detail_open() and not self._close_details():
            return None
        board = self._stable_board()
        if not board and self._drag_input.clickable() and self._read_board(require_hand=False):
            self._inspection_click(*BOARD_NEUTRAL)
        return board

    def _wait_battle(self, previous_round, confirm_start=False):
        deadline = monotonic() + 120
        speed_checked = False
        saw_battle = False
        start_transition = False
        while monotonic() < deadline:
            self.next_frame()
            result = self._result()
            if result:
                self._prepared_profile = None
                self.log_info(f"荣耀之丘结算：{result.name}", notify=True)
                return result.name
            if confirm_start:
                confirmation = self._start_confirmation()
                if confirmation:
                    if self._drag_input.clickable():
                        self._inspection_click(1074, 562)
                        confirm_start = False
                        start_transition = True
                    self.sleep(.45)
                    continue
            if not speed_checked:
                speed, _ = self._speed()
                saw_battle = saw_battle or speed is not None
                if speed == MAX_SPEED or speed is not None and self._drag_input.clickable():
                    actual_speed = self._max_speed()
                    if actual_speed == MAX_SPEED:
                        self.log_info(f"荣耀之丘实战倍率：{actual_speed}×")
                    speed_checked = True
            self._dismiss_core_reveal()
            board = self._read_board(require_hand=False)
            if board is None:
                saw_battle = saw_battle or not self._start_button()
            elif (previous_round is not None and board.round > previous_round or
                  previous_round is None and (not start_transition or saw_battle)):
                return board.round
            self.sleep(.7)
        raise RuntimeError("战斗后未识别到下一回合或结算界面。")

    def run(self):
        self._rules = CLASSIC_RULES
        self.next_frame()
        if not self.hwnd or not self.hwnd.exists or board_image(self.frame) is None:
            raise RuntimeError("请使用 16:9 Windows PC 客户端打开荣耀之丘 NPC 对局。")
        result = self._result()
        if result:
            self._prepared_profile = None
            self.log_info(f"荣耀之丘结算：{result.name}", notify=True)
            return
        profile = (FUSION_PROFILE if self.fusion_deck else
                   self._prepared_profile or self.config.get(DECK_CONFIG, RIPPER_PROFILE))
        if profile not in DECK_PROFILES:
            raise RuntimeError("无法识别卡组策略，请重新选择。")
        self._drag_input = PynputInteraction(self.executor.device_manager.capture_method, self.hwnd)
        self._reset_inspections()
        if self._challenge_button():
            self._prepared_profile = None
            profile = self._prepared_profile = self._prepare_duel()
        opening = self._mulligan()
        if not opening and self._start_button() and not self._read_board(require_hand=False):
            opening = self.wait_until(self._mulligan, time_out=3)
        if opening:
            self._confirm_opening()
        if self._start_confirmation():
            # A prior explicit Start click is awaiting the game confirmation.
            if isinstance(self._wait_battle(self._number(ROUND_REGION, self._rules.round_pattern), confirm_start=True), str):
                return
        elif not self._start_button():
            if self._speed()[0] is None and not self._core_reveal():
                raise RuntimeError("请进入荣耀之丘 NPC 对局的出牌或实战界面，并关闭弹窗。")
            if not self._core_reveal() and isinstance(self._wait_battle(None), str):
                return
        # Bounded both per round and across the whole duel.
        for _ in range(self._rules.round_limit):
            used_turtle = False
            retry_available = True
            rejected_tunes = set()
            inspection_retries = 0
            last_brant_state = None
            for _ in range(18):
                board = self._ready_board() or self.wait_until(self._ready_board, time_out=15)
                if not board or any(card.cost is None for card in board.hand):
                    self.screenshot('glory_hill_board_unrecognized')
                    raise RuntimeError("未能完整识别荣耀之丘手牌或棋盘，已停在当前回合。")
                if not self._drag_input.clickable():
                    self.log_info("出牌需要鸣潮回到前台，等待窗口切换。")
                    if not self.wait_until(self._drag_input.clickable, time_out=60):
                        raise RuntimeError("鸣潮窗口仍在后台，已暂停当前对局。")
                    continue
                board = self._name_board(board)
                if board is None:
                    inspection_retries += 1
                    if inspection_retries >= 3:
                        raise RuntimeError("查牌时棋盘状态变化，已停在当前回合。")
                    continue
                inspection_retries = 0
                unknown = unsupported_cards(board, DECK_PROFILES[profile])
                if unknown:
                    names = '、'.join(sorted(name or '（无法识别牌名）' for name in unknown))
                    raise RuntimeError(f"当前卡牌没有已验证的策略：{names}。已停在出牌阶段。")
                if profile in (RIPPER_PROFILE, BRANT_PROFILE):
                    move = self._ripper_move(board, used_turtle, prioritize_rippers=profile == BRANT_PROFILE)
                elif profile == FUSION_PROFILE:
                    move = choose_fusion_move(board, rejected_tunes)
                else:
                    move = choose_move(board)
                if profile == BRANT_PROFILE:
                    front = tuple((board.field_names[slot], board.stages[slot]) for slot in RIPPER_FRONT)
                    rear = tuple((board.field_names[slot], board.stages[slot]) for slot in RIPPER_BACK)
                    hand_rippers = sum(card.name == RIPPER for card in board.hand)
                    hand_ape = int(any(card.name == APE for card in board.hand))
                    brant_state = (board.round, board.energy, hand_rippers, hand_ape, front, rear)
                    if brant_state != last_brant_state:
                        self.log_info(f'荣耀之丘第 {board.round} 回合布兰特，能量 {board.energy}，'
                                      f'手牌车刃镰 {hand_rippers}，飞廉之猩 {hand_ape}，前排 {front}，后排 {rear}')
                        last_brant_state = brant_state
                if move is None:
                    break
                if move.kind == 'recycle_board':
                    source, target = (SLOTS[move.slot], SLOT_Y), RECYCLE
                else:
                    source = (move.card.x, HAND_Y)
                    target = MORPH if move.kind == 'morph' else (
                        RECYCLE if move.slot is None else (SLOTS[move.slot], SLOT_Y))
                if move.kind == 'core' and not retry_available:
                    self.log_info(f'荣耀之丘第 {board.round} 回合展开手牌重试核心牌 {move.card.name}。')
                    source = self._expanded_source(move.card)
                    if source is None:
                        raise RuntimeError('无法确认展开后的核心声骸位置，已停在当前回合。')
                self.log_debug(f"荣耀之丘动作 {move.kind}，源 {source}，目标 {target}")
                if not self._drag(source, target):
                    self.next_frame()
                    continue
                def accepted():
                    after = self._read_board(require_hand=False, read_stages=move.kind == 'tune')
                    return after if self._rules.verify_move(board, move, after) else None

                after = accepted() or self.wait_until(accepted, time_out=3)
                if not after:
                    self._dismiss_core_reveal()
                    observed = self._read_board()
                    unchanged = observed and replace(
                        board, hand=tuple(replace(card, name='') for card in board.hand),
                        field_names=(), wing_guard=frozenset(), taunt=frozenset(), tough=frozenset(),
                    ) == observed
                    if unchanged and retry_available:
                        retry_available = False
                        continue
                    if unchanged and profile == FUSION_PROFILE and move.kind == 'tune':
                        rejected_tunes.add((move.card.name, move.slot))
                        self.log_info(f'调谐两次未生效，场面与手牌读数一致，跳过 {move.card.name} → 槽位 {move.slot + 1}。')
                        retry_available = True
                        continue
                    after = accepted() or self.wait_until(accepted, time_out=2)
                if not after:
                    self.screenshot('glory_hill_move_unconfirmed')
                    raise RuntimeError(f"荣耀之丘操作未得到确认（{move.kind}），已停在当前回合。")
                retry_available = True
                self._invalidate_after_move(move)
                if move.kind == 'morph' and move.card.name == TURTLE:
                    used_turtle = True
                self.log_info(f"荣耀之丘第 {board.round} 回合 {move.kind}，能量 {board.energy}→{after.energy}，{move.card.name if move.card else board.field_names[move.slot]}")
            else:
                raise RuntimeError("荣耀之丘本回合操作超过上限。")
            if profile in (RIPPER_PROFILE, BRANT_PROFILE):
                self._use_survival(board, protect_ripper=profile == BRANT_PROFILE)
            elif profile == FUSION_PROFILE:
                self._use_fatal_weakness(board)
            start = self._start_button()
            if not self._drag_input.clickable():
                raise RuntimeError("鸣潮窗口失去焦点，已停在出牌阶段。")
            if not start:
                raise RuntimeError("荣耀之丘开战按钮已消失。")
            self.click_box(start, down_time=.07, after_sleep=.55)
            if isinstance(self._wait_battle(board.round, confirm_start=True), str):
                return
        raise RuntimeError(f"荣耀之丘已完成 {self._rules.round_limit} 轮等待，但未识别到结算。")
