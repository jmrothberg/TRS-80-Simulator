"""Expression Engine: the one evaluator PRINT, LET, IF and FOR all share."""

from __future__ import annotations

import unittest

import support
from support import evaluate, new_machine, run_program

from functional_model import memory_map as mm
from functional_model.errors import BasicError


class ArithmeticTest(unittest.TestCase):
    def check(self, expression: str, expected: int):
        self.assertEqual(evaluate(expression).require_integer(), expected, expression)

    def test_the_four_operations(self):
        self.check("2+3", 5)
        self.check("10-4", 6)
        self.check("6*7", 42)
        self.check("20/4", 5)

    def test_integer_division_truncates_toward_zero(self):
        self.check("7/2", 3)
        self.check("0-7/2", -3)
        self.check("7/(0-2)", -3)

    def test_precedence(self):
        self.check("2+3*4", 14)
        self.check("(2+3)*4", 20)
        self.check("2*3+4*5", 26)
        self.check("2^3^2", 512)  # right associative
        self.check("0-2^2", -4)  # unary minus is weaker than ^

    def test_unary_operators(self):
        self.check("-5", -5)
        self.check("--5", 5)
        self.check("-(2+3)", -5)
        self.check("+7", 7)

    def test_nested_parentheses(self):
        self.check("((1+2)*(3+4))-((5-2)*2)", 15)

    def test_comparisons_are_minus_one_and_zero(self):
        self.check("1<2", -1)
        self.check("2<2", 0)
        self.check("2<=2", -1)
        self.check("3>2", -1)
        self.check("3>=4", 0)
        self.check("1=1", -1)
        self.check("1<>1", 0)

    def test_logical_operators_are_bitwise(self):
        self.check("NOT 0", -1)
        self.check("NOT (1=1)", 0)
        self.check("(1=1) AND (2=2)", -1)
        self.check("(1=1) AND (2=3)", 0)
        self.check("(1=1) OR (2=3)", -1)
        self.check("12 AND 10", 8)
        self.check("12 OR 3", 15)

    def test_division_by_zero(self):
        with self.assertRaises(BasicError) as caught:
            evaluate("1/0")
        self.assertEqual(caught.exception.code, "/0")

    def test_sixteen_bit_range_is_enforced(self):
        self.check("32767", 32767)
        with self.assertRaises(BasicError) as caught:
            evaluate("32767+1")
        self.assertEqual(caught.exception.code, "OV")


class FunctionTest(unittest.TestCase):
    def check(self, expression: str, expected: int):
        self.assertEqual(evaluate(expression).require_integer(), expected, expression)

    def test_numeric_functions(self):
        self.check("ABS(-7)", 7)
        self.check("ABS(7)", 7)
        self.check("SGN(-3)", -1)
        self.check("SGN(0)", 0)
        self.check("SGN(3)", 1)
        self.check("INT(5)", 5)

    def test_peek_reads_the_address_space(self):
        machine = new_machine()
        machine.memory.write(mm.VRAM_BASE, ord("Q"))
        self.assertEqual(
            evaluate(f"PEEK({mm.VRAM_BASE})", machine).require_integer(), ord("Q")
        )

    def test_point_is_a_two_argument_function(self):
        machine = new_machine()
        machine.graphics.set(4, 4)
        self.assertEqual(evaluate("POINT(4,4)", machine).require_integer(), -1)
        self.assertEqual(evaluate("POINT(5,5)", machine).require_integer(), 0)

    def test_functions_nest_and_compose(self):
        self.check("ABS(0-(2+3))*SGN(9)", 5)
        self.check("ABS(SGN(0-4))", 1)

    def test_rnd_stays_in_range(self):
        machine = new_machine()
        for _ in range(50):
            value = evaluate("RND(6)", machine).require_integer()
            self.assertTrue(1 <= value <= 6, value)

    def test_rnd_zero_needs_floating_point(self):
        with self.assertRaises(BasicError) as caught:
            evaluate("RND(0)")
        self.assertEqual(caught.exception.code, "FC")

    def test_wrong_argument_count_is_a_syntax_error(self):
        with self.assertRaises(BasicError) as caught:
            evaluate("POINT(1)")
        self.assertEqual(caught.exception.code, "SN")


class StackTest(unittest.TestCase):
    """The operand and operator stacks really are in the Stack Area."""

    def test_stacks_are_left_balanced(self):
        machine = new_machine()
        evaluate("((1+2)*3)-4", machine)
        self.assertEqual(machine.expression.operands.pointer, 0)
        self.assertEqual(machine.expression.operators.pointer, 0)

    def test_operands_are_written_to_the_documented_addresses(self):
        machine = new_machine()
        tokenized = machine.tokenizer.tokenize("1+2")
        machine._load_direct_statement(tokenized.token_bytes)
        machine.expression.evaluate()
        # The first operand slot holds the last integer pushed there.
        self.assertEqual(
            machine.memory.read(mm.EXPR_OPERAND_STACK_BASE), ord("I")
        )

    def test_deep_nesting_is_bounded_by_the_stack_depth(self):
        depth = mm.EXPR_OPERATOR_DEPTH + 4
        with self.assertRaises(Exception):
            evaluate("(" * depth + "1" + ")" * depth)


class SharedEngineTest(unittest.TestCase):
    """PRINT, LET, IF and FOR must all reach the same evaluator."""

    def test_every_statement_uses_the_expression_engine(self):
        output = run_program(
            """
            10 A=2*3
            20 PRINT A+1
            30 IF A*2=12 THEN PRINT 99
            40 FOR I=A TO A+1: PRINT I: NEXT
            """
        )
        self.assertEqual(output.split(), ["7", "99", "6", "7"])


if __name__ == "__main__":
    unittest.main()
