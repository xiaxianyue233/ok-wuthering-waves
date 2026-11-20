import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src.task.RahaiBlocksTask import ChallengeFailed, RahaiBlocksTask
from src.task.rahai_blocks import (
    Board, COLS, ROWS, Piece, canonical_frame, choose_move, clear_lines, placements,
    preview_matches, read_board, score_bar_full,
)


def fixture(name):
    path = Path(__file__).with_name('images') / f'rahai_{name}.jpg'
    return canonical_frame(cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR))


class TestRahaiBlocks(unittest.TestCase):
    def test_intersecting_lines_clear_simultaneously(self):
        self.assertEqual(clear_lines(ROWS[2] | COLS[3] | 1), (1, 2))

    def test_full_lines_include_but_do_not_remove_gray_blocks(self):
        corners = 0x8100000000000081
        mask = ROWS[0] | COLS[0] | corners | (1 << 9)
        self.assertEqual(clear_lines(mask, corners), (corners | (1 << 9), 2))

    def test_rotations_cannot_mirror_or_wrap(self):
        moves = placements(((0, 0), (0, 1), (1, 1)))
        self.assertEqual({turns for turns, *_ in moves}, {0, 1, 2, 3})
        for _, row, col, shape, mask in moves:
            self.assertEqual(mask.bit_count(), len(shape))
            self.assertTrue(all(row + y < 8 and col + x < 8 for x, y in shape))

    def test_solver_considers_the_other_piece(self):
        square = Piece(0, ((0, 0), (0, 1), (1, 0), (1, 1)), (0, 0))
        single = Piece(1, ((0, 0),), (0, 0))
        row = ROWS[1] ^ (1 << 8)
        almost_full = row | ROWS[0] ^ 3
        board = Board(almost_full, (square, single))
        move = choose_move(board)
        self.assertEqual(move.slot, 1)
        self.assertFalse(move.mask & board.mask)
        self.assertEqual(clear_lines(board.mask | move.mask)[1], 1)

    def test_reads_real_board_and_ignores_rotation_tooltip(self):
        board = read_board(fixture('score'))
        self.assertEqual(board.mask, 27026459673497112)
        self.assertEqual([len(p.cells) for p in board.pieces], [4, 5])
        move = choose_move(board)
        self.assertEqual((move.slot, move.row, move.col), (0, 2, 5))
        self.assertTrue(preview_matches(fixture('preview'), board, move))
        self.assertFalse(preview_matches(fixture('score'), board, move))

    def test_reward_overlay_is_not_playable_and_has_full_bar(self):
        for board_name, reward_name in (('score', 'reward'), ('score_4500', 'reward_4500'),
                                        ('medal_start', 'medal_reward')):
            with self.subTest(board=board_name):
                reward = fixture(reward_name)
                self.assertIsNone(read_board(reward))
                self.assertTrue(score_bar_full(reward))
                self.assertFalse(score_bar_full(fixture(board_name)))

    def test_reads_three_trays_and_all_four_gray_corners(self):
        board = read_board(fixture('score_4500'))
        self.assertEqual(board.mask, 0x991800C3C3001899)
        self.assertEqual(board.fixed, 0x8100000000000081)
        self.assertEqual([(p.slot, len(p.cells)) for p in board.pieces], [(0, 5), (1, 4), (2, 5)])
        move = choose_move(board)
        self.assertFalse(move.mask & board.mask)
        alternative = choose_move(board, excluded={(move.slot, move.mask)})
        self.assertNotEqual((alternative.slot, alternative.mask), (move.slot, move.mask))

    def test_reads_medal_board_that_matches_both_tray_geometries(self):
        board = read_board(fixture('medal_start'))
        self.assertEqual(board.mask, 0x800E7AC2DEE8C12)
        self.assertEqual(board.fixed, 0x800008001000010)
        self.assertEqual([(p.slot, len(p.cells)) for p in board.pieces], [(0, 4), (1, 4), (2, 5)])
        self.assertEqual(board.pieces[2].cells, tuple((x, 0) for x in range(5)))

    def test_partly_used_three_tray_layout_keeps_slot_ids(self):
        board = read_board(fixture('score_4500_partial'))
        self.assertEqual(board.mask, 0x9B1A3E0E3E001A9B)
        self.assertEqual(board.fixed, 0x8100000000000081)
        self.assertEqual([p.slot for p in board.pieces], [0, 1])

    def test_bright_piece_does_not_look_like_two_tray_divider(self):
        board = read_board(fixture('score_4500_ambiguous_trays'))
        self.assertIsNotNone(board)
        self.assertEqual([(piece.slot, len(piece.cells)) for piece in board.pieces], [(0, 9), (1, 4), (2, 5)])

    def test_unrelated_and_non_widescreen_frames_are_rejected(self):
        self.assertIsNone(read_board(canonical_frame(np.zeros((720, 1280, 3), np.uint8))))
        self.assertIsNone(canonical_frame(np.zeros((720, 1440, 3), np.uint8)))


class TestRahaiBlocksEntry(unittest.TestCase):
    def test_open_medal_board_takes_priority_over_the_stage_list(self):
        task = Mock(spec=RahaiBlocksTask)
        board = read_board(fixture('medal_start'))
        self.assertIsNotNone(board)
        task._open_board.return_value = board
        self.assertEqual(RahaiBlocksTask._start_view(task), (board, None))
        task._stage_list.assert_not_called()

    def test_without_an_open_board_the_stage_list_remains_an_entry(self):
        task = Mock(spec=RahaiBlocksTask)
        task._open_board.return_value = None
        stages = [object()]
        task._stage_list.return_value = stages
        self.assertEqual(RahaiBlocksTask._start_view(task), (None, stages))


class TestRahaiBlocksCompletion(unittest.TestCase):
    def make_task(self):
        task = Mock(spec=RahaiBlocksTask)
        task._reward.side_effect = lambda: RahaiBlocksTask._reward(task)
        task._completion.side_effect = lambda: RahaiBlocksTask._completion(task)
        return task

    @staticmethod
    def screen(text):
        return lambda *args, match: [text] if match.fullmatch(text) else []

    def test_replay_catches_transient_success_after_last_scoring_drop(self):
        task = self.make_task()
        task._playable_board.return_value = read_board(fixture('score_4500'))
        task._place.return_value = True
        task._read_board.return_value = None
        task.ocr.side_effect = self.screen('')
        frame = 0

        def advance():
            nonlocal frame
            frame += 1
            text = {3: '挑 战 成 功', 4: '回转的深空'}.get(frame, '')
            task.ocr.side_effect = self.screen(text)

        task.next_frame.side_effect = advance
        with patch('src.task.RahaiBlocksTask.clear_lines', return_value=(0, 1)):
            self.assertEqual(RahaiBlocksTask._play_board(task, Mock()), 'replay')
        self.assertEqual(frame, 3)
        task._place.assert_called_once()
        task.click.assert_not_called()
        task.wait_until.assert_not_called()

    def test_disappearing_board_polls_for_replay_success_during_transition(self):
        task = self.make_task()
        task._playable_board.return_value = None
        task.ocr.side_effect = self.screen('')

        def poll(condition, *, time_out):
            task.ocr.side_effect = self.screen('挑战成功')
            return condition()

        task.wait_until.side_effect = poll
        self.assertEqual(RahaiBlocksTask._play_board(task, Mock()), 'replay')
        task.click.assert_not_called()

    def test_stage_list_and_failure_are_not_success_evidence(self):
        for text in ('回转的深空', '挑战失败', '4500/4500'):
            with self.subTest(text=text):
                task = self.make_task()
                task._playable_board.return_value = None
                task.ocr.side_effect = self.screen(text)
                task.wait_until.side_effect = lambda condition, **kwargs: condition()
                with self.assertRaisesRegex(ChallengeFailed, '棋盘消失，未确认通关'):
                    RahaiBlocksTask._play_board(task, Mock())

    def test_board_resume_preserves_the_first_clear_reward(self):
        task = self.make_task()
        task._playable_board.return_value = None
        task.ocr.side_effect = self.screen('获 得')
        self.assertEqual(RahaiBlocksTask._play_board(task, Mock()), 'reward')
        task.click.assert_not_called()

    def test_stage_list_clicks_only_a_confirmed_reward(self):
        for result, click_count in (('reward', 3), ('replay', 2)):
            with self.subTest(result=result):
                task = self.make_task()
                task._stage_details.return_value = True
                task._ready_board.return_value = True
                task.wait_until.side_effect = lambda condition, **kwargs: condition()
                task.ocr.return_value = [object()]
                start, status, title = object(), object(), Mock()
                task._challenge_button.side_effect = [start, None]
                task._play_board.return_value = result
                RahaiBlocksTask._challenge(task, Mock(), title, status, 1)
                self.assertEqual(task.click.call_count, click_count)
                if result == 'reward':
                    task.click.assert_called_with(.5, .88, after_sleep=.6)
