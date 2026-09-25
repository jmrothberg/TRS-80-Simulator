"""TRS-80 inspired Level II BASIC for ESP32 MicroPython USB serial.

The interpreter runs on the microcontroller.  No Tkinter, browser, network,
or external packages are required.  See README.md for supported syntax.
"""

import math
import random
import sys
import os

try:
    import select
except ImportError:
    select = None


def split_top(s, delimiter):
    out, start, depth, quoted = [], 0, 0, False
    for i, ch in enumerate(s):
        if ch == '"':
            quoted = not quoted
        elif not quoted:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == delimiter and depth == 0:
                out.append(s[start:i].strip())
                start = i + 1
    out.append(s[start:].strip())
    return out


def _alnum(ch):
    """Letter or digit. MicroPython str has no isalnum."""
    return ch.isalpha() or ch.isdigit()


def _else_at(clause):
    """Index of the ELSE for this THEN. An ELSE inside a nested IF stays there."""
    upper = clause.upper()
    depth, i, n = 0, 0, len(clause)
    while i < n:
        if clause[i] == '"':
            i += 1
            while i < n and clause[i] != '"':
                i += 1
            i += 1
            continue
        start = i == 0 or not _alnum(clause[i - 1])
        if start and upper.startswith('IF', i) and (i + 2 >= n or not _alnum(clause[i + 2])):
            depth += 1
            i += 2
            continue
        if start and upper.startswith('ELSE', i) and (i + 4 >= n or not _alnum(clause[i + 4])):
            if depth == 0:
                return i
            depth -= 1
            i += 4
            continue
        i += 1
    return -1


def tokens(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
        elif c == '"':
            j = i + 1
            while j < len(s) and s[j] != '"':
                j += 1
            if j == len(s):
                raise ValueError('unterminated string')
            out.append(('str', s[i + 1:j]))
            i = j + 1
        elif c.isdigit() or c == '.' and i + 1 < len(s) and s[i + 1].isdigit():
            j = i + 1
            while j < len(s) and (s[j].isdigit() or s[j] == '.'):
                j += 1
            out.append(('num', s[i:j]))
            i = j
        elif c.isalpha() or c == '_':
            j = i + 1
            while j < len(s) and (_alnum(s[j]) or s[j] in '_$%!#'):
                j += 1
            out.append(('id', s[i:j].upper()))
            i = j
        elif s[i:i + 2] in ('<=', '>=', '<>'):
            out.append(('op', s[i:i + 2]))
            i += 2
        elif c in '+-*/^(),=<>' :
            out.append(('op', c))
            i += 1
        else:
            raise ValueError('unexpected character ' + c)
    out.append(('eof', ''))
    return out


def make_array(dims, fill):
    """BASIC DIM sizes are the highest legal index, so each axis is size+1."""
    if len(dims) == 1:
        return [fill] * (dims[0] + 1)
    return [make_array(dims[1:], fill) for _ in range(dims[0] + 1)]


# Longer words first so PRINT# wins over PRINT and DEFSTR wins over DEF.
_KEYWORDS = (
    'PRINT@', 'PRINT#', 'INPUT#', 'DEFINT', 'DEFSNG', 'DEFSTR', 'DEFDBL',
    'RESTORE', 'RETURN', 'RANDOM', 'RESUME', 'GOSUB', 'GOTO', 'PRINT',
    'INPUT', 'NEXT', 'DATA', 'READ', 'STOP', 'THEN', 'ELSE', 'OPEN',
    'CLOSE', 'COLOR', 'SOUND', 'CLEAR', 'ERROR', 'BEEP', 'POKE', 'CONT',
    'DIM', 'DEF', 'REM', 'LET', 'FOR', 'END', 'CLS', 'SET', 'RESET',
    'ON', 'IF',
)


def statement_word(source):
    """Keyword plus the rest. PRINT\"hi\" has no space; ? is PRINT."""
    raw = source.strip()
    if not raw:
        return '', ''
    if raw[0] == '?':
        return 'PRINT', raw[1:].strip()
    upper = raw.upper()
    for keyword in _KEYWORDS:
        if upper.startswith(keyword):
            end = len(keyword)
            # PRINT@0 has no space. A keyword that ends in @ or # may be followed by a digit.
            if end == len(raw) or not _alnum(keyword[-1]) or not (_alnum(raw[end]) or raw[end] in '_$%!#'):
                return keyword, raw[end:].strip()
    word = raw.split(None, 1)[0].upper()
    return word, raw[len(word):].strip()


class Expression:
    def __init__(self, machine, source):
        self.machine = machine
        self.items = tokens(source)
        self.pos = 0

    def peek(self):
        return self.items[self.pos][1]

    def take(self, value=None):
        item = self.items[self.pos]
        if value is not None and item[1] != value:
            raise ValueError('expected ' + value)
        self.pos += 1
        return item

    def parse(self):
        value = self.expr(0)
        if self.peek():
            raise ValueError('extra expression text')
        return value

    def expr(self, minimum):
        kind, value = self.take()
        if kind == 'num':
            left = float(value)
        elif kind == 'str':
            left = value
        elif value == '(':
            left = self.expr(0)
            self.take(')')
        elif value in ('+', '-', 'NOT'):
            # ^ is tighter than unary minus, so -2^2 is -(2^2). NOT stays tight.
            right = self.expr(8 if value == 'NOT' else 6)
            left = (+right if value == '+' else -right if value == '-' else ~int(right))
        elif kind == 'id':
            if self.peek() == '(':
                self.take('(')
                args = []
                if self.peek() != ')':
                    args.append(self.expr(0))
                    while self.peek() == ',':
                        self.take(',')
                        args.append(self.expr(0))
                self.take(')')
                left = self.machine.call(value, args)
            else:
                # MEM, ERR, and ERL are functions even with no parentheses.
                left = self.machine.call(value, []) if value in ('INKEY$', 'RND', 'MEM', 'FRE', 'ERR', 'ERL', 'POS') else self.machine.get_var(value)
        else:
            raise ValueError('expected value')
        priority = {'OR': 1, 'AND': 2, '=': 3, '<>': 3, '<': 3,
                    '>': 3, '<=': 3, '>=': 3, '+': 4, '-': 4,
                    '*': 5, '/': 5, 'MOD': 5, '^': 6}
        while self.peek() in priority and priority[self.peek()] >= minimum:
            op = self.take()[1]
            p = priority[op]
            right = self.expr(p if op == '^' else p + 1)
            if op == '+':
                left = left + right
            elif op == '-':
                left = left - right
            elif op == '*':
                left = left * right
            elif op == '/':
                left = left / right
            elif op == '^':
                left = left ** right
            elif op == 'MOD':
                left = int(left) % int(right)
            elif op == 'AND':
                left = int(left) & int(right)
            elif op == 'OR':
                left = int(left) | int(right)
            else:
                if op == '=': result = left == right
                elif op == '<>': result = left != right
                elif op == '<': result = left < right
                elif op == '>': result = left > right
                elif op == '<=': result = left <= right
                else: result = left >= right
                left = -1 if result else 0
        return left


def printable(value):
    """Numbers use a sign column and a trailing blank, the way Level II prints."""
    if isinstance(value, str):
        return value
    # int() comparison: MicroPython float has no is_integer().
    if isinstance(value, float) and value == int(value):
        value = int(value)
    text = str(value)
    if not text.startswith('-'):
        text = ' ' + text
    return text + ' '


class Basic:
    def __init__(self, output=None, input_fn=None, hardware=None):
        self.output = output or (lambda s: sys.stdout.write(s))
        self.input_fn = input_fn or input
        self.hardware = hardware
        self.program = {}
        self.screen = [[' '] * 64 for _ in range(16)]
        self.pixels = bytearray(128 * 48 // 8)
        self.pixel_colors = {}
        self.text_colors = bytearray([2] * 1024)
        self.color_fg, self.color_bg = 2, 0
        self.cursor = 0
        self.dirty = True
        self.tape = None
        self.channel = None
        self.keys = []
        # DEFINT/DEFSTR survive NEW and RUN. DEF FN and ON ERROR do not.
        self.deftype = {}
        self.fns = {}
        self.on_error = None
        self.erl = 0
        self.err = 0
        self.resume_pc = None
        self.in_error = False
        self.cont_pc = None
        self.keep_cont = False
        self.gpio_out = 0
        self.palette_bytes = bytearray(48)
        self.poller = None
        if select is not None:
            try:
                self.poller = select.poll()
                self.poller.register(sys.stdin, select.POLLIN)
            except (AttributeError, OSError, TypeError):
                self.poller = None
        self.reset()

    def reset(self, clear_fn=False):
        self.vars, self.arrays, self.loops, self.gosubs = {}, {}, [], []
        self.data, self.data_pos = [], 0
        self.pc = 0
        self.running = False
        self.resume_pc = None
        self.in_error = False
        self.keep_cont = False
        self.cont_pc = None
        if clear_fn:
            self.fns = {}
            self.on_error = None
            self.erl = 0
            self.err = 0

    def canon(self, raw):
        """First two characters plus the type mark. # is single, same as !."""
        name = raw.strip().upper()
        mark = ''
        if name and name[-1] in '$%!#':
            mark = '$' if name[-1] == '$' else '%' if name[-1] == '%' else '!'
            name = name[:-1]
        stem = ''.join(ch for ch in name if _alnum(ch))[:2]
        if not stem:
            raise ValueError('bad name')
        if not mark:
            mark = self.deftype.get(stem[0], '')
        if mark == '!':
            mark = ''
        return stem + mark

    def get_var(self, name):
        key = self.canon(name)
        if key in self.vars:
            return self.vars[key]
        return '' if key.endswith('$') else 0

    def array_get(self, name, indexes):
        box = self.arrays[self.canon(name)]
        idxs = [int(i) for i in indexes]
        for i in idxs[:-1]:
            box = box[i]
        return box[idxs[-1]]

    def array_set(self, name, indexes, value):
        key = self.canon(name)
        box = self.arrays[key]
        idxs = [int(i) for i in indexes]
        for i in idxs[:-1]:
            box = box[i]
        if key.endswith('$') != isinstance(value, str):
            raise ValueError('type mismatch')
        if key.endswith('%') and not isinstance(value, str):
            value = int(float(value))
        box[idxs[-1]] = value

    def poll_key(self):
        if self.keys:
            return self.keys.pop(0)
        if self.poller is not None and self.poller.poll(0):
            return sys.stdin.read(1)
        return ''

    def check_break(self):
        """Esc or Ctrl-C stops a running program. Other keys stay for INKEY$."""
        key = self.poll_key()
        if key in ('\x1b', '\x03'):
            raise KeyboardInterrupt
        if key:
            self.keys.insert(0, key)

    def screen_write(self, text):
        if text: self.dirty = True
        for char in text:
            if char == '\n':
                self.cursor = ((self.cursor // 64) + 1) * 64
            elif char == '\r':
                self.cursor -= self.cursor % 64
            elif char in '\b\x7f':
                # Backspace stays on this row so the host console and panel match.
                if self.cursor % 64:
                    self.cursor -= 1
                    self.screen[self.cursor // 64][self.cursor % 64] = ' '
            else:
                if self.cursor >= 1024:
                    self.screen.pop(0)
                    self.screen.append([' '] * 64)
                    self.text_colors = self.text_colors[64:] + bytearray([self.color_fg] * 64)
                    self.cursor -= 64
                self.screen[self.cursor // 64][self.cursor % 64] = char
                self.text_colors[self.cursor] = self.color_fg
                self.cursor += 1
            if self.cursor >= 1024:
                self.screen.pop(0)
                self.screen.append([' '] * 64)
                self.text_colors = self.text_colors[64:] + bytearray([self.color_fg] * 64)
                self.cursor -= 64

    def emit(self, text):
        self.output(text)
        self.screen_write(text)

    def refresh(self):
        if self.dirty and self.hardware is not None:
            # Update the host window before the slow panel refresh, from the same buffer.
            self.mirror()
            self.hardware.draw(self)
            self.dirty = False

    def mirror(self):
        """Send the real 64x16 and the cursor. ESC ] S, 4 digits, 1024 chars."""
        cur = self.cursor
        if cur < 0:
            cur = 0
        if cur > 1023:
            cur = 1023
        chars = ''.join(''.join(row) for row in self.screen)
        self.output('\x1b]S%04d%s' % (cur, chars))

    def eval(self, text):
        return Expression(self, text.strip()).parse()

    def call(self, name, args):
        a = args[0] if args else 0
        if name in self.fns:
            param, expr = self.fns[name]
            arg = args[0] if args else 0
            had = param in self.vars
            old = self.vars.get(param)
            self.vars[param] = arg
            try:
                return self.eval(expr)
            finally:
                if had:
                    self.vars[param] = old
                else:
                    self.vars.pop(param, None)
        if name == 'RND':
            if a < 0:
                raise ValueError('FC')
            return random.random() if a == 0 else random.randint(1, int(a))
        if name == 'INT': return math.floor(a)
        if name == 'ABS': return abs(a)
        if name == 'SGN': return (a > 0) - (a < 0)
        if name == 'SQR': return math.sqrt(a)
        if name == 'SIN': return math.sin(a)
        if name == 'COS': return math.cos(a)
        if name == 'TAN': return math.tan(a)
        if name == 'ATN': return math.atan(a)
        if name == 'LOG': return math.log(a)
        if name == 'EXP': return math.exp(a)
        if name == 'LEN': return len(a)
        if name == 'VAL':
            # Level II reads the leading number and stops. VAL("8 9") is 8.
            text = str(a).strip()
            i = 1 if text[:1] in '+-' else 0
            start, dot = i, False
            while i < len(text) and (text[i].isdigit() or text[i] == '.' and not dot):
                if text[i] == '.':
                    dot = True
                i += 1
            if i == start:
                return 0
            return float(text[:i])
        if name == 'STR$':
            # One leading blank for positive numbers, and no trailing blank.
            number = int(a) if isinstance(a, float) and a == int(a) else a
            text = str(number)
            return text if text.startswith('-') else ' ' + text
        if name == 'CHR$': return chr(int(a))
        if name == 'ASC': return ord(a[0])
        if name == 'LEFT$': return args[0][:int(args[1])]
        if name == 'RIGHT$':
            n = int(args[1])
            if n < 0: raise ValueError('FC')
            return '' if n == 0 else args[0][-n:]
        if name == 'MID$': return args[0][int(args[1])-1:int(args[1])-1+int(args[2])] if len(args) > 2 else args[0][int(args[1])-1:]
        if name == 'STRING$':
            n = int(args[0])
            if n < 0: raise ValueError('FC')
            piece = args[1][:1] if isinstance(args[1], str) else chr(int(args[1]))
            return piece * n
        if name == 'INSTR':
            if len(args) == 3:
                start, hay, needle = int(args[0]), args[1], args[2]
            else:
                start, hay, needle = 1, args[0], args[1]
            found = hay.find(needle, max(0, start - 1))
            return 0 if found < 0 else found + 1
        if name == 'FIX': return math.trunc(a)
        if name == 'CINT': return int(a)
        if name in ('CSNG', 'CDBL'): return float(a)
        if name in ('MEM', 'FRE'): return 24576
        if name == 'ERL': return self.erl
        if name == 'ERR': return self.err
        if name == 'POINT': return -1 if self.point(int(args[0]), int(args[1])) else 0
        if name == 'COLORAT':
            x, y = int(args[0]), int(args[1])
            self.point(x, y)
            return self.pixel_colors.get(y * 128 + x, self.color_fg)
        if name == 'INKEY$': return self.poll_key()
        if name == 'PEEK':
            addr = int(a)
            if 46240 <= addr <= 46287:
                return self.palette_bytes[addr - 46240]
            # No joystick is plugged in, so the stick reads as absent.
            if addr in (46295, 46296, 46297, 46298, 46299, 46300, 46301, 46302):
                return 0
            if addr == 46304:
                return self.gpio_out
            if addr == 46305:
                return 0
            if addr in (46292, 46293, 46294):
                return 0
            if addr == 14400:
                key = self.poll_key()
                return ord(key) if key else 0
            if 15360 <= addr < 16384:
                return ord(self.screen[(addr-15360)//64][(addr-15360)%64])
            raise ValueError('unsupported PEEK address')
        if name == 'POS': return self.cursor % 64
        if name[:1].isalpha() and self.canon(name) in self.arrays:
            return self.array_get(name, args)
        raise ValueError('unknown function ' + name)

    def point(self, x, y):
        if not (0 <= x < 128 and 0 <= y < 48):
            raise ValueError('FC')
        bit = y * 128 + x
        return (self.pixels[bit // 8] >> (bit % 8)) & 1

    def graphics(self, command, body):
        args = split_top(body.strip()[1:-1], ',')
        x, y = int(self.eval(args[0])), int(self.eval(args[1]))
        self.point(x, y)
        bit = y * 128 + x
        if command == 'SET':
            self.pixels[bit // 8] |= 1 << (bit % 8)
            if len(args) > 2:
                self.pixel_colors[bit] = int(self.eval(args[2])) & 15
        else:
            self.pixels[bit // 8] &= ~(1 << (bit % 8))
            self.pixel_colors.pop(bit, None)
        self.dirty = True

    def set_var(self, target, value):
        target = target.strip()
        if '(' in target:
            name, sub = target.split('(', 1)
            if not sub.endswith(')'):
                raise ValueError('bad subscript')
            indexes = [self.eval(x) for x in split_top(sub[:-1], ',')]
            self.array_set(name, indexes, value)
            return
        key = self.canon(target)
        if key.endswith('$'):
            if not isinstance(value, str):
                raise ValueError('type mismatch')
        elif isinstance(value, str):
            raise ValueError('type mismatch')
        elif key.endswith('%'):
            # DEFINT truncates toward zero. CINT is the one that would round.
            value = int(float(value))
        else:
            value = float(value)
        self.vars[key] = value

    def tab_to(self, column):
        column = int(column)
        if column < 0:
            raise ValueError('FC')
        column %= 64
        here = self.cursor % 64
        if here > column:
            self.emit('\n')
            here = 0
        if column > here:
            self.emit(' ' * (column - here))

    def print_text(self, text):
        parts, separators, quoted, depth, start = [], [], False, 0, 0
        for i, ch in enumerate(text):
            if ch == '"': quoted = not quoted
            elif not quoted:
                if ch == '(': depth += 1
                elif ch == ')': depth -= 1
                elif depth == 0 and ch in ';,':
                    parts.append(text[start:i].strip())
                    separators.append(ch)
                    start = i + 1
        parts.append(text[start:].strip())
        for i, part in enumerate(parts):
            folded = part.upper().replace(' ', '')
            if folded.startswith('TAB(') and folded.endswith(')'):
                self.tab_to(self.eval(part[part.upper().find('(') + 1:-1]))
            elif folded.startswith('SPC(') and folded.endswith(')'):
                count = int(self.eval(part[part.upper().find('(') + 1:-1]))
                if count > 0:
                    self.emit(' ' * count)
            elif part:
                self.emit(printable(self.eval(part)))
            if i < len(separators) and separators[i] == ',': self.emit(' ' * 8)
        if not separators or len(parts[-1]) or text[-1:] not in ';,':
            self.emit('\n')

    def print_using(self, text):
        """PRINT USING with # numeric fields. Other characters are copied."""
        sep = ';' if ';' in text else ','
        pieces = split_top(text, sep)
        fmt = self.eval(pieces[0])
        if not isinstance(fmt, str):
            raise ValueError('type mismatch')
        values = [self.eval(piece) for piece in pieces[1:] if piece]
        out, vi, i = [], 0, 0
        while i < len(fmt):
            if fmt[i] == '#':
                j = i
                while j < len(fmt) and fmt[j] in '#.':
                    j += 1
                field = fmt[i:j]
                number = float(values[vi])
                vi += 1
                if '.' in field:
                    shown = ('%.' + str(len(field.split('.', 1)[1])) + 'f') % number
                else:
                    shown = str(int(round(number)))
                if len(shown) < len(field):
                    shown = ' ' * (len(field) - len(shown)) + shown
                out.append(shown)
                i = j
            else:
                out.append(fmt[i])
                i += 1
        self.emit(''.join(out))
        if text[-1:] not in ';,':
            self.emit('\n')

    def statements(self, source):
        # IF owns the remainder of its line, including THEN/ELSE colons.
        result = []
        for part in split_top(source, ':'):
            head = result[-1].lstrip().upper() if result else ''
            # IF owns the rest of the line. REM and DATA own a colon too.
            if head.startswith('IF ') or head.startswith('IF') and not _alnum(head[2:3]) or head.startswith('REM') or head.startswith('DATA'):
                result[-1] += ':' + part
            else:
                result.append(part)
        return result

    def run(self, start=None, fresh=True):
        if fresh:
            self.reset(clear_fn=True)
        else:
            self.data = []
        self.code = []
        for number in sorted(self.program):
            for statement in self.statements(self.program[number]):
                self.code.append((number, statement))
                if statement.upper().startswith('DATA '):
                    self.data.extend(split_top(statement[5:], ','))
        resume_at = self.pc
        self.pc = self.jump(start) if start is not None else (0 if fresh else resume_at)
        self.running = True
        while self.running and self.pc < len(self.code):
            number, statement = self.code[self.pc]
            self.pc += 1
            try:
                self.check_break()
                self.execute(statement)
            except KeyboardInterrupt:
                self.running = False
                self.keep_cont = True
                self.cont_pc = self.pc
                self.emit('BREAK IN ' + str(number) + '\n')
            except (ValueError, ZeroDivisionError, IndexError, KeyError, TypeError) as exc:
                self.erl = number
                text = str(exc)
                # ERROR n raises 'ERR n'. Other faults stay non-zero so ON ERROR can see them.
                self.err = int(text[4:]) if text.startswith('ERR ') and text[4:].isdigit() else 2
                if self.on_error is not None and not self.in_error:
                    # Resume retries this statement. pc already points at the next one.
                    self.resume_pc = self.pc
                    self.in_error = True
                    self.pc = self.jump(self.on_error)
                else:
                    self.running = False
                    self.emit('?ERROR ' + str(exc) + ' IN ' + str(number) + '\n')
        self.running = False
        if not self.keep_cont:
            self.cont_pc = None
        self.refresh()

    def list_lines(self, spec):
        """LIST, LIST n (from n on), LIST n-m, LIST n-, LIST -m."""
        spec = spec.strip()
        lo = hi = None
        if spec and spec != '-':
            if '-' in spec:
                left, right = spec.split('-', 1)
                lo = int(left) if left.strip() else None
                hi = int(right) if right.strip() else None
            else:
                lo = int(spec)
        for number in sorted(self.program):
            if lo is not None and number < lo:
                continue
            if hi is not None and number > hi:
                continue
            self.emit(str(number) + ' ' + self.program[number] + '\n')

    def execute_parts(self, parts):
        """Colon statements inside IF. A GOSUB returns to the rest of this chain."""
        for index, part in enumerate(parts):
            if not self.running:
                return True
            word, body = statement_word(part.strip())
            if word == 'GOTO':
                self.pc = self.jump(self.eval(body))
                return True
            if word == 'GOSUB':
                self.gosubs.append((self.pc, len(self.loops), parts[index + 1:]))
                self.pc = self.jump(self.eval(body))
                return True
            if word in ('RETURN', 'RUN', 'END', 'STOP', 'RESUME'):
                self.execute(part)
                return True
            self.execute(part)
        return False

    def jump(self, number):
        for i, (n, _) in enumerate(self.code):
            if n == int(number): return i
        raise ValueError('undefined line ' + printable(number))

    def _for_next(self, name):
        """Statement index of the NEXT that closes this FOR. pc is already past the FOR."""
        depth = 0
        i = self.pc
        while i < len(self.code):
            word, body = statement_word(self.code[i][1].strip())
            if word == 'FOR':
                depth += 1
            elif word == 'NEXT':
                names = [self.canon(part) for part in body.split(',') if part.strip()] if body.strip() else []
                if depth <= 0 and (not names or name in names):
                    return i
                depth -= len(names) if names else 1
            i += 1
        return None

    def save_program(self, name):
        from microtrs_hw import open_storage
        with open_storage(name, write=True) as target:
            for n in sorted(self.program):
                target.write(str(n) + ' ' + self.program[n] + '\n')
        self.emit('SAVED ' + str(len(self.program)) + ' LINES\n')

    def load_program(self, name):
        from microtrs_hw import open_storage
        loaded = {}
        with open_storage(name, write=False) as source:
            for raw in source:
                raw = raw.strip()
                if not raw: continue
                number, sep, body = raw.partition(' ')
                if not number.isdigit() or not sep:
                    raise ValueError('invalid BASIC line')
                loaded[int(number)] = body
        self.program = loaded
        self.emit('LOADED ' + str(len(loaded)) + ' LINES\n')

    def execute(self, statement):
        s = statement.strip()
        if not s: return
        word, body = statement_word(s)
        if word in ('REM', 'DATA'): return
        if word in ('DEFINT', 'DEFSNG', 'DEFSTR', 'DEFDBL'):
            mark = {'DEFINT': '%', 'DEFSTR': '$', 'DEFSNG': '', 'DEFDBL': ''}[word]
            for part in body.upper().split(','):
                part = part.strip()
                if not part: continue
                if '-' in part:
                    left, right = part.split('-', 1)
                    for code in range(ord(left.strip()[0]), ord(right.strip()[0]) + 1):
                        self.deftype[chr(code)] = mark
                else:
                    self.deftype[part[0]] = mark
            return
        if word == 'DEF':
            # DEF FNR(R)=expr. The call name is FNR, including the FN.
            text = body.strip()
            name, rest = text.split('(', 1)
            param, expr = rest.split(')=', 1)
            self.fns[name.strip().upper()] = (self.canon(param), expr.strip())
            return
        _no_assign = ('IF', 'FOR', 'PRINT', 'PRINT@', 'PRINT#', 'REM', 'DATA', 'DEF',
                      'ON', 'GOTO', 'GOSUB', 'NEXT', 'INPUT', 'INPUT#', 'READ')
        if word == 'LET' or '=' in s and word not in _no_assign:
            lhs, rhs = (body if word == 'LET' else s).split('=', 1)
            self.set_var(lhs, self.eval(rhs))
        elif word == 'PRINT' or word == 'PRINT@':
            if word == 'PRINT' and body.upper().startswith('USING '):
                self.print_using(body[6:].strip())
            elif word == 'PRINT@':
                pos, rest = split_top(s[6:].strip(), ',')[0], split_top(s[6:].strip(), ',')
                n = int(self.eval(pos))
                if not 0 <= n < 1024: raise ValueError('FC')
                value = ''.join(printable(self.eval(x)) for x in rest[1:] if x)
                for i, ch in enumerate(value):
                    if n + i < 1024:
                        self.screen[(n+i)//64][(n+i)%64] = ch
                        self.text_colors[n+i] = self.color_fg
                self.dirty = True
            else: self.print_text(body)
            # A running program refreshes from the run loop. Immediate PRINT
            # still draws before the command returns.
            if not self.running:
                self.refresh()
        elif word == 'CLS':
            self.screen = [[' '] * 64 for _ in range(16)]
            self.pixels = bytearray(len(self.pixels))
            self.pixel_colors = {}
            self.text_colors = bytearray([self.color_fg] * 1024)
            self.cursor = 0
            self.dirty = True
            self.output('\x1b[2J\x1b[H')
            self.refresh()
        elif word in ('SET', 'RESET'):
            self.graphics(word, body)
        elif word == 'COLOR':
            # E-ink is black on white. Accept the command so card programs
            # do not stop, and remember a legal index for COLORAT.
            try:
                colors = [int(self.eval(x)) for x in split_top(body, ',') if x.strip()]
            except (ValueError, ZeroDivisionError, IndexError, KeyError, TypeError):
                return
            if colors and 0 <= colors[0] <= 15:
                self.color_fg = colors[0]
            if len(colors) > 1 and 0 <= colors[1] <= 15:
                self.color_bg = colors[1]
        elif word == 'SOUND':
            items = [int(self.eval(x)) for x in split_top(body, ',')]
            if not 0 <= items[0] <= 65535 or len(items) > 1 and not 0 <= items[1] <= 65535:
                raise ValueError('FC')
            if self.hardware: self.hardware.tone(items[0], items[1] if len(items) > 1 else 0)
        elif word == 'BEEP':
            if self.hardware: self.hardware.tone(880, 250)
        elif word == 'RANDOM': random.seed()
        elif word == 'CLEAR':
            # Stay on this line. CLEAR drops variables, not the program or DEF types.
            self.vars, self.arrays, self.loops, self.gosubs = {}, {}, [], []
            self.data_pos = 0
        elif word == 'POKE':
            items = [int(self.eval(x)) for x in split_top(body, ',')]
            if len(items) != 2 or not 0 <= items[1] <= 255:
                raise ValueError('unsupported POKE address/value')
            if 46240 <= items[0] <= 46287:
                self.palette_bytes[items[0] - 46240] = items[1] & 255
                return
            if items[0] == 46304:
                self.gpio_out = items[1] & 255
                return
            if not 15360 <= items[0] < 16384:
                raise ValueError('unsupported POKE address/value')
            pos = items[0] - 15360
            self.screen[pos//64][pos%64] = chr(items[1])
            self.dirty = True
            self.refresh()
        elif word.startswith('INPUT#'):
            name = s.split(',', 1)[1].strip()
            if s.upper().startswith('INPUT#-1'):
                if self.tape is None: raise ValueError('no tape; use TAPE filename')
                if self.tape_mode != 'I': raise ValueError('tape is output only')
                source = self.tape
                missing = 'end of tape'
            elif self.channel is not None and self.channel[0] == 'I':
                source = self.channel[1]
                missing = 'end of file'
            else:
                raise ValueError('no input channel')
            value = source.readline()
            if not value: raise ValueError(missing)
            self.set_var(name, value.rstrip('\r\n') if self.canon(name).endswith('$') else float(value))
        elif word.startswith('PRINT#'):
            value = s.split(',', 1)[1].strip()
            if s.upper().startswith('PRINT#-1'):
                if self.tape is None or self.tape_mode != 'O': raise ValueError('no output tape')
                self.tape.write(printable(self.eval(value)) + '\n')
                self.tape.flush()
            elif self.channel is not None and self.channel[0] == 'O':
                self.channel[1].write(printable(self.eval(value)) + '\n')
            else: raise ValueError('no output channel')
        elif word == 'OPEN':
            from microtrs_hw import open_storage
            args = split_top(body, ',')
            if len(args) != 3: raise ValueError('OPEN mode,#n,filename')
            mode = self.eval(args[0]).upper()
            if mode not in ('I', 'O'): raise ValueError('invalid mode')
            self.close_channel()
            self.channel = (mode, open_storage(self.eval(args[2]), write=(mode == 'O')))
        elif word == 'CLOSE': self.close_channel()
        elif word == 'LINE' and body.upper().startswith('INPUT#'):
            if self.channel is None or self.channel[0] != 'I': raise ValueError('no input channel')
            value = self.channel[1].readline()
            if not value: raise ValueError('end of file')
            self.set_var(body.split(',', 1)[1].strip(), value.rstrip('\r\n'))
        elif word == 'GOTO': self.pc = self.jump(self.eval(body))
        elif word == 'ON':
            upper = body.upper()
            if upper.startswith('ERROR'):
                rest = body[5:].strip()
                if not rest.upper().startswith('GOTO'):
                    raise ValueError('ON ERROR GOTO')
                target = rest[4:].strip()
                self.on_error = None if target == '0' else int(self.eval(target) if not target.isdigit() else target)
            else:
                marker = ' GOSUB ' if ' GOSUB ' in upper else ' GOTO '
                at = upper.find(marker)
                if at < 0: raise ValueError('ON needs GOTO or GOSUB')
                selector = int(self.eval(body[:at]))
                targets = split_top(body[at+len(marker):], ',')
                if 1 <= selector <= len(targets):
                    if marker == ' GOSUB ': self.gosubs.append((self.pc, len(self.loops), []))
                    self.pc = self.jump(self.eval(targets[selector-1]))
        elif word == 'GOSUB':
            # Remember how deep FOR was, so RETURN can drop loops opened in the sub.
            self.gosubs.append((self.pc, len(self.loops), []))
            self.pc = self.jump(self.eval(body))
        elif word == 'RETURN':
            if not self.gosubs:
                raise ValueError('RG')
            back, depth, after = self.gosubs.pop()
            del self.loops[depth:]
            # after is the rest of an IF chain, such as GOTO 9900 following GOSUB.
            if not after or not self.execute_parts(after):
                self.pc = back
        elif word == 'RESUME':
            if self.resume_pc is None:
                raise ValueError('RESUME without error')
            mode = body.upper()
            if mode == 'NEXT':
                self.pc = self.resume_pc
            elif body:
                self.pc = self.jump(self.eval(body))
            else:
                self.pc = self.resume_pc - 1
            self.resume_pc = None
            self.in_error = False
        elif word == 'ERROR':
            raise ValueError('ERR ' + str(int(self.eval(body))))
        elif word == 'STOP':
            self.running = False
            self.keep_cont = True
            self.cont_pc = self.pc
        elif word == 'END':
            self.running = False
            self.cont_pc = None
        elif word == 'IF':
            upper = body.upper()
            pos = upper.find(' THEN ')
            if pos < 0: raise ValueError('missing THEN')
            condition, clause = body[:pos], body[pos+6:]
            # ELSE inside a nested IF belongs to that IF, not this one.
            branch = _else_at(clause)
            selected = clause[:branch] if branch >= 0 else clause
            if not self.eval(condition): selected = clause[branch+4:] if branch >= 0 else ''
            if selected:
                if selected.strip().isdigit(): self.pc = self.jump(int(selected.strip()))
                else:
                    self.execute_parts(self.statements(selected))
        elif word == 'FOR':
            name, spec = body.split('=', 1)
            name = self.canon(name)
            p = spec.upper().find(' TO ')
            if p < 0: raise ValueError('missing TO')
            tail = spec[p+4:]
            q = tail.upper().find(' STEP ')
            start, end = self.eval(spec[:p]), self.eval(tail[:q] if q >= 0 else tail)
            step = self.eval(tail[q+6:]) if q >= 0 else 1
            if step == 0: raise ValueError('FC')
            self.set_var(name, start)
            # FOR I while FOR I/J are live drops J too. Level II NEXT J is then ?NF.
            for i, loop in enumerate(self.loops):
                if loop[0] == name:
                    self.loops = self.loops[:i]
                    break
            self.loops.append((name, end, step, self.pc))
            # FOR 5 TO 1 never enters the body. Land on its NEXT, which closes it.
            if (step > 0 and start > end) or (step < 0 and start < end):
                at = self._for_next(name)
                if at is None:
                    raise ValueError('FOR without NEXT')
                self.pc = at
        elif word == 'NEXT':
            names = [self.canon(x) for x in body.split(',')] if body else ['']
            for name in names:
                if not self.loops: raise ValueError('NEXT without FOR')
                name0, end, step, resume = self.loops[-1]
                if name and name != name0: raise ValueError('NEXT mismatch')
                value = self.vars[name0] + step
                self.set_var(name0, value)
                if value <= end if step > 0 else value >= end:
                    self.pc = resume
                    break
                self.loops.pop()
        elif word == 'INPUT':
            chunks = split_top(body, ';')
            if len(chunks) > 1:
                self.emit(printable(self.eval(chunks[0])))
                body = chunks[-1]
            self.refresh()
            for name in split_top(body, ','):
                answer = self.input_fn('? ')
                if self.canon(name).endswith('$'):
                    self.set_var(name, answer)
                else:
                    self.set_var(name, float(answer) if str(answer).strip() else 0)
        elif word == 'DIM':
            for item in split_top(body, ','):
                name, size = item.split('(', 1)
                dims = [int(self.eval(x)) for x in split_top(size[:-1], ',')]
                key = self.canon(name)
                self.arrays[key] = make_array(dims, '' if key.endswith('$') else 0)
        elif word == 'READ':
            for name in split_top(body, ','):
                if self.data_pos >= len(self.data): raise ValueError('out of DATA')
                raw = self.data[self.data_pos].strip().strip('"')
                self.data_pos += 1
                self.set_var(name, raw if self.canon(name).endswith('$') else float(raw))
        elif word == 'RESTORE': self.data_pos = 0
        elif word == 'RUN':
            # Restart here. The nested run() finishes the program; this frame then stops.
            self.run(int(self.eval(body)) if body.strip() else None)
            self.running = False
        elif word == 'CONT':
            raise ValueError('CN')
        elif word in ('SAVE', 'CSAVE'):
            self.save_program(body.strip())
        elif word in ('LOAD', 'CLOAD'):
            self.load_program(body.strip())
            # The loaded program replaces this one. Stop, instead of falling into what follows.
            self.running = False
        else: raise ValueError('unknown command ' + word)

    def close_channel(self):
        if self.channel is not None:
            self.channel[1].close()
            self.channel = None

    def close_tape(self):
        if self.tape is not None:
            self.tape.close()
            self.tape = None

    def command(self, line):
        line = line.strip()
        if not line: return
        upper = line.upper()
        if upper.startswith('CLOAD'):
            line = 'LOAD' + line[5:]
        elif upper.startswith('CSAVE'):
            line = 'SAVE' + line[5:]
        first = line.split(None, 1)[0]
        if first.isdigit():
            number = int(first)
            if number < 0 or number > 65535: raise ValueError('line range')
            tail = line[len(first):].strip()
            if tail: self.program[number] = tail
            else: self.program.pop(number, None)
        elif line.upper() == 'RUN': self.run()
        elif line.upper().startswith('RUN '): self.run(int(line[4:]))
        elif line.upper() == 'LIST' or line.upper().startswith('LIST '):
            self.list_lines(line[4:].strip())
        elif line.upper() == 'CONT':
            if self.cont_pc is None:
                raise ValueError('cannot CONT')
            self.pc = self.cont_pc
            self.keep_cont = False
            self.run(fresh=False)
        elif line.upper().startswith('EDIT '):
            number = int(line[5:].strip())
            if number not in self.program:
                raise ValueError('undefined line ' + str(number))
            self.emit(str(number) + ' ' + self.program[number] + '\n')
            replacement = self.input_fn('')
            if str(replacement).strip():
                self.program[number] = str(replacement).strip()
                self.cont_pc = None
        elif line.upper() == 'VERSION':
            self.emit('TRS-80 BASIC\n')
        elif line.upper() == 'NEW':
            self.program = {}
            self.reset(clear_fn=True)
            self.color_fg, self.color_bg = 1, 0
        elif line.upper() == 'DIR':
            from microtrs_hw import list_sd
            for name in list_sd():
                self.emit(name + '\n')
        elif line.upper().startswith('REMOVE '):
            from microtrs_hw import remove_sd
            remove_sd(line[7:].strip())
            self.emit('REMOVED\n')
        elif line.upper().startswith('LOAD '):
            self.load_program(line[5:].strip())
        elif line.upper().startswith('SAVE '):
            self.save_program(line[5:].strip())
        elif line.upper().startswith('TAPE '):
            from microtrs_hw import open_storage
            self.close_tape()
            self.tape = open_storage(line[5:].strip(), write=False)
            self.tape_mode = 'I'
            self.emit('TAPE READY\n')
        elif line.upper().startswith('TAPEOUT '):
            from microtrs_hw import open_storage
            self.close_tape()
            self.tape = open_storage(line[8:].strip(), write=True)
            self.tape_mode = 'O'
            self.emit('OUTPUT TAPE READY\n')
        elif line.upper() == 'TAPECLOSE': self.close_tape()
        elif line.upper() == 'SCREEN':
            for row in self.screen: self.output(''.join(row) + '\n')
        elif line.upper() == 'HELP BASIC':
            self.emit('LET REM END STOP CONT IF FOR NEXT GOTO GOSUB ON ERROR RESUME.\n')
            self.emit('PRINT ? TAB USING INPUT DEF FN DEFINT DEFSTR STRING$ INSTR.\n')
            self.emit('FIX CINT CSNG MEM FRE ERR ERL. EDIT n. LIST n-m.\n')
        elif line.upper() == 'HELP':
            self.emit('RUN LIST NEW LOAD SAVE DIR REMOVE TAPE SCREEN HELP. Esc breaks a running program.\n')
        else: self.execute(line)
        # One panel update after the command, including text emit() just stored.
        self.refresh()


def read_line(basic, prompt=''):
    """Read one console line. Echo goes to USB serial and the 64x16 screen."""
    if prompt:
        basic.emit(prompt)
    line = []
    while True:
        ch = sys.stdin.read(1)
        if not ch:
            continue
        if ch in '\r\n':
            basic.emit('\n')
            return ''.join(line)
        if ch in '\x08\x7f':
            if line:
                line.pop()
                basic.emit('\x08 \x08')
            continue
        if ch == '\x1b':
            # Esc breaks a running program. At READY it does nothing.
            if basic.running:
                raise KeyboardInterrupt
            continue
        if ch == '\x03':
            raise KeyboardInterrupt
        if ord(ch) < 32:
            continue
        line.append(ch)
        basic.emit(ch)


def main():
    try:
        from microtrs_hw import Hardware
        hardware = Hardware()
    except (ImportError, OSError, ValueError) as exc:
        print('Hardware unavailable:', exc)
        hardware = None
    basic = Basic(hardware=hardware)
    basic.input_fn = lambda prompt='': read_line(basic, prompt)
    basic.emit('TRS-80 BASIC\nType HELP.\n')
    basic.refresh()
    while True:
        try:
            basic.command(read_line(basic, 'READY> '))
        except KeyboardInterrupt:
            basic.emit('\nBREAK\n')
            basic.refresh()
        except Exception as exc:
            basic.emit('?ERROR ' + str(exc) + '\n')
            basic.refresh()


if __name__ == '__main__':
    main()
