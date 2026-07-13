"""End-to-end test suite for the *native* ShengSiong compiler (shengc).

Python here is only the test harness: every test invokes the real `shengc`
binary, compiles a `.sheng` program to a native executable via the system C
compiler, runs that executable, and asserts on its output / exit status.
Nothing in the language runtime is Python.
"""

import os
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHENGC = os.path.join(ROOT, "shengc")


def compile_and_run(source, args=("--run",), expect_compile_ok=True):
    """Compile `source` with shengc and (by default) run it.

    Returns (returncode, stdout, stderr) of the final step.
    """
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "prog.sheng")
        out = os.path.join(d, "prog")
        with open(src, "w") as f:
            f.write(source)
        cmd = [SHENGC, src, "-o", out, *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=d)
        return proc.returncode, proc.stdout, proc.stderr


def run_ok(source):
    rc, out, err = compile_and_run(source)
    assert rc == 0, f"expected success, got rc={rc}, stderr={err}"
    return out


def lines(source):
    return run_ok(source).strip().splitlines()


# --------------------------------------------------------------------------
def test_compiler_binary_exists():
    assert os.path.exists(SHENGC), "shengc must be built (run make)"


def test_hello_print():
    assert lines('print "hello"') == ["hello"]


def test_print_int_and_float():
    assert lines("print 42\nprint 4.5\nprint 4.0") == ["42", "4.5", "4"]


def test_arithmetic_precedence():
    assert lines("print 2 + 3 * 4 - 1") == ["13"]


def test_integer_division_exact():
    assert lines("print 10 / 2") == ["5"]


def test_float_division():
    assert lines("print 7 / 2") == ["3.5"]


def test_modulo():
    assert lines("print 10 % 3") == ["1"]


def test_string_concatenation():
    assert lines('print "n=" + 5\nprint 5 + "!"') == ["n=5", "5!"]


def test_comparisons():
    src = "print 1 < 2\nprint 2 <= 2\nprint 3 > 4\nprint 3 >= 3\nprint 1 == 1\nprint 1 != 2"
    assert lines(src) == ["true", "true", "false", "true", "true", "true"]


def test_booleans_and_logic():
    assert lines("print true and false\nprint true or false\nprint not false") == [
        "false", "true", "true",
    ]


def test_unary_minus():
    assert lines("print -7\nprint - -7") == ["-7", "7"]


def test_if_else():
    assert lines("if (1 > 2) { print 1 } else { print 2 }") == ["2"]


def test_while_loop():
    assert lines("let i = 0\nwhile (i < 3) { print i\ni = i + 1 }") == ["0", "1", "2"]


def test_function_and_return():
    assert lines("func add(a, b) { return a + b }\nprint add(2, 3)") == ["5"]


def test_function_no_return_is_nil():
    assert lines("func f() { let x = 1 }\nprint f()") == ["nil"]


def test_recursion_factorial():
    src = "func fact(n) { if (n <= 1) { return 1 } return n * fact(n-1) }\nprint fact(6)"
    assert lines(src) == ["720"]


def test_recursion_fibonacci():
    src = (
        "func fib(n) { if (n < 2) { return n } return fib(n-1) + fib(n-2) }\n"
        "print fib(10)"
    )
    assert lines(src) == ["55"]


def test_builtins():
    src = (
        'print len("abcde")\nprint str(99)\nprint num("2.5")\n'
        "print min(4, 2, 8)\nprint max(4, 2, 8)\nprint abs(-3)"
    )
    assert lines(src) == ["5", "99", "2.5", "2", "8", "3"]


def test_global_variable_visible_in_function():
    src = "let base = 100\nfunc f(x) { return x + base }\nprint f(5)"
    assert lines(src) == ["105"]
