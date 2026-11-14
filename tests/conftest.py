import pytest

from cubo.credentials import ENV_VARS


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Nenhum teste lê a configuração real nem as chaves do ambiente de quem roda."""
    monkeypatch.setenv("CUBO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CUBO_DATA_DIR", str(tmp_path / "data"))
    for variable in ENV_VARS.values():
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.chdir(tmp_path)
