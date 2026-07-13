import pytest

from shengsiong import run
from shengsiong.interpreter import Interpreter, RuntimeErrorSS, Environment
from shengsiong.lexer import Lexer
from shengsiong.parser import Parser


def out(src):
    return run(src).output


def test_print_number_and_string():
    assert out('print 42\nprint "hi"') == ["42", "hi"]


def test_print_float_integer_valued():
    assert out("print 4.0") == ["4"]


def test_print_float_fractional():
    assert out("print 4.5") == ["4.5"]


def test_print_booleans_and_nil():
    assert out("print true\nprint false") == ["true", "false"]


def test_let_and_variable_reference():
    assert out("let x = 5\nprint x") == ["5"]


def test_assignment_returns_value():
    assert out("let x = 1\nprint (x = 9)\nprint x") == ["9", "9"]


def test_undefined_variable_raises():
    with pytest.raises(RuntimeErrorSS):
        run("print y")


def test_assign_to_undefined_raises():
    with pytest.raises(RuntimeErrorSS):
        run("y = 3")


def test_arithmetic():
    assert out("print 2 + 3 * 4 - 1") == ["13"]


def test_integer_division_stays_int_when_even():
    assert out("print 10 / 2") == ["5"]


def test_division_becomes_float_when_needed():
    assert out("print 7 / 2") == ["3.5"]


def test_modulo():
    assert out("print 10 % 3") == ["1"]


def test_division_by_zero_raises():
    with pytest.raises(RuntimeErrorSS):
        run("print 1 / 0")


def test_modulo_by_zero_raises():
    with pytest.raises(RuntimeErrorSS):
        run("print 1 % 0")


def test_string_concatenation_mixed():
    assert out('print "n=" + 5') == ["n=5"]
    assert out('print 5 + "!"') == ["5!"]


def test_arithmetic_type_error_raises():
    with pytest.raises(RuntimeErrorSS):
        run('print 1 - "a"')


def test_comparison_operators():
    assert out("print 1 < 2\nprint 2 <= 2\nprint 3 > 4\nprint 3 >= 3") == [
        "true", "true", "false", "true",
    ]


def test_comparison_type_error():
    with pytest.raises(RuntimeErrorSS):
        run('print 1 < "a"')


def test_equality_and_inequality():
    assert out("print 1 == 1\nprint 1 != 2\nprint true == true") == [
        "true", "true", "true",
    ]


def test_equality_bool_vs_number_is_false():
    assert out("print true == 1") == ["false"]


def test_unary_negation_and_not():
    assert out("print -5\nprint not false\nprint not 0") == ["-5", "true", "true"]


def test_unary_minus_type_error():
    with pytest.raises(RuntimeErrorSS):
        run('print -"x"')


def test_logical_short_circuit_or():
    assert out("print true or (1/0 == 0)") == ["true"]


def test_logical_short_circuit_and():
    assert out("print false and (1/0 == 0)") == ["false"]


def test_logical_and_returns_operand():
    assert out("print 3 and 4") == ["4"]
    assert out("print 0 and 4") == ["0"]


def test_truthiness_rules():
    prog = 'print not ""\nprint not "x"\nprint not []\nprint not [1]\nprint not nil_test()'
    src = "func nil_test() { return }\n" + prog
    assert out(src) == ["true", "false", "true", "false", "true"]


def test_if_else_branches():
    assert out("if (1 > 2) { print 1 } else { print 2 }") == ["2"]
    assert out("if (2 > 1) { print 1 }") == ["1"]


def test_while_loop_counts():
    src = "let i = 0\nwhile (i < 3) { print i\ni = i + 1 }"
    assert out(src) == ["0", "1", "2"]


def test_while_infinite_guard(monkeypatch):
    # Lower the real guard limit, then run a non-terminating loop; the real
    # guard line must raise rather than hang.
    import shengsiong.interpreter as I
    monkeypatch.setattr(I.Interpreter, "MAX_LOOP_ITERATIONS", 10)
    with pytest.raises(RuntimeErrorSS):
        run("let i = 0\nwhile (true) { i = i + 1 }")


def test_truthy_on_function_value():
    # `not <function>` exercises the fall-through truthiness branch.
    assert out("func f() { return 1 }\nprint not f") == ["false"]


def test_functions_and_return():
    src = "func add(a, b) { return a + b }\nprint add(2, 3)"
    assert out(src) == ["5"]


def test_function_without_return_yields_nil():
    src = "func noop() { let x = 1 }\nprint noop()"
    assert out(src) == ["nil"]


def test_function_closure_captures_env():
    src = (
        "let base = 10\n"
        "func addbase(x) { return x + base }\n"
        "print addbase(5)"
    )
    assert out(src) == ["15"]


def test_function_wrong_arity_raises():
    with pytest.raises(RuntimeErrorSS):
        run("func f(a) { return a }\nf(1, 2)")


def test_calling_non_function_raises():
    with pytest.raises(RuntimeErrorSS):
        run("let x = 5\nx()")


def test_recursion_factorial():
    src = (
        "func fact(n) { if (n <= 1) { return 1 } return n * fact(n - 1) }\n"
        "print fact(5)"
    )
    assert out(src) == ["120"]


def test_builtin_len_str_num():
    assert out('print len("hello")') == ["5"]
    assert out("print len([1, 2, 3])") == ["3"]
    assert out("print str(42)") == ["42"]
    assert out('print num("3.5")') == ["3.5"]
    assert out('print num("4")') == ["4"]


def test_builtin_min_max_abs():
    assert out("print min(3, 1, 2)") == ["1"]
    assert out("print max(3, 1, 2)") == ["3"]
    assert out("print abs(-7)") == ["7"]


def test_builtin_len_type_error():
    with pytest.raises(RuntimeErrorSS):
        run("print len(5)")


def test_builtin_num_bad_value():
    with pytest.raises(RuntimeErrorSS):
        run('print num("abc")')


def test_builtin_wrong_arity():
    with pytest.raises(RuntimeErrorSS):
        run("print abs(1, 2)")


def test_list_literal_and_index():
    assert out("let x = [10, 20, 30]\nprint x[1]") == ["20"]


def test_string_index():
    assert out('let s = "abc"\nprint s[2]') == ["c"]


def test_list_index_out_of_range():
    with pytest.raises(RuntimeErrorSS):
        run("let x = [1]\nprint x[5]")


def test_string_index_out_of_range():
    with pytest.raises(RuntimeErrorSS):
        run('print "a"[9]')


def test_index_non_integer():
    with pytest.raises(RuntimeErrorSS):
        run("let x = [1]\nprint x[true]")


def test_string_index_non_integer():
    with pytest.raises(RuntimeErrorSS):
        run('print "abc"[true]')


def test_index_unindexable():
    with pytest.raises(RuntimeErrorSS):
        run("print 5[0]")


def test_print_list_stringify():
    assert out("print [1, 2, 3]") == ["[1, 2, 3]"]


def test_print_function_values():
    src = "func f() { return 1 }\nprint f\nprint len"
    result = out(src)
    assert result[0].startswith("<func f")
    assert result[1].startswith("<native len")


def test_environment_get_undefined_direct():
    env = Environment()
    with pytest.raises(RuntimeErrorSS):
        env.get("missing")


def test_environment_assign_undefined_direct():
    env = Environment()
    with pytest.raises(RuntimeErrorSS):
        env.assign("missing", 1)
