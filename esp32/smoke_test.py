"""Portable smoke checks; uses only the Python standard library."""
from main import Basic


def run(lines, answers=()):
    output = []
    inputs = iter(answers)
    machine = Basic(output.append, lambda _: next(inputs))
    for line in lines:
        machine.command(line)
    return machine, ''.join(output)


m, out = run(['10 FOR I=1 TO 3', '20 PRINT I;', '30 NEXT I',
              '40 IF I=4 THEN PRINT " OK" ELSE PRINT "BAD"', 'RUN'])
assert out == '123 OK\n', repr(out)
m, out = run(['10 DIM A(3)', '20 A(2)=7', '30 PRINT A(2)',
              '40 DATA 12,"YES"', '50 READ N,S$', '60 PRINT N;S$', 'RUN'])
assert out == '7\n12YES\n', repr(out)
m, out = run(['10 SET(2,3)', '20 IF POINT(2,3) THEN GOSUB 50',
              '30 END', '50 PRINT "PIXEL"', '60 RETURN', 'RUN'])
assert out == 'PIXEL\n', repr(out)
m, out = run(['10 PRINT@ 0,"A"', 'RUN'])
assert m.screen[0][0] == 'A'
print('ESP32 BASIC smoke checks passed')
