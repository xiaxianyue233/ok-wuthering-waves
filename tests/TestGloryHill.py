import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from dataclasses import replace

from src.task.GloryHillTask import GloryHillTask
from src.task.glory_hill import (
    BEAR, CHIME, CHOP, CLERIC, CONSTRUCT, CORE, LIZARD, MACHINE, NOBLE, PIG, PUFFER, ROCK,
    APE, HAND_Y, HUNTER, RIPPER, SCORPION, SLOT_Y, SLOTS, TURTLE, VANGUARD, Board, Card, Move,
    BRANT_PLAN, CLASSIC_RULES, FUSION_PLAN, RULES_BY_EVENT, challenge_plan, detect_duel_event,
    choose_fusion_move, choose_move, choose_ripper_move, same_card_art,
)


class TestGloryHill(unittest.TestCase):
    def setUp(self):
        self.rock = Card(800, 1, 1, ROCK)
        self.pig = Card(638, 1, 1, PIG)
        self.bear = Card(962, 3, 3, BEAR)
        self.board = Board(
            round=3, count=4, energy=2,
            occupied=(True, True, True, False, True, False, False),
            hand=(self.pig, self.rock, self.bear),
            stages=(1, 1, 1, None, 1, None, None),
            field_names=(SCORPION, LIZARD, CLERIC, '', SCORPION, '', ''),
        )

    def test_wing_guard_combo_replans_after_each_play(self):
        self.assertEqual(choose_move(self.board), Move('morph', self.pig))
        energised = replace(self.board, energy=4, hand=(self.rock, self.bear))
        self.assertEqual(choose_move(energised), Move('tune', self.rock, 1))
        staged = replace(energised, energy=3, hand=(self.bear,), stages=(1, 2, 1, None, 1, None, None),
                         field_names=(SCORPION, ROCK, CLERIC, '', SCORPION, '', ''), wing_guard=frozenset({1}))
        self.assertEqual(choose_move(staged), Move('tune', self.bear, 1))

    def test_core_uses_open_slot_even_with_zero_energy(self):
        core = Card(800, 8, 0, CORE)
        full = replace(self.board, hand=(core,))
        self.assertEqual(choose_move(full), Move('recycle_board', None, 4))
        open_board = replace(full, count=3, energy=0, occupied=(True, True, True, False, False, False, False),
                             stages=(1, 1, 1, None, None, None, None),
                             field_names=(SCORPION, LIZARD, CLERIC, '', '', '', ''))
        self.assertEqual(choose_move(open_board), Move('core', core, 4))

    def test_unknown_one_cost_card_does_not_inherit_default_strategy(self):
        unknown = replace(self.board, hand=(Card(800, 1, 1, '未验证卡牌'), Card(962, 1, 1, CHOP)))
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            choose_move(unknown)


class TestFusionDeck(unittest.TestCase):
    def test_early_noble_uses_three_energy_only_after_second_tune_level(self):
        noble = Card(800, 3, 3, NOBLE)
        machine = Card(960, 3, 3, MACHINE)
        board = Board(2, 1, 2, (False, False, True, False, False, False, False), (noble, machine),
                      (None, None, 2, None, None, None, None), ('', '', LIZARD, '', '', '', ''))
        self.assertEqual(choose_fusion_move(board), Move('recycle', machine))
        self.assertEqual(choose_fusion_move(replace(board, energy=3, hand=(noble,))), Move('tune', noble, 2))
        self.assertIsNone(choose_fusion_move(replace(board, stages=(None, None, 1, None, None, None, None))))

    def test_machine_inherits_taunt_and_tough_from_same_front_slot(self):
        machine = Card(800, 3, 3, MACHINE)
        noble = Card(960, 3, 3, NOBLE)
        board = Board(2, 1, 3, (False, False, True, False, False, False, False), (machine, noble),
                      (None, None, 2, None, None, None, None), ('', '', PUFFER, '', '', '', ''),
                      tough=frozenset({2}))
        self.assertEqual(choose_fusion_move(board), Move('tune', machine, 2))

    def test_construct_frees_slot_without_recycling_an_upgraded_unit(self):
        core = Card(800, 8, 0, CONSTRUCT)
        board = Board(5, 4, 0, (True, True, True, False, True, False, False), (core,),
                      (5, 2, 5, None, 1, None, None), (NOBLE, LIZARD, BEAR, '', CHIME, '', ''))
        self.assertEqual(choose_fusion_move(board), Move('recycle_board', None, 4))


class TestDoubleRipperDeck(unittest.TestCase):
    def test_rear_ripper_uses_prepared_slot_and_recycles_spare_for_third_energy(self):
        ripper = Card(800, 3, 3, RIPPER)
        bear = Card(960, 3, 3, BEAR)
        board = Board(4, 2, 2, (False, True, False, False, True, False, False), (ripper, bear),
                      (None, 8, None, None, 2, None, None), ('', APE, '', '', VANGUARD, '', ''))
        self.assertEqual(choose_ripper_move(board), Move('recycle', bear))
        self.assertEqual(choose_ripper_move(replace(board, energy=3, hand=(ripper,))), Move('tune', ripper, 4))

    def test_brant_recycles_two_spares_if_ripper_arrives_at_one_energy(self):
        ripper = Card(800, 3, 3, RIPPER)
        bear = Card(960, 3, 3, BEAR)
        puffer = Card(1120, 1, 1, PUFFER)
        board = Board(2, 1, 1, (False, False, False, False, True, False, False),
                      (ripper, bear, puffer), (None, None, None, None, 2, None, None),
                      ('', '', '', '', VANGUARD, '', ''))
        self.assertEqual(choose_ripper_move(board, prioritize_rippers=True), Move('recycle', bear))
        after_first = replace(board, energy=2, hand=(ripper, puffer))
        self.assertEqual(choose_ripper_move(after_first, prioritize_rippers=True), Move('recycle', puffer))
        after_second = replace(board, energy=3, hand=(ripper,))
        self.assertEqual(choose_ripper_move(after_second, prioritize_rippers=True), Move('tune', ripper, 4))
        self.assertIsNone(choose_ripper_move(replace(board, hand=(ripper, bear)), prioritize_rippers=True))

    def test_turtle_is_used_at_most_once_per_deployment(self):
        turtle = Card(800, 1, 1, TURTLE)
        board = Board(3, 1, 1, (False, False, False, False, True, False, False), (turtle,),
                      (None, None, None, None, 1, None, None), ('', '', '', '', HUNTER, '', ''))
        self.assertEqual(choose_ripper_move(board), Move('morph', turtle))
        self.assertNotEqual(choose_ripper_move(board, used_turtle=True), Move('morph', turtle))


    def test_brant_tunes_stealth_onto_durable_rear_base(self):
        hunter = Card(640, 1, 1, HUNTER)
        vanguard = Card(800, 1, 1, VANGUARD)
        board = Board(1, 0, 2, (False,) * 7, (hunter, vanguard), (None,) * 7, ('',) * 7)
        self.assertEqual(choose_ripper_move(board, prioritize_rippers=True), Move('summon', hunter, 4))
        with_hunter = replace(board, count=1, energy=1, hand=(vanguard,),
                              occupied=(False, False, False, False, True, False, False),
                              stages=(None, None, None, None, 1, None, None),
                              field_names=('', '', '', '', HUNTER, '', ''))
        self.assertEqual(choose_ripper_move(with_hunter, prioritize_rippers=True), Move('tune', vanguard, 4))

    def test_brant_builds_front_taunt_while_looking_for_second_ripper(self):
        puffer = Card(800, 1, 1, PUFFER)
        hunter = Card(960, 1, 1, HUNTER)
        vanguard = Card(1120, 1, 1, VANGUARD)
        board = Board(3, 1, 2, (False, False, False, False, True, False, False),
                      (puffer, hunter, vanguard), (None, None, None, None, 5, None, None),
                      ('', '', '', '', RIPPER, '', ''))
        self.assertEqual(choose_ripper_move(board, prioritize_rippers=True), Move('summon', puffer, 2))
        with_puffer = replace(board, count=2, energy=1, hand=(hunter, vanguard),
                              occupied=(False, False, True, False, True, False, False),
                              stages=(None, None, 1, None, 5, None, None),
                              field_names=('', '', PUFFER, '', RIPPER, '', ''))
        self.assertEqual(choose_ripper_move(with_puffer, prioritize_rippers=True), Move('tune', hunter, 2))
        self.assertEqual(choose_ripper_move(replace(board, energy=1), prioritize_rippers=True),
                         Move('summon', hunter, 5))

    def test_brant_builds_second_rear_stack_with_existing_ripper(self):
        ripper = Card(650, 3, 3, RIPPER)
        vanguard = Card(800, 1, 1, VANGUARD)
        hunter = Card(960, 1, 1, HUNTER)
        board = Board(2, 1, 2, (False, False, False, False, True, False, False),
                      (ripper, vanguard, hunter), (None, None, None, None, 5, None, None),
                      ('', '', '', '', RIPPER, '', ''))
        self.assertEqual(choose_ripper_move(board, prioritize_rippers=True), Move('summon', hunter, 5))


class TestGloryHillPreparation(unittest.TestCase):
    def test_known_opponent_can_switch_deck_or_strategy(self):
        self.assertEqual(challenge_plan('布兰特', '冰火调谐'), BRANT_PLAN)
        self.assertEqual(challenge_plan('夏空', '双镰坚守'), FUSION_PLAN)
        self.assertEqual(challenge_plan('其他对手', '冰火调谐'), FUSION_PLAN)
        self.assertIsNone(challenge_plan('其他对手', '未知自定义卡组'))

    def test_rekindled_markers_override_eight_round_victory_condition(self):
        self.assertIs(RULES_BY_EVENT[detect_duel_event('在第 8 回合结束时剩余生命较高')], CLASSIC_RULES)
        event = detect_duel_event('荣耀之丘：激斗重燃 第8回合 领域 奇藏')
        self.assertEqual(event, 'rekindled')
        self.assertNotIn(event, RULES_BY_EVENT)

    def test_card_art_rejects_lookalike_with_a_local_change(self):
        card = np.full((8, 28, 3), 80, dtype=np.uint8)
        changed = card.copy()
        changed[:, 8:10] = 100
        self.assertFalse(same_card_art(card, changed))
        self.assertTrue(same_card_art(card, card + 2))

    def test_new_round_reuses_matching_hand_but_rechecks_field_skills(self):
        art = np.full((8, 28, 3), 80, dtype=np.uint8)
        new_card = Card(960, 1, 1, '')
        surviving_card = Card(800, 3, 3, '')
        board = Board(2, 1, 2, (False, False, False, False, True, False, False),
                      (surviving_card, new_card), (None, None, None, None, 2, None, None))
        reader = SimpleNamespace(
            frame=object(), _inspections_round=1,
            _hand_inspections=[(art, 3, 3, RIPPER)],
            _field_inspections={4: (art, 2, (VANGUARD, {'嘲讽'}))},
            _read_card_details=Mock(side_effect=[(HUNTER, set()), (VANGUARD, set())]),
            _core_reveal=lambda: False, _detail_open=lambda: False, _read_board=lambda: board,
        )
        with patch('src.task.GloryHillTask.board_image', return_value=object()), \
                patch('src.task.GloryHillTask.hand_headers', return_value=((800, 825), (960, 825))), \
                patch('src.task.GloryHillTask.card_fingerprint', return_value=art):
            named = GloryHillTask._name_board(reader, board)
        self.assertEqual(tuple(card.name for card in named.hand), (RIPPER, HUNTER))
        self.assertEqual(named.taunt, frozenset())
        self.assertEqual([call.args for call in reader._read_card_details.call_args_list],
                         [(960, HAND_Y), (SLOTS[4], SLOT_Y)])

    def test_after_rejected_tune_plan_can_select_another_target(self):
        noble = Card(800, 3, 3, NOBLE)
        board = Board(2, 2, 3, (False, True, True, False, False, False, False), (noble,),
                      (None, 2, 2, None, None, None, None), ('', LIZARD, LIZARD, '', '', '', ''))
        first = choose_fusion_move(board)
        second = choose_fusion_move(board, {(noble.name, first.slot)})
        self.assertEqual(second.kind, 'tune')
        self.assertNotEqual(second.slot, first.slot)
