"""Domain (supermarket) and error-handling tests for native ShengSiong."""

import os
import subprocess
import tempfile

import pytest

from test_language import compile_and_run, run_ok, lines, SHENGC, ROOT


def run_expect_runtime_error(source):
    """Compile OK, but the produced binary should exit non-zero (ss_die)."""
    rc, out, err = compile_and_run(source)
    assert rc != 0, f"expected runtime failure, got success. out={out}"
    return err


def compile_expect_fail(source):
    """The compiler itself should reject the program (bad parse/type)."""
    rc, out, err = compile_and_run(source, args=("--emit-c",))
    assert rc != 0, f"expected compile failure, got success. out={out[:200]}"
    return err


# -- entity + flow ---------------------------------------------------------
def test_declare_and_report():
    src = (
        "store tampines\nwarehouse central\nproduct milk { price: 3.0 }\n"
        "stock 5 units of milk at tampines\nreport tampines\n"
    )
    out = lines(src)
    assert "[store] tampines" in out
    assert "  milk: 5" in out
    assert "revenue: 0.00" in out


def test_full_supply_chain():
    src = (
        "store tampines\nwarehouse central\nsupplier acme\n"
        "product milk { price: 2.0 }\n"
        "order 100 units of milk from acme to central\n"
        "deliver 40 units of milk from central to tampines\n"
        "stock 10 units of milk at tampines\n"
        "sell 20 units of milk at tampines\n"
        "print inventory(milk, tampines)\n"
        "print inventory(milk, central)\n"
        "print revenue()\n"
    )
    assert lines(src) == ["30", "60", "40"]


def test_price_statement_and_attribute():
    src = "product milk { price: 1.0 }\nprice milk at 5.5\nprint milk.price"
    assert lines(src) == ["5.5"]


def test_deliver_via_truck_counts():
    src = (
        "warehouse central\nstore tampines\nsupplier acme\nproduct milk\n"
        "truck lorry { capacity: 100 }\n"
        "order 50 units of milk from acme to central\n"
        "deliver 30 units of milk from central to tampines via lorry\n"
        "print lorry.deliveries\n"
    )
    assert lines(src) == ["1"]


def test_auto_restock_triggers():
    src = (
        "store tampines\nsupplier acme\nproduct milk { price: 1.0 }\n"
        "stock 30 units of milk at tampines\n"
        "restock milk at tampines when below 20 order 100 units from acme\n"
        "sell 15 units of milk at tampines\n"
        "print inventory(milk, tampines)\n"
    )
    # 30 - 15 = 15 < 20 -> +100 => 115
    assert lines(src) == ["115"]


def test_auto_restock_on_add_when_below():
    src = (
        "store tampines\nsupplier acme\nproduct milk\n"
        "stock 5 units of milk at tampines\n"
        "restock milk at tampines when below 20 order 50 units from acme\n"
        "print inventory(milk, tampines)\n"
    )
    assert lines(src) == ["55"]


def test_all_entity_attributes():
    src = (
        "store s\nsupplier acme { lead_time: 4, reliability: 0.8 }\n"
        "product milk { price: 3.0, category: \"dairy\" }\n"
        "truck lorry { capacity: 250 }\n"
        "print milk.price\nprint milk.category\nprint milk.name\n"
        "print acme.lead_time\nprint acme.reliability\n"
        "print lorry.capacity\nprint lorry.deliveries\nprint s.name\n"
    )
    assert lines(src) == ["3", "dairy", "milk", "4", "0.8", "250", "0", "s"]


def test_report_all_default():
    src = (
        "store a\nstore b\nproduct milk\n"
        "stock 1 units of milk at a\nreport\n"
    )
    out = lines(src)
    assert "[store] a" in out and "[store] b" in out


# -- runtime errors (native binary aborts via ss_die) ----------------------
def test_sell_insufficient_is_runtime_error():
    err = run_expect_runtime_error(
        "store s\nproduct milk\nsell 5 units of milk at s\n"
    )
    assert "insufficient stock" in err


def test_deliver_over_capacity_runtime_error():
    src = (
        "warehouse w\nstore s\nsupplier acme\nproduct milk\n"
        "truck t { capacity: 10 }\n"
        "order 100 units of milk from acme to w\n"
        "deliver 50 units of milk from w to s via t\n"
    )
    err = run_expect_runtime_error(src)
    assert "capacity" in err


def test_unknown_product_compile_error():
    # 'ghost' was never declared, so it is an undefined identifier -> compile error.
    err = compile_expect_fail("store s\nstock 1 units of ghost at s\n")
    assert "undefined variable" in err


def test_report_unknown_target_compile_error():
    err = compile_expect_fail("store s\nreport nowhere\n")
    assert "undefined variable" in err


def test_dynamic_unknown_product_runtime_error():
    # A product name computed at runtime bypasses compile-time checks and hits
    # the engine's find_prod guard.
    err = run_expect_runtime_error(
        'store s\nproduct milk\nstock 1 units of ("gho" + "st") at s\n'
    )
    assert "unknown product" in err


def test_dynamic_unknown_target_runtime_error():
    err = run_expect_runtime_error('store s\nreport ("no" + "where")\n')
    assert "unknown target" in err


def test_division_by_zero_runtime_error():
    err = run_expect_runtime_error("print 1 / 0\n")
    assert "division by zero" in err


# -- compile-time errors ---------------------------------------------------
def test_parse_error_rejected():
    err = compile_expect_fail("let x =\n")
    assert "parse error" in err


def test_unknown_property_rejected():
    err = compile_expect_fail("product milk { price: 1.0 }\nprint milk.color\n")
    assert "cannot read property" in err


def test_bad_character_rejected():
    err = compile_expect_fail("print @\n")
    assert "unexpected character" in err


def test_invalid_assignment_target_rejected():
    err = compile_expect_fail("1 = 2\n")
    assert "invalid assignment" in err


# -- toolchain behaviours --------------------------------------------------
def test_emit_c_outputs_c_source():
    rc, out, err = compile_and_run('print 1', args=("--emit-c",))
    assert rc == 0
    assert "int main(void)" in out
    assert "v_print" in out


def test_produced_file_is_native_binary():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "p.sheng")
        out = os.path.join(d, "p")
        with open(src, "w") as f:
            f.write('print "native"\n')
        rc = subprocess.run([SHENGC, src, "-o", out], capture_output=True, text=True).returncode
        assert rc == 0
        info = subprocess.run(["file", out], capture_output=True, text=True).stdout
        assert "ELF" in info and "executable" in info
        # and it runs on its own with no interpreter/VM
        r = subprocess.run([out], capture_output=True, text=True)
        assert r.stdout.strip() == "native"


def test_missing_input_usage():
    rc = subprocess.run([SHENGC], capture_output=True, text=True).returncode
    assert rc == 2


def test_unknown_option_rejected():
    rc = subprocess.run([SHENGC, "--bogus"], capture_output=True, text=True).returncode
    assert rc != 0


def test_example_program_compiles_and_runs():
    example = os.path.join(ROOT, "examples", "supermarket.sheng")
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "market")
        rc = subprocess.run([SHENGC, example, "-o", out], capture_output=True, text=True).returncode
        assert rc == 0
        r = subprocess.run([out], capture_output=True, text=True)
        assert r.returncode == 0
        assert "revenue:" in r.stdout
