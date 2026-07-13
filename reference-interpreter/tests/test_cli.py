import os

import pytest

from shengsiong import cli, run_file


def test_eval_command(capsys):
    rc = cli.main(["eval", "print 1 + 1"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "2"


def test_run_file(tmp_path, capsys):
    f = tmp_path / "prog.sheng"
    f.write_text('print "hello from file"\n')
    rc = cli.main(["run", str(f)])
    assert rc == 0
    assert "hello from file" in capsys.readouterr().out


def test_run_stdin(monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("print 7 * 6"))
    rc = cli.main(["run", "-"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "42"


def test_run_missing_file(capsys):
    rc = cli.main(["run", "/no/such/file.sheng"])
    assert rc == 2
    assert "cannot read" in capsys.readouterr().err


def test_run_without_path(capsys):
    rc = cli.main(["run"])
    assert rc == 2
    assert "expected a file" in capsys.readouterr().err


def test_eval_without_source(capsys):
    rc = cli.main(["eval"])
    assert rc == 2
    assert "expected a source" in capsys.readouterr().err


def test_no_args_prints_usage(capsys):
    rc = cli.main([])
    assert rc == 2
    assert "Usage" in capsys.readouterr().err


def test_help_command(capsys):
    for flag in ("-h", "--help", "help"):
        rc = cli.main([flag])
        assert rc == 0
        assert "Usage" in capsys.readouterr().out


def test_unknown_command(capsys):
    rc = cli.main(["frobnicate"])
    assert rc == 2
    assert "unknown command" in capsys.readouterr().err


def test_lex_error_reported(capsys):
    rc = cli.main(["eval", "@"])
    assert rc == 1
    assert "Lex error" in capsys.readouterr().err


def test_parse_error_reported(capsys):
    rc = cli.main(["eval", "let x ="])
    assert rc == 1
    assert "Parse error" in capsys.readouterr().err


def test_runtime_error_reported(capsys):
    rc = cli.main(["eval", "print undefined_var"])
    assert rc == 1
    assert "Runtime error" in capsys.readouterr().err


def test_main_uses_argv(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prog", "eval", "print 99"])
    rc = cli.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == "99"


def test_run_file_helper(tmp_path):
    f = tmp_path / "p.sheng"
    f.write_text("store s\nproduct milk\nstock 5 units of milk at s\n")
    interp = run_file(str(f))
    assert interp.market.location("s").qty("milk") == 5


def test_examples_directory_runs():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    examples = os.path.join(here, "examples")
    files = [f for f in os.listdir(examples) if f.endswith(".sheng")]
    assert files, "expected at least one example program"
    for name in files:
        interp = run_file(os.path.join(examples, name))
        assert isinstance(interp.output, list)
