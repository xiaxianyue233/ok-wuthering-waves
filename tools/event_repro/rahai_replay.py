"""MCP reproduction entry point for an already-cleared 4,500-point score board."""

from ok import BaseTask

from src.task.RahaiBlocksTask import RahaiBlocksTask


class Task(BaseTask):
    def reset_to_start(self):
        self.next_frame()

    def verify_start_state(self):
        task = self.executor.get_task_by_class(RahaiBlocksTask)
        score = task._score() if task and task._open_board() else None
        return bool(score and score[0] < score[1] == 4500)

    def run(self):
        task = self.executor.get_task_by_class(RahaiBlocksTask)
        task.run()
        if not task.wait_until(task._stage_list, time_out=8):
            raise RuntimeError('重玩结束后未自动返回关卡列表。')
