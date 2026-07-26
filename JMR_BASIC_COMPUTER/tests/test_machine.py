"""The whole computer: boot, console, direct mode, statements, errors."""

from __future__ import annotations

import unittest

import support
from support import enter, new_machine, output_of, run_program

from functional_model import memory_map as mm
from functional_model.engines.storage_engine import MemoryBackend
from functional_model.machine import Machine
from functional_model.sequencer import Status


class BootTest(unittest.TestCase):
    def test_the_user_experience_from_the_constitution(self):
        machine = new_machine()
        machine.type_line('10 PRINT "HELLO"')
        machine.type_line("RUN")
        self.assertEqual(
            machine.screen_text(),
            'JMR LEVEL II BASIC\n'
            'READY\n'
            '>10 PRINT "HELLO"\n'
            '>RUN\n'
            'HELLO\n'
            'READY\n'
            '>',
        )

    def test_the_banner_is_the_first_thing_on_the_screen(self):
        machine = new_machine()
        self.assertEqual(machine.screen_lines()[0].strip(), "JMR LEVEL II BASIC")
        self.assertEqual(machine.screen_lines()[1].strip(), "READY")

    def test_boot_leaves_no_program_and_no_variables(self):
        machine = new_machine()
        self.assertTrue(machine.program.is_empty)
        self.assertEqual(machine.variables.items(), [])


class ConsoleTest(unittest.TestCase):
    def test_typing_goes_through_the_uart_and_the_keyboard_fifo(self):
        machine = new_machine()
        machine.receive("PRINT 1")
        self.assertTrue(machine.uart.rx)
        machine.tick()
        self.assertFalse(machine.uart.rx)
        self.assertEqual(machine.console.buffer, "PRINT 1")
        machine.receive("\r")
        machine.run_until_idle()
        self.assertIn("1", machine.screen_text())

    def test_backspace_edits_the_line(self):
        machine = new_machine()
        machine.type_line("PRINT 12\x083")
        self.assertIn(" 13", machine.screen_text())

    def test_the_line_buffer_is_in_work_ram(self):
        machine = new_machine()
        machine.type_line("PRINT 1")
        stored = machine.memory.read_block(mm.INPUT_LINE_BUFFER, 7).decode()
        self.assertEqual(stored, "PRINT 1")

    def test_a_numbered_line_is_filed_not_run(self):
        machine = new_machine()
        machine.type_line('10 PRINT "NOPE"')
        self.assertNotIn("\nNOPE", machine.screen_text())
        self.assertEqual(machine.program_text(), ['10 PRINT"NOPE"'])

    def test_an_empty_line_just_prompts(self):
        machine = new_machine()
        machine.type_line("")
        self.assertTrue(machine.screen_text().endswith(">"))


class DirectModeTest(unittest.TestCase):
    def test_expressions_print_immediately(self):
        machine = new_machine()
        machine.type_line("PRINT 6*7")
        self.assertIn(" 42", machine.screen_text())

    def test_variables_survive_between_direct_statements(self):
        machine = new_machine()
        machine.type_line("A=5")
        machine.type_line("PRINT A*2")
        self.assertIn(" 10", machine.screen_text())

    def test_several_statements_on_one_line(self):
        machine = new_machine()
        machine.type_line("A=1:B=2:PRINT A+B")
        self.assertIn(" 3", machine.screen_text())

    def test_new_erases_the_program(self):
        machine = enter(new_machine(), "10 PRINT 1")
        machine.type_line("NEW")
        self.assertEqual(machine.program_text(), [])


class StatementTest(unittest.TestCase):
    def test_print_separators(self):
        self.assertEqual(run_program('10 PRINT "A";"B";"C"'), "ABC")
        self.assertEqual(run_program("10 PRINT 1;2;3"), " 1  2  3")
        zones = run_program('10 PRINT "A","B"')
        self.assertEqual(zones, "A" + " " * 15 + "B")

    def test_print_at_positions_output(self):
        output = run_program('10 PRINT@ 64, "SECOND ROW"')
        self.assertEqual(output.splitlines()[1], "SECOND ROW")

    def test_trailing_separator_suppresses_the_newline(self):
        self.assertEqual(run_program('10 PRINT "A";\n20 PRINT "B"'), "AB")

    def test_goto_and_gosub(self):
        output = run_program(
            """
            10 GOSUB 100
            20 GOTO 200
            100 PRINT "SUB"
            110 RETURN
            200 PRINT "END"
            """
        )
        self.assertEqual(output.split(), ["SUB", "END"])

    def test_if_then_line_number_is_a_goto(self):
        self.assertEqual(run_program("10 IF 1=1 THEN 30\n20 PRINT 2\n30 PRINT 3"), " 3")

    def test_if_false_abandons_the_rest_of_the_line(self):
        self.assertEqual(run_program('10 IF 0 THEN PRINT "NO":PRINT "ALSO NO"\n20 PRINT "YES"'), "YES")

    def test_for_next_counts(self):
        self.assertEqual(run_program("10 FOR I=1 TO 3\n20 PRINT I;\n30 NEXT"), " 1  2  3")

    def test_for_with_a_negative_step(self):
        self.assertEqual(run_program("10 FOR I=3 TO 1 STEP -1\n20 PRINT I;\n30 NEXT"), " 3  2  1")

    def test_a_loop_that_never_runs(self):
        self.assertEqual(run_program('10 FOR I=1 TO 0\n20 PRINT "NO"\n30 NEXT\n40 PRINT "DONE"'), "DONE")

    def test_one_next_can_close_several_loops(self):
        output = run_program(
            """
            10 FOR I=1 TO 2
            20 FOR J=1 TO 2
            30 PRINT I*10+J;
            40 NEXT J,I
            """
        )
        self.assertEqual(output.split(), ["11", "12", "21", "22"])

    def test_a_skipped_loop_steps_over_a_whole_next_list(self):
        output = run_program(
            """
            10 FOR I=1 TO 0
            20 FOR J=1 TO 2
            30 PRINT "X";
            40 NEXT J,I
            50 PRINT "DONE"
            """
        )
        self.assertEqual(output, "DONE")

    def test_nested_loops(self):
        output = run_program(
            """
            10 FOR I=1 TO 2
            20 FOR J=1 TO 2
            30 PRINT I*10+J;
            40 NEXT J
            50 NEXT I
            """
        )
        self.assertEqual(output.split(), ["11", "12", "21", "22"])

    def test_read_data_restore(self):
        output = run_program(
            """
            10 READ A,B
            20 PRINT A+B
            30 RESTORE
            40 READ C
            50 PRINT C
            60 DATA 10,32
            """
        )
        self.assertEqual(output.split(), ["42", "10"])

    def test_data_spread_over_several_lines(self):
        output = run_program(
            """
            10 FOR I=1 TO 4
            20 READ V:PRINT V;
            30 NEXT
            40 DATA 1,2
            50 DATA 3,4
            """
        )
        self.assertEqual(output.split(), ["1", "2", "3", "4"])

    def test_running_out_of_data(self):
        machine = enter(new_machine(), "10 READ A\n20 READ B\n30 DATA 1")
        machine.type_line("RUN")
        self.assertIn("?OD ERROR IN 20", machine.screen_text())

    def test_cls_clears_the_screen(self):
        machine = enter(new_machine(), '10 PRINT "GONE"\n20 CLS\n30 PRINT "HERE"')
        machine.type_line("RUN")
        self.assertNotIn("GONE", machine.screen_text())
        self.assertIn("HERE", machine.screen_text())

    def test_set_reset_point(self):
        output = run_program(
            """
            10 SET(3,4)
            20 PRINT@ 448, POINT(3,4);
            30 RESET(3,4)
            40 PRINT POINT(3,4)
            """
        )
        self.assertEqual(output.splitlines()[-1].split(), ["-1", "0"])

    def test_poke_writes_to_video_memory(self):
        # Row 5, well clear of the READY message the prompt writes at the top.
        address = mm.vram_address(5, 0)
        machine = enter(new_machine(), f"10 CLS:POKE {address},65")
        machine.type_line("RUN")
        self.assertEqual(machine.memory.read(address), 65)

    def test_peek_reads_back_what_poke_wrote(self):
        output = run_program(f"10 POKE {mm.WORK_RAM_BASE + 0x40},77\n20 PRINT PEEK({mm.WORK_RAM_BASE + 0x40})")
        self.assertEqual(output.strip(), "77")

    def test_end_stops_the_program(self):
        self.assertEqual(run_program('10 PRINT "A"\n20 END\n30 PRINT "B"'), "A")

    def test_rem_is_ignored(self):
        self.assertEqual(run_program('10 REM nothing to see\n20 PRINT "OK"'), "OK")

    def test_implied_let(self):
        self.assertEqual(run_program("10 A=7:LET B=6:PRINT A*B"), " 42")


class InputTest(unittest.TestCase):
    def test_input_stalls_the_processor_until_a_line_arrives(self):
        machine = enter(new_machine(), '10 INPUT "AGE";A\n20 PRINT A*2')
        machine.type_line("RUN")
        self.assertIs(machine.pcu.status, Status.WAITING_INPUT)
        machine.type_line("21")
        self.assertIs(machine.pcu.status, Status.HALTED)
        self.assertIn(" 42", machine.screen_text())

    def test_input_prompts_with_a_question_mark(self):
        machine = enter(new_machine(), "10 INPUT A")
        machine.type_line("RUN")
        self.assertTrue(machine.screen_text().endswith("?"))
        machine.type_line("1")

    def test_several_variables_from_one_line(self):
        machine = enter(new_machine(), "10 INPUT A,B\n20 PRINT A+B")
        machine.type_line("RUN")
        machine.type_line("20,22")
        self.assertIn(" 42", machine.screen_text())

    def test_a_non_numeric_answer_asks_again(self):
        machine = enter(new_machine(), "10 INPUT A\n20 PRINT A")
        machine.type_line("RUN")
        machine.type_line("banana")
        self.assertIn("?REDO", machine.screen_text())
        self.assertIs(machine.pcu.status, Status.WAITING_INPUT)
        machine.type_line("5")
        self.assertIn(" 5", machine.screen_text())


class ListTest(unittest.TestCase):
    def test_list_shows_the_program(self):
        machine = enter(new_machine(), '10 PRINT "A"\n20 PRINT "B"')
        machine.type_line("CLS:LIST")
        self.assertEqual(output_of(machine).splitlines()[:2], ['10 PRINT"A"', '20 PRINT"B"'])

    def test_list_one_line(self):
        machine = enter(new_machine(), "10 PRINT 1\n20 PRINT 2\n30 PRINT 3")
        machine.type_line("CLS:LIST 20")
        self.assertEqual(output_of(machine).splitlines(), ["20 PRINT 2"])

    def test_list_a_range(self):
        machine = enter(new_machine(), "10 PRINT 1\n20 PRINT 2\n30 PRINT 3")
        machine.type_line("CLS:LIST 20-30")
        self.assertEqual(output_of(machine).splitlines(), ["20 PRINT 2", "30 PRINT 3"])

    def test_a_listing_can_be_typed_back_in(self):
        source = '10 FOR I=1 TO 3\n20 PRINT I;\n30 NEXT I'
        first = enter(new_machine(), source)
        second = enter(new_machine(), "\n".join(first.program_text()))
        self.assertEqual(first.program_text(), second.program_text())


class StorageTest(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        backend = MemoryBackend()
        writer = Machine(backend)
        writer.boot()
        enter(writer, '10 PRINT "SAVED"\n20 PRINT 42')
        writer.type_line('SAVE "PROG"')

        reader = Machine(backend)
        reader.boot()
        reader.type_line('LOAD "PROG"')
        self.assertEqual(reader.program_text(), ['10 PRINT"SAVED"', "20 PRINT 42"])
        reader.type_line("CLS:RUN")
        self.assertEqual(output_of(reader).split(), ["SAVED", "42"])

    def test_loading_source_text_goes_through_the_tokenizer(self):
        backend = MemoryBackend()
        backend.write("TEXT", b'10 PRINT "FROM TEXT"\n20 END\n')
        machine = Machine(backend)
        machine.boot()
        machine.type_line('LOAD "TEXT"')
        self.assertEqual(machine.program_text(), ['10 PRINT"FROM TEXT"', "20 END"])

    def test_a_missing_file_is_reported(self):
        machine = Machine(MemoryBackend())
        machine.boot()
        machine.type_line('LOAD "NOPE"')
        self.assertIn("?FF ERROR", machine.screen_text())


class ErrorTest(unittest.TestCase):
    def check(self, source: str, expected: str):
        machine = new_machine()
        for line in source.strip().splitlines():
            machine.type_line(line.strip())
        self.assertIn(expected, machine.screen_text())

    def test_undefined_line(self):
        self.check("GOTO 999", "?UL ERROR")

    def test_error_reports_the_line_it_happened_in(self):
        self.check("10 GOTO 999\nRUN", "?UL ERROR IN 10")

    def test_syntax_error(self):
        self.check("PRINT )", "?SN ERROR")

    def test_next_without_for(self):
        self.check("10 NEXT\nRUN", "?NF ERROR IN 10")

    def test_return_without_gosub(self):
        self.check("10 RETURN\nRUN", "?RG ERROR IN 10")

    def test_division_by_zero(self):
        self.check("10 PRINT 1/0\nRUN", "?/0 ERROR IN 10")

    def test_overflow(self):
        self.check("10 A=32767+1\nRUN", "?OV ERROR IN 10")

    def test_illegal_function_call(self):
        self.check("10 SET(200,10)\nRUN", "?FC ERROR IN 10")

    def test_the_machine_recovers_after_an_error(self):
        machine = new_machine()
        machine.type_line("GOTO 999")
        machine.type_line("PRINT 1+1")
        self.assertIn(" 2", machine.screen_text())

    def test_arrays_report_that_they_are_not_here_yet(self):
        self.check("10 DIM A(5)\nRUN", "?FC ERROR IN 10")


class BreakTest(unittest.TestCase):
    def test_a_running_program_can_be_interrupted(self):
        # A program that never ends is executed in slices, so the host stays in
        # control.  `type_line` is not used here: it would wait for the program
        # to finish, and this one never does.
        machine = enter(new_machine(), "10 GOTO 10")
        machine.statement_limit = 200
        machine.receive("RUN\r")
        machine.tick()  # console line -> RUN -> first slice
        self.assertIs(machine.pcu.status, Status.RUNNING)
        machine.tick()  # another slice, still going
        self.assertIs(machine.pcu.status, Status.RUNNING)
        machine.request_break()
        machine.tick()
        self.assertIs(machine.pcu.status, Status.HALTED)
        self.assertIn("BREAK IN 10", machine.screen_text())


if __name__ == "__main__":
    unittest.main()
