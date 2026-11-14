import configparser
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).parent.parent / "deploy"
INSTALL = DEPLOY / "install.sh"
UNINSTALL = DEPLOY / "uninstall.sh"
OPTIONS = ["--rede", "--hostname", "--sem-espeak", "--sem-avahi", "--sem-modelos", "--sim"]


def run_script(script, *args, home, path=None, cwd=None):
    """Roda o script numa pasta de casa vazia, para ele não mexer em nada de verdade."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"CUBO_CONFIG_DIR", "CUBO_DATA_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME"}
    }
    env["HOME"] = str(home)
    if path:
        env["PATH"] = f"{path}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or home,
        timeout=60,
        check=False,
    )


def simulate(*args, home, **options):
    result = run_script(INSTALL, "--simular", *args, home=home, **options)
    assert result.returncode == 0, result.stderr
    return result.stdout


def position(output, text):
    assert text in output, f"não achei {text!r} na saída:\n{output}"
    return output.index(text)


@pytest.fixture
def home(tmp_path):
    folder = tmp_path / "casa"
    folder.mkdir()
    return folder


# ---- unidade do systemd


def read_unit(text):
    unit = configparser.ConfigParser(interpolation=None, delimiters=("=",), strict=False)
    unit.optionxform = str
    unit.read_string(text)
    return unit


def test_the_unit_restarts_on_failure_and_starts_with_the_user_session():
    unit = read_unit((DEPLOY / "cubo.service").read_text())

    assert unit["Service"]["Restart"] == "on-failure"
    assert int(unit["Service"]["RestartSec"]) >= 1
    assert unit["Install"]["WantedBy"] == "default.target"
    # Uma falha de configuração não adianta repetir.
    assert unit["Service"]["RestartPreventExitStatus"] == "2"
    assert unit["Service"]["Environment"] == "PYTHONUNBUFFERED=1"


def test_the_unit_runs_the_cubo_of_the_project_virtualenv():
    unit = read_unit((DEPLOY / "cubo.service").read_text())

    assert unit["Service"]["ExecStart"] == '"@INSTALL_DIR@/.venv/bin/cubo"'
    # O systemd recusa aspas em WorkingDirectory: com elas, o serviço nem sobe.
    assert unit["Service"]["WorkingDirectory"] == "@INSTALL_DIR@"


def test_the_marker_is_replaced_everywhere(home):
    result = run_script(INSTALL, "--mostrar-unidade", home=home)

    assert result.returncode == 0
    assert "@INSTALL_DIR@" not in result.stdout
    assert str(INSTALL.parent.parent) in result.stdout


def systemd_analyze_works(tmp_path):
    probe = tmp_path / "probe.service"
    probe.write_text("[Service]\nExecStart=/bin/true\n")
    if not shutil.which("systemd-analyze"):
        return False
    result = subprocess.run(
        ["systemd-analyze", "--user", "verify", str(probe)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and not result.stderr.strip()


@pytest.mark.parametrize("folder", ["projeto", "pasta com espaço", "a%b$c&d"])
def test_the_rendered_unit_is_valid_for_systemd(tmp_path, home, folder):
    if not systemd_analyze_works(tmp_path):
        pytest.skip("systemd-analyze não funciona neste ambiente")
    project = tmp_path / folder
    shutil.copytree(DEPLOY, project / "deploy")
    cubo = project / ".venv" / "bin" / "cubo"
    cubo.parent.mkdir(parents=True)
    cubo.write_text("#!/bin/sh\nexit 0\n")
    cubo.chmod(0o755)
    rendered = run_script(project / "deploy" / "install.sh", "--mostrar-unidade", home=home)
    unit = tmp_path / "cubo.service"
    unit.write_text(rendered.stdout)

    result = subprocess.run(
        ["systemd-analyze", "--user", "verify", str(unit)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "not absolute" not in result.stderr
    assert "bad unit file" not in result.stderr


# ---- scripts


@pytest.mark.parametrize("script", [INSTALL, UNINSTALL, DEPLOY / "common.sh"])
def test_scripts_have_valid_bash_syntax(script):
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", [INSTALL, UNINSTALL])
def test_scripts_are_executable(script):
    assert os.access(script, os.X_OK)


def test_install_help_lists_every_option(home):
    result = run_script(INSTALL, "--ajuda", home=home)

    assert result.returncode == 0
    for option in [*OPTIONS, "--simular", "--mostrar-unidade"]:
        assert option in result.stdout


@pytest.mark.parametrize(
    "args, message",
    [
        (["--opcao-que-nao-existe"], "opção desconhecida"),
        (["--hostname"], "precisa de um nome"),
        (["--hostname", "Nome Inválido!"], "nome de máquina inválido"),
        (["--hostname", "-cubo"], "nome de máquina inválido"),
    ],
)
def test_install_rejects_bad_arguments(home, args, message):
    result = run_script(INSTALL, "--simular", *args, home=home)

    assert result.returncode == 2
    assert message in result.stderr
    assert "Uso:" in result.stderr


def test_a_python_older_than_3_11_is_refused_with_an_explanation(tmp_path, home):
    fake = tmp_path / "bin"
    fake.mkdir()
    python = fake / "python3"
    python.write_text('#!/bin/sh\n[ "$1" = "-V" ] && echo "Python 3.10.12" && exit 0\nexit 1\n')
    python.chmod(0o755)

    result = run_script(INSTALL, "--simular", home=home, path=fake)

    assert result.returncode == 1
    assert "3.11" in result.stderr
    assert "3.10.12" in result.stderr


def test_the_default_install_runs_every_step_in_order(home):
    output = simulate(home=home)

    steps = [
        "apt-get install -y python3-venv libportaudio2 espeak-ng avahi-daemon",
        "python3 -m venv",
        "pip install --quiet -e",
        "cubo preparar",
        "gravar",
        "loginctl enable-linger",
        "systemctl --user daemon-reload",
        "systemctl --user enable cubo.service",
        "systemctl --user restart cubo.service",
    ]
    positions = [position(output, step) for step in steps]
    assert positions == sorted(positions)


def test_simulating_changes_nothing_on_disk(home):
    simulate("--rede", "--hostname", "cubo-teste", home=home)

    assert list(home.iterdir()) == []


@pytest.mark.parametrize(
    "option, package",
    [("--sem-espeak", "espeak-ng"), ("--sem-avahi", "avahi-daemon")],
)
def test_optional_packages_can_be_left_out(home, option, package):
    assert package not in simulate(option, home=home)
    assert package in simulate(home=home)


def test_models_are_skipped_when_asked(home):
    assert "cubo preparar" not in simulate("--sem-modelos", home=home)


def test_without_network_there_is_no_certificate_and_no_panel_change(home):
    output = simulate(home=home)

    assert "openssl" not in output
    assert "listen" not in output
    assert "/tls" not in output


def test_the_network_option_creates_the_certificate_and_opens_the_panel(home):
    output = simulate("--rede", home=home)

    assert "apt-get install -y python3-venv libportaudio2 espeak-ng avahi-daemon openssl" in output
    certificate = position(output, "openssl req -x509")
    assert certificate < position(output, "chmod 600")
    assert certificate < position(output, "systemctl --user enable")
    assert "subjectAltName=DNS:" in output
    # A chave só o dono lê, e a pasta também.
    assert re.search(r"chmod 700 \S+/\.config/cubo/tls", output)


def test_the_hostname_is_only_changed_when_asked(home):
    assert "hostnamectl" not in simulate(home=home)

    output = simulate("--hostname", "cubo-teste", home=home)

    assert "hostnamectl set-hostname cubo-teste" in output
    assert position(output, "hostnamectl") < position(output, "systemctl --user enable")


def test_the_certificate_uses_the_new_hostname(home):
    output = simulate("--rede", "--hostname", "cubo-teste", home=home)

    assert "-subj /CN=cubo-teste" in output
    assert "DNS:cubo-teste.local" in output


# ---- uninstall


def uninstall(*args, home):
    result = run_script(UNINSTALL, "--simular", *args, home=home)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_uninstall_removes_the_service_and_keeps_the_data(home):
    output = uninstall(home=home)

    assert "systemctl --user disable --now cubo.service" in output
    assert "rm -f" in output and "cubo.service" in output
    assert "rm -rf" not in output
    assert list(home.iterdir()) == []


def test_uninstall_can_erase_the_configuration_and_the_models(home):
    output = uninstall("--apagar-dados", home=home)

    assert f"rm -rf {home}/.config/cubo {home}/.local/share/cubo" in output


def test_uninstall_help_and_bad_arguments(home):
    assert run_script(UNINSTALL, "--ajuda", home=home).returncode == 0

    result = run_script(UNINSTALL, "--nada", home=home)

    assert result.returncode == 2
    assert "opção desconhecida" in result.stderr
