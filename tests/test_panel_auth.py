import stat

import pytest

from cubo.web.auth import LoginThrottle, PanelAuth, PasswordError


def make_auth(tmp_path):
    return PanelAuth(tmp_path / "panel.toml")


def test_starts_without_a_password(tmp_path):
    auth = make_auth(tmp_path)

    assert not auth.has_password
    assert not auth.verify("qualquer coisa")


def test_the_right_password_opens_and_the_wrong_one_does_not(tmp_path):
    auth = make_auth(tmp_path)

    auth.set_password("senha-segura-123")

    assert auth.has_password
    assert auth.verify("senha-segura-123")
    assert not auth.verify("senha-segura-124")
    assert not auth.verify("")


def test_the_password_is_never_stored_in_clear_text(tmp_path):
    auth = make_auth(tmp_path)

    auth.set_password("senha-segura-123")

    assert "senha-segura-123" not in (tmp_path / "panel.toml").read_text()


def test_the_file_is_private_to_the_owner(tmp_path):
    auth = make_auth(tmp_path)

    auth.set_password("senha-segura-123")
    auth.session_secret()

    assert stat.S_IMODE((tmp_path / "panel.toml").stat().st_mode) == 0o600


def test_the_password_survives_a_restart(tmp_path):
    make_auth(tmp_path).set_password("senha-segura-123")

    assert make_auth(tmp_path).verify("senha-segura-123")


def test_rejects_short_passwords(tmp_path):
    with pytest.raises(PasswordError, match="8 caracteres"):
        make_auth(tmp_path).set_password("curta")


def test_changing_the_password_replaces_the_old_one(tmp_path):
    auth = make_auth(tmp_path)
    auth.set_password("senha-antiga-123")

    auth.set_password("senha-nova-1234")

    assert auth.verify("senha-nova-1234")
    assert not auth.verify("senha-antiga-123")


def test_the_session_secret_is_stable_and_random(tmp_path):
    first = make_auth(tmp_path).session_secret()

    assert len(first) >= 32
    assert make_auth(tmp_path).session_secret() == first
    assert make_auth(tmp_path / "outra").session_secret() != first


def test_clearing_the_password_also_ends_the_sessions(tmp_path):
    auth = make_auth(tmp_path)
    auth.set_password("senha-segura-123")
    secret = auth.session_secret()

    assert auth.clear_password()

    assert not auth.has_password
    assert auth.session_secret() != secret
    assert not auth.clear_password()


def test_the_first_access_needs_the_code_from_the_terminal(tmp_path):
    auth = make_auth(tmp_path)

    assert auth.check_setup_code(auth.setup_code)
    assert auth.check_setup_code(f"  {auth.setup_code} ")
    assert not auth.check_setup_code("errado")


def test_the_code_stops_working_once_there_is_a_password(tmp_path):
    auth = make_auth(tmp_path)
    code = auth.setup_code
    auth.set_password("senha-segura-123")

    assert auth.setup_code is None
    assert not auth.check_setup_code(code)


def test_each_start_has_a_different_code(tmp_path):
    assert make_auth(tmp_path).setup_code != make_auth(tmp_path / "x").setup_code


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_locks_a_client_after_too_many_failures():
    clock = Clock()
    throttle = LoginThrottle(max_attempts=3, lock_seconds=60, clock=clock)

    for _ in range(2):
        throttle.fail("1.2.3.4")
    assert throttle.seconds_locked("1.2.3.4") == 0

    throttle.fail("1.2.3.4")

    assert throttle.seconds_locked("1.2.3.4") == 60


def test_the_lock_ends_with_time():
    clock = Clock()
    throttle = LoginThrottle(max_attempts=1, lock_seconds=60, clock=clock)
    throttle.fail("a")

    clock.now += 61

    assert throttle.seconds_locked("a") == 0


def test_a_lock_does_not_affect_other_clients():
    throttle = LoginThrottle(max_attempts=1, clock=Clock())
    throttle.fail("a")

    assert throttle.seconds_locked("a") > 0
    assert throttle.seconds_locked("b") == 0


def test_success_clears_the_failure_count():
    throttle = LoginThrottle(max_attempts=3, clock=Clock())
    throttle.fail("a")
    throttle.fail("a")
    throttle.succeed("a")

    throttle.fail("a")
    throttle.fail("a")

    assert throttle.seconds_locked("a") == 0


def test_after_the_lock_the_client_gets_fresh_attempts():
    clock = Clock()
    throttle = LoginThrottle(max_attempts=2, lock_seconds=60, clock=clock)
    throttle.fail("a")
    throttle.fail("a")
    clock.now += 61

    throttle.fail("a")

    assert throttle.seconds_locked("a") == 0
