"""Portable smoke checks; uses only the Python standard library."""
from main import Basic
import tempfile
import board_config


def run(lines, answers=()):
    output = []
    inputs = iter(answers)
    machine = Basic(output.append, lambda _: next(inputs))
    for line in lines:
        machine.command(line)
    return machine, ''.join(output)


m, out = run(['10 FOR I=1 TO 3', '20 PRINT I;', '30 NEXT I',
              '40 IF I=4 THEN PRINT " OK" ELSE PRINT "BAD"', 'RUN'])
assert out == ' 1  2  3  OK\n', repr(out)
m, out = run(['10 DIM A(3)', '20 A(2)=7', '30 PRINT A(2)',
              '40 DATA 12,"YES"', '50 READ N,S$', '60 PRINT N;S$', 'RUN'])
assert out == ' 7 \n 12 YES\n', repr(out)
m, out = run(['10 SET(2,3)', '20 IF POINT(2,3) THEN GOSUB 50',
              '30 END', '50 PRINT "PIXEL"', '60 RETURN', 'RUN'])
assert out == 'PIXEL\n', repr(out)
m, out = run(['10 PRINT@ 0,"A"', 'RUN'])
assert m.screen[0][0] == 'A'
m, out = run(['10 ON 2 GOSUB 100,200', '20 PRINT "DONE"', '30 END',
              '100 PRINT "WRONG"', '110 RETURN', '200 PRINT "RIGHT"',
              '210 RETURN', 'RUN'])
assert out == 'RIGHT\nDONE\n', repr(out)
m, out = run(['10 COLOR 4,0', '20 SET(1,1,12)',
              '30 PRINT COLORAT(1,1)', 'RUN'])
assert out == ' 12 \n', repr(out)
with tempfile.TemporaryDirectory() as directory:
    board_config.SD_MOUNT = directory
    m, out = run(['10 INPUT#-1,V$', '20 PRINT V$',
                  '30 COLOR 2,0', '40 SOUND 440,10', '50 END'])
    captured = []
    m.output = captured.append
    m.command('SAVE "HELLO.BAS"')
    assert 'SAVED 5 LINES' in ''.join(captured)
    m.command('NEW')
    m.command('LOAD "HELLO.BAS"')
    assert len(m.program) == 5
    with open(directory + '/GAME.DAT', 'w') as tape:
        tape.write('ADVENTURE\n')
    m.command('TAPE "GAME.DAT"')
    m.command('RUN')
    assert 'ADVENTURE\n' in ''.join(captured)
    m.command('OPEN "O",#1,"OUT.DAT"')
    m.command('PRINT#1,"WRITTEN"')
    m.command('CLOSE')
    with open(directory + '/OUT.DAT') as saved:
        assert saved.read() == 'WRITTEN\n'
    m.command('TAPEOUT "TAPED.DAT"')
    m.command('PRINT#-1,"A"')
    m.command('TAPECLOSE')
    with open(directory + '/TAPED.DAT') as saved:
        assert saved.read() == 'A\n'
    assert m.eval('"A"="A"') == -1
    assert m.eval('"A"<>"B"') == -1
m, out = run(['10 PRINT"HI"', '20 DIM A(2,2)', '30 A(2,1)=4',
              '40 DEF FNX(N)=N*3', '50 PRINT A(2,1);FNX(2)',
              '60 PRINT"AB";TAB(4);"Z"', '70 TOTAL=9', '80 PRINT TO', 'RUN'])
assert out == 'HI\n 4  6 \nAB  Z\n 9 \n', repr(out)
assert m.screen[2][4] == 'Z'
print('ESP32 BASIC smoke checks passed')
