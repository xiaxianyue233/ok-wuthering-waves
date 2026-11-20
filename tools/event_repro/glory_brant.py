"""MCP reproduction entry point for the Brant Select Challenge screen."""

from ok import BaseTask

from src.task.GloryHillTask import GloryHillTask


class Task(BaseTask):
    def reset_to_start(self):
        self.next_frame()

    def verify_start_state(self):
        task = self.executor.get_task_by_class(GloryHillTask)
        return bool(task and task._challenge_button() and task._exact(
            (.72, .105, .996, .163), '神秘的挑战者·布兰特',
        ))

    def run(self):
        task = self.executor.get_task_by_class(GloryHillTask)
        self.hwnd.bring_to_front()
        task.run()
        result = task._result()
        if not result:
            raise RuntimeError('未识别到布兰特对局结算。')
        self.log_info(f'布兰特实测结算：{result.name}')
