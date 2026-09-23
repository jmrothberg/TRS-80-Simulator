"""TRS-80 inspired Level II BASIC for ESP32 MicroPython USB serial.

The interpreter runs on the microcontroller.  No Tkinter, browser, network,
or external packages are required.  See README.md for supported syntax.
"""

import math
import random
import sys
import os
import time

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
            while j < len(s) and (s[j].isalnum() or s[j] in '_$'):
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
            right = self.expr(7)
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
                left = self.machine.call(value, []) if value in ('INKEY$', 'RND') else self.machine.vars.get(value, '' if value.endswith('$') else 0)
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
    if isinstance(value, str):
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


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
        self.poller = None
        if select is not None:
            try:
                self.poller = select.poll()
                self.poller.register(sys.stdin, select.POLLIN)
            except (AttributeError, OSError, TypeError):
                self.poller = None
        self.reset()

    def reset(self):
        self.vars, self.arrays, self.loops, self.gosubs = {}, {}, [], []
        self.data, self.data_pos = [], 0
        self.pc = 0
        self.running = False

    def poll_key(self):
        if self.keys:
            return self.keys.pop(0)
        if self.poller is not None and self.poller.poll(0):
            return sys.stdin.read(1)
        return ''

    def screen_write(self, text):
        if text: self.dirty = True
        for char in text:
            if char == '\n':
                self.cursor = ((self.cursor // 64) + 1) * 64
            elif char == '\r':
                self.cursor -= self.cursor % 64
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
            self.hardware.draw(self)
            self.dirty = False

    def eval(self, text):
        return Expression(self, text.strip()).parse()

    def call(self, name, args):
        a = args[0] if args else 0
        if name in self.arrays:
            return self.arrays[name][int(a)]
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
        if name == 'VAL': return float(a)
        if name == 'STR$': return ' ' + printable(a) if a >= 0 else printable(a)
        if name == 'CHR$': return chr(int(a))
        if name == 'ASC': return ord(a[0])
        if name == 'LEFT$': return args[0][:int(args[1])]
        if name == 'RIGHT$': return args[0][-int(args[1]):]
        if name == 'MID$': return args[0][int(args[1])-1:int(args[1])-1+int(args[2])] if len(args) > 2 else args[0][int(args[1])-1:]
        if name == 'POINT': return self.point(int(args[0]), int(args[1]))
        if name == 'COLORAT':
            x, y = int(args[0]), int(args[1])
            self.point(x, y)
            return self.pixel_colors.get(y * 128 + x, self.color_fg)
        if name == 'INKEY$': return self.poll_key()
        if name == 'PEEK':
            addr = int(a)
            if addr == 14400:
                key = self.poll_key()
                return ord(key) if key else 0
            if 15360 <= addr < 16384:
                return ord(self.screen[(addr-15360)//64][(addr-15360)%64])
            raise ValueError('unsupported PEEK address')
        if name == 'POS': return self.cursor % 64
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
        target = target.strip().upper()
        if '(' in target:
            name, sub = target.split('(', 1)
            self.arrays[name][int(self.eval(sub[:-1]))] = value
        else:
            if target.endswith('$') != isinstance(value, str):
                raise ValueError('type mismatch')
            self.vars[target] = value

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
            if part: self.emit(printable(self.eval(part)))
            if i < len(separators) and separators[i] == ',': self.emit(' ' * 8)
        if not separators or len(parts[-1]) or text[-1:] not in ';,':
            self.emit('\n')

    def statements(self, source):
        # IF owns the remainder of its line, including THEN/ELSE colons.
        result = []
        for part in split_top(source, ':'):
            if result and result[-1].lstrip().upper().startswith('IF '):
                result[-1] += ':' + part
            else:
                result.append(part)
        return result

    def run(self, start=None):
        self.reset()
        self.data = []
        self.code = []
        for number in sorted(self.program):
            for statement in self.statements(self.program[number]):
                self.code.append((number, statement))
                if statement.upper().startswith('DATA '):
                    self.data.extend(split_top(statement[5:], ','))
        self.pc = self.jump(start) if start is not None else 0
        self.running = True
        steps = 0
        last_draw = time.ticks_ms() if hasattr(time, 'ticks_ms') else 0
        while self.running and self.pc < len(self.code):
            number, statement = self.code[self.pc]
            self.pc += 1
            try:
                self.execute(statement)
                steps += 1
                if self.hardware is not None and steps % 64 == 0:
                    now = time.ticks_ms() if hasattr(time, 'ticks_ms') else 0
                    if not last_draw or time.ticks_diff(now, last_draw) >= 200:
                        self.refresh()
                        last_draw = now
            except (ValueError, ZeroDivisionError, IndexError, KeyError, TypeError) as exc:
                self.running = False
                self.output('?ERROR ' + str(exc) + ' IN ' + str(number) + '\n')
        self.running = False
        self.refresh()

    def jump(self, number):
        for i, (n, _) in enumerate(self.code):
            if n == int(number): return i
        raise ValueError('undefined line ' + printable(number))

    def execute(self, statement):
        s = statement.strip()
        if not s: return
        word = s.split(None, 1)[0].upper()
        body = s[len(word):].strip()
        for compact in ('SET', 'RESET', 'PRINT@', 'PRINT#', 'INPUT#'):
            if s.upper().startswith(compact + '(') or compact in ('PRINT@', 'PRINT#', 'INPUT#') and s.upper().startswith(compact):
                word, body = compact, s[len(compact):].strip()
                break
        if word in ('REM', 'DATA'): return
        if word == 'LET' or '=' in s and word not in ('IF', 'FOR', 'PRINT', 'PRINT@', 'PRINT#', 'REM', 'DATA'):
            lhs, rhs = (body if word == 'LET' else s).split('=', 1)
            self.set_var(lhs, self.eval(rhs))
        elif word == 'PRINT' or s.upper().startswith('PRINT@'):
            if s.upper().startswith('PRINT@'):
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
            colors = [int(self.eval(x)) for x in split_top(body, ',')]
            if len(colors) != 2 or any(x < 0 or x > 15 for x in colors):
                raise ValueError('FC')
            self.color_fg, self.color_bg = colors
        elif word == 'SOUND':
            items = [int(self.eval(x)) for x in split_top(body, ',')]
            if not 0 <= items[0] <= 65535 or len(items) > 1 and not 0 <= items[1] <= 65535:
                raise ValueError('FC')
            if self.hardware: self.hardware.tone(items[0], items[1] if len(items) > 1 else 0)
        elif word == 'BEEP':
            if self.hardware: self.hardware.tone(880, 250)
        elif word == 'RANDOM': random.seed()
        elif word == 'CLEAR': self.reset()
        elif word == 'POKE':
            items = [int(self.eval(x)) for x in split_top(body, ',')]
            if len(items) != 2 or not 15360 <= items[0] < 16384 or not 0 <= items[1] <= 255:
                raise ValueError('unsupported POKE address/value')
            pos = items[0] - 15360
            self.screen[pos//64][pos%64] = chr(items[1])
            self.dirty = True
            self.refresh()
        elif word.startswith('INPUT#'):
            if self.tape is None: raise ValueError('no tape; use TAPE filename')
            if self.tape_mode != 'I': raise ValueError('tape is output only')
            name = s.split(',', 1)[1].strip()
            value = self.tape.readline()
            if not value: raise ValueError('end of tape')
            self.set_var(name, value.rstrip('\r\n') if name.endswith('$') else float(value))
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
            from microtrs_hw import storage_path
            args = split_top(body, ',')
            if len(args) != 3: raise ValueError('OPEN mode,#n,filename')
            mode = self.eval(args[0]).upper()
            if mode not in ('I', 'O'): raise ValueError('invalid mode')
            self.close_channel()
            self.channel = (mode, open(storage_path(self.eval(args[2])), 'r' if mode == 'I' else 'w'))
        elif word == 'CLOSE': self.close_channel()
        elif word == 'LINE' and body.upper().startswith('INPUT#'):
            if self.channel is None or self.channel[0] != 'I': raise ValueError('no input channel')
            value = self.channel[1].readline()
            if not value: raise ValueError('end of file')
            self.set_var(body.split(',', 1)[1].strip(), value.rstrip('\r\n'))
        elif word == 'GOTO': self.pc = self.jump(self.eval(body))
        elif word == 'ON':
            upper = body.upper()
            marker = ' GOSUB ' if ' GOSUB ' in upper else ' GOTO '
            at = upper.find(marker)
            if at < 0: raise ValueError('ON needs GOTO or GOSUB')
            selector = int(self.eval(body[:at]))
            targets = split_top(body[at+len(marker):], ',')
            if 1 <= selector <= len(targets):
                if marker == ' GOSUB ': self.gosubs.append(self.pc)
                self.pc = self.jump(self.eval(targets[selector-1]))
        elif word == 'GOSUB':
            self.gosubs.append(self.pc)
            self.pc = self.jump(self.eval(body))
        elif word == 'RETURN': self.pc = self.gosubs.pop()
        elif word in ('END', 'STOP'): self.running = False
        elif word == 'IF':
            upper = body.upper()
            pos = upper.find(' THEN ')
            if pos < 0: raise ValueError('missing THEN')
            condition, clause = body[:pos], body[pos+6:]
            # ELSE is recognized outside quotes only.
            branch = clause.upper().find(' ELSE ')
            selected = clause[:branch] if branch >= 0 else clause
            if not self.eval(condition): selected = clause[branch+6:] if branch >= 0 else ''
            if selected:
                if selected.strip().isdigit(): self.pc = self.jump(int(selected.strip()))
                else:
                    for part in self.statements(selected): self.execute(part)
        elif word == 'FOR':
            name, spec = body.split('=', 1)
            name = name.strip().upper()
            p = spec.upper().find(' TO ')
            if p < 0: raise ValueError('missing TO')
            tail = spec[p+4:]
            q = tail.upper().find(' STEP ')
            start, end = self.eval(spec[:p]), self.eval(tail[:q] if q >= 0 else tail)
            step = self.eval(tail[q+6:]) if q >= 0 else 1
            if step == 0: raise ValueError('FC')
            self.set_var(name, start)
            self.loops = [loop for loop in self.loops if loop[0] != name]
            self.loops.append((name, end, step, self.pc))
        elif word == 'NEXT':
            names = [x.strip().upper() for x in body.split(',')] if body else ['']
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
                self.output(printable(self.eval(chunks[0])))
                body = chunks[-1]
            for name in split_top(body, ','):
                answer = self.input_fn('? ')
                self.set_var(name, answer if name.strip().endswith('$') else float(answer))
        elif word == 'DIM':
            for item in split_top(body, ','):
                name, size = item.split('(', 1)
                self.arrays[name.strip().upper()] = [0] * (int(self.eval(size[:-1])) + 1)
        elif word == 'READ':
            for name in split_top(body, ','):
                if self.data_pos >= len(self.data): raise ValueError('out of DATA')
                raw = self.data[self.data_pos].strip().strip('"')
                self.data_pos += 1
                self.set_var(name, raw if name.endswith('$') else float(raw))
        elif word == 'RESTORE': self.data_pos = 0
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
        first = line.split(None, 1)[0]
        if first.isdigit():
            number = int(first)
            if number < 0 or number > 65535: raise ValueError('line range')
            tail = line[len(first):].strip()
            if tail: self.program[number] = tail
            else: self.program.pop(number, None)
        elif line.upper() == 'RUN': self.run()
        elif line.upper().startswith('RUN '): self.run(int(line[4:]))
        elif line.upper() == 'LIST':
            for n in sorted(self.program): self.output(str(n) + ' ' + self.program[n] + '\n')
        elif line.upper() == 'NEW':
            self.program = {}
            self.reset()
        elif line.upper().startswith('LOAD '):
            from microtrs_hw import storage_path
            path = storage_path(line[5:].strip())
            loaded = {}
            with open(path, 'r') as source:
                for raw in source:
                    raw = raw.strip()
                    if not raw: continue
                    number, sep, body = raw.partition(' ')
                    if not number.isdigit() or not sep:
                        raise ValueError('invalid BASIC line in ' + path)
                    loaded[int(number)] = body
            self.program = loaded
            self.output('LOADED ' + str(len(loaded)) + ' LINES\n')
        elif line.upper().startswith('SAVE '):
            from microtrs_hw import storage_path
            path = storage_path(line[5:].strip())
            with open(path, 'w') as target:
                for n in sorted(self.program):
                    target.write(str(n) + ' ' + self.program[n] + '\n')
            self.output('SAVED ' + str(len(self.program)) + ' LINES\n')
        elif line.upper().startswith('TAPE '):
            from microtrs_hw import storage_path
            self.close_tape()
            self.tape = open(storage_path(line[5:].strip()), 'r')
            self.tape_mode = 'I'
            self.output('TAPE READY\n')
        elif line.upper().startswith('TAPEOUT '):
            from microtrs_hw import storage_path
            self.close_tape()
            self.tape = open(storage_path(line[8:].strip()), 'w')
            self.tape_mode = 'O'
            self.output('OUTPUT TAPE READY\n')
        elif line.upper() == 'TAPECLOSE': self.close_tape()
        elif line.upper() == 'SCREEN':
            for row in self.screen: self.output(''.join(row) + '\n')
        elif line.upper() == 'HELP':
            self.output('RUN LIST NEW LOAD SAVE TAPE SCREEN HELP; BASIC: PRINT LET IF FOR NEXT GOTO GOSUB RETURN INPUT DIM DATA READ RESTORE SET RESET CLS COLOR SOUND OPEN CLOSE END\n')
        else: self.execute(line)


def main():
    try:
        from microtrs_hw import Hardware
        hardware = Hardware()
    except (ImportError, OSError, ValueError) as exc:
        print('Hardware unavailable:', exc)
        hardware = None
    basic = Basic(hardware=hardware)
    basic.output('TRS-80 BASIC / ESP32 MicroPython\nType HELP for commands. Ctrl-C stops the session.\n')
    while True:
        try:
            basic.command(input('READY> '))
        except KeyboardInterrupt:
            basic.output('\nBREAK\n')
        except Exception as exc:
            basic.output('?ERROR ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
