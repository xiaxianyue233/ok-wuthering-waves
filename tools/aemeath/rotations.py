import ast
import re


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unexpected source for {old!r}")
    return text.replace(old, new)


def swap_method(source, name, replacement):
    node, = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == name]
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + '\n']
    return ''.join(lines)


def optimize_script(archive, filename, source):
    original = source
    if 'def send_input_left(up):' in source and 'ctypes.windll.user32.SendInput(' in source:
        marker = '    try:\n        inp = _INPUT(type=_INPUT_MOUSE)'
        start = source.index('def send_input_left(up):')
        end = source.index(marker, start)
        source = source[:end] + '    if not up:\n        _pace_press("mouse", "left")\n' + source[end:]
    if 'Hiyuki_Lucilla_Suisui_' in archive and filename == 'Hiyuki.py' and 'def _send_input(inp):' in source:
        source = re.sub(r'(def si_mouse\(button, up\):\n(?:    """[^\n]*\n)?)',
                        r'\1    if not up:\n        _pace_press("mouse", button)\n', source, count=1)
        source = re.sub(r'(def si_key\(vk, up\):\n(?:    """[^\n]*\n)?)',
                        r'\1    if not up:\n        key = chr(vk) if 48 <= vk <= 57 or 65 <= vk <= 90 else vk\n        _pace_press("key", key)\n', source, count=1)
    if '_pace_press(' in source:
        nodes = ast.parse(source).body
        first_import = next(i for i, n in enumerate(nodes) if isinstance(n, (ast.Import, ast.ImportFrom)))
        while isinstance(nodes[first_import], ast.ImportFrom) and nodes[first_import].module == '__future__':
            first_import += 1
        lines = source.splitlines(keepends=True)
        lines.insert(nodes[first_import].lineno - 1, 'from src.combat.InputPacing import before_press as _pace_press\n')
        source = ''.join(lines)
    if filename == 'Hsin.py' and 'def spam_key(' in source and re.search(r'spam_key\([^\n]+interval=0\.06\b', source):
        source = swap_method(source, 'spam_key', '''    def spam_key(self, send, window, interval=None, tag='key', poke=False, presses=None):
        """Retry inside the configured window with enough time to register each press."""
        interval = max(0.16, self.KEY_INTERVAL if interval is None else interval)
        if presses is not None and presses > 0:
            interval = max(interval, window / presses)
        deadline = time.monotonic() + window
        next_click = time.monotonic()
        count = clicks = 0
        while time.monotonic() + 0.04 <= deadline and (presses is None or count < presses):
            sent_at = time.monotonic()
            send()
            count += 1
            next_press = min(deadline, sent_at + interval)
            while (remaining := next_press - time.monotonic()) > 0:
                now = time.monotonic()
                if poke and now >= next_click and remaining >= 0.10:
                    self.click()
                    clicks += 1
                    next_click = now + max(0.16, self.A_INTERVAL)
                self.macro_wait(min(0.02, next_press - time.monotonic()))
        self.macro_mark(f'{tag}(x{count},A x{clicks})')
        return count
''')
        source = re.sub(r'(spam_key\([^\n]+interval=)0\.06\b', r'\g<1>0.16', source)
    if archive == 'Lucy_Mornye_Rebecca_芝士奶酪_1.0.0.zip' and filename == 'Rebecca.py':
        source = replace(source, 'self._fr_click(interval=0.08)', 'self._fr_click(interval=0.16)')
    if archive == 'Aemeath_Lynae_Mornye_楽山_3.1.0.zip' and filename == 'Aemeath.py':
        source = swap_method(source, 'perform_25s_cycle', '''    def _wait_cycle_skill(self, ready, seconds, normal_attack=False):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if ready():
                return True
            if normal_attack:
                self.click()
            self.sleep(0.18)
            self.task.next_frame()
        return False

    def perform_25s_cycle(self):
        if self.check_outro() not in LINNAI_NAMES:
            self.continues_normal_attack(2, interval=0.18)
            return self.switch_next_char()
        if not self.task.use_liberation or not self._wait_cycle_skill(
                lambda: self.enhance_e_available() and self.liberation_available(), 2.5, normal_attack=True):
            self.logger.debug('25s rotation: opening skills unavailable, rotating out')
            return self.switch_next_char()
        self.click_echo()
        self.f_break()
        if not self.click_liberation(wait_if_cd_ready=0, input_timeout=1.2):
            return self.switch_next_char()
        self.f_break()
        self.click_resonance(has_animation=True, time_out=1.5)
        if not self._wait_cycle_skill(self.enhance_e_available, 2.0, normal_attack=True):
            return self.switch_next_char()
        self.click_resonance(has_animation=True, time_out=1.5)
        self.handle_heavy()
        if not self._wait_cycle_skill(self.liberation_available, 1.5):
            return self.switch_next_char()
        if not self.click_liberation(wait_if_cd_ready=0, input_timeout=1.2):
            return self.switch_next_char()

        self.click_resonance()
        self.continues_normal_attack(2, interval=0.18)
        self.send_resonance_key()
        judge = next((c for c in self.task.chars if c is not self and hasattr(c, 'con_both')), None)
        if judge:
            judge.con_both_reset()
            self.task.next_frame()
            if judge.con_both(self, need=1):
                self.current_con = 1
        return self.switch_next_char()
''')
    if source != original:
        compile(source, filename, 'exec')
    return source
