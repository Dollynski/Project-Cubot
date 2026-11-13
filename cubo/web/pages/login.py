"""Entrada no painel: login e definição da senha no primeiro acesso."""

from nicegui import run, ui

from cubo.web.auth import PasswordError
from cubo.web.layout import centered
from cubo.web.panel import Panel
from cubo.web.session import client_address, sign_in


def build_sign_in(panel: Panel) -> None:
    if not panel.auth.has_password:
        ui.navigate.to("/primeiro-acesso")
        return

    async def submit() -> None:
        client = client_address()
        if wait := panel.throttle.seconds_locked(client):
            ui.notify(
                f"Muitas tentativas erradas. Tente de novo em {wait} segundos.", type="negative"
            )
            return
        # A conferência da senha é de propósito lenta: roda fora do laço de eventos.
        if await run.io_bound(panel.auth.verify, password.value):
            panel.throttle.succeed(client)
            sign_in()
            ui.navigate.to("/")
        else:
            panel.throttle.fail(client)
            password.set_value("")
            ui.notify("Senha incorreta.", type="negative")

    with centered("Entrar no Cubô"):
        password = ui.input("Senha", password=True, password_toggle_button=True)
        password.classes("w-full").on("keydown.enter", submit)
        ui.button("Entrar", on_click=submit).classes("w-full")


def build_first_access(panel: Panel) -> None:
    if panel.auth.has_password:
        ui.navigate.to("/entrar")
        return

    async def submit() -> None:
        client = f"primeiro-acesso:{client_address()}"
        if wait := panel.throttle.seconds_locked(client):
            ui.notify(
                f"Muitas tentativas erradas. Tente de novo em {wait} segundos.", type="negative"
            )
            return
        if not panel.auth.check_setup_code(code.value):
            panel.throttle.fail(client)
            ui.notify(
                "Código incorreto. Ele aparece no terminal onde o Cubô foi iniciado.",
                type="negative",
            )
            return
        if new.value != repeat.value:
            ui.notify("As senhas não são iguais.", type="negative")
            return
        try:
            await run.io_bound(panel.auth.set_password, new.value)
        except PasswordError as error:
            ui.notify(str(error), type="negative")
            return
        panel.throttle.succeed(client)
        sign_in()
        ui.navigate.to("/")

    with centered("Primeiro acesso"):
        ui.label(
            "Defina a senha do painel. Para provar que você está no aparelho, "
            "informe o código que o Cubô mostrou no terminal ao iniciar."
        ).classes("text-sm opacity-70")
        code = ui.input("Código do terminal").classes("w-full")
        new = ui.input("Nova senha", password=True, password_toggle_button=True).classes("w-full")
        repeat = ui.input("Repita a senha", password=True).classes("w-full")
        repeat.on("keydown.enter", submit)
        ui.button("Definir senha", on_click=submit).classes("w-full")
