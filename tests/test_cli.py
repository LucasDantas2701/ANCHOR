"""Command-line options: English names, with the old Portuguese ones still accepted."""

import argparse

import pytest

from anchor.cli import option, require
from anchor.planner.config import get_profile


def parser():
    ap = argparse.ArgumentParser()
    option(ap, "--profile", "--perfil")
    option(ap, "--memory", "--memoria", default="memory/agent.json")
    option(ap, "--run", "--executar", action="store_true")
    option(ap, "--max-attempts", "--max-tentativas", type=int, default=3)
    return ap


def test_english_options():
    args = parser().parse_args(["--profile", "p", "--run", "--max-attempts", "5"])
    assert (args.profile, args.memory, args.run, args.max_attempts) == ("p", "memory/agent.json", True, 5)


def test_old_portuguese_options_still_work():
    args = parser().parse_args(["--perfil", "p", "--memoria", "m.json", "--executar", "--max-tentativas", "2"])
    assert (args.profile, args.memory, args.run, args.max_attempts) == ("p", "m.json", True, 2)


def test_old_options_are_hidden_from_help():
    text = parser().format_help()
    assert "--profile" in text and "--perfil" not in text and "--memoria" not in text


def test_required_option_is_checked():
    ap = parser()
    with pytest.raises(SystemExit):
        require(ap, ap.parse_args([]), "--profile")


def test_old_profile_names_still_work():
    assert get_profile("ollama-pequeno").name == "ollama-small"
    assert get_profile("ollama-medio").name == "ollama-medium"
