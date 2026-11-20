import unittest
from dataclasses import replace

from src.task.glory_hill import (
    BEAR, CHIME, CHOP, CLERIC, CONSTRUCT, CORE, LIZARD, MACHINE, NOBLE, PIG, PUFFER, ROCK,
    APE, HUNTER, RIPPER, SCORPION, TURTLE, VANGUARD, Board, Card, Move,
    choose_fusion_move, choose_move, choose_ripper_move,
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

    def test_turtle_is_used_at_most_once_per_deployment(self):
        turtle = Card(800, 1, 1, TURTLE)
        board = Board(3, 1, 1, (False, False, False, False, True, False, False), (turtle,),
                      (None, None, None, None, 1, None, None), ('', '', '', '', HUNTER, '', ''))
        self.assertEqual(choose_ripper_move(board), Move('morph', turtle))
        self.assertNotEqual(choose_ripper_move(board, used_turtle=True), Move('morph', turtle))
