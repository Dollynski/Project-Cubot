import re
import shlex
from pathlib import Path

import pytest

import cubo.__main__ as cli
from tests.test_deploy import DEPLOY, INSTALL, UNINSTALL, run_script

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text()

FENCE = re.compile(r"^[ \t]*```(\w*)\n(.*?)^[ \t]*```", re.DOTALL | re.MULTILINE)
LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")


def code_blocks(language=None):
    return [body for lang, body in FENCE.findall(README) if language is None or lang == language]


INLINE_CODE = re.compile(r"`([^`\n]+)`")


def command_lines(prefix):
    """Comandos que começam com ``prefix``, nos blocos bash e nos trechos de código das frases."""
    candidates = [
        line.strip() for block in code_blocks("bash") for line in block.splitlines() if line.strip()
    ]
    candidates += INLINE_CODE.findall(FENCE.sub("", README))
    return [shlex.split(text, comments=True) for text in candidates if text.startswith(prefix)]


def slug(heading):
    """Âncora que o GitHub cria para um título."""
    text = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"\s", "-", text.strip())


def test_the_readme_has_commands_to_check():
    assert len(command_lines("cubo ")) >= 8
    assert len(command_lines("./deploy/")) >= 3


@pytest.mark.parametrize("command", command_lines("cubo "), ids=lambda c: " ".join(c))
def test_every_cubo_command_is_accepted_by_the_cli(command):
    # O parser recusa comando ou opção que não existe e termina com SystemExit.
    cli._build_parser().parse_args(command[1:])


@pytest.mark.parametrize("command", command_lines("./deploy/"), ids=lambda c: " ".join(c))
def test_every_deploy_command_is_accepted_by_the_scripts(tmp_path, command):
    script = {"install.sh": INSTALL, "uninstall.sh": UNINSTALL}[Path(command[0]).name]
    assert script.parent == DEPLOY

    result = run_script(script, "--simular", *command[1:], home=tmp_path)

    assert result.returncode == 0, result.stderr


def test_code_blocks_have_no_markdown_links_or_known_typos():
    for block in code_blocks():
        assert "](" not in block, f"link de markdown dentro de um bloco de código:\n{block}"
        assert "apt get" not in block
        assert "docker run-d" not in block


def test_every_internal_link_points_to_a_heading():
    anchors = {slug(title) for title in re.findall(r"^#{1,6}\s+(.+)$", README, re.MULTILINE)}

    for _, target in LINK.findall(README):
        if target.startswith("#"):
            assert target[1:] in anchors, f"âncora sem título: {target}"


def test_every_relative_link_points_to_a_file():
    for _, target in LINK.findall(README):
        if not target.startswith(("http", "#", "mailto:")):
            assert (ROOT / target).exists(), f"arquivo que não existe: {target}"


def test_the_readme_does_not_mention_the_old_flow():
    for old in ("whisper.cpp", "python main.py", "requirements.txt", ".env"):
        assert old not in README
