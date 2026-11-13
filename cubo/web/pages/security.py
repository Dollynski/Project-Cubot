"""Segurança: senha do painel e como ele pode ser acessado."""

from pathlib import Path

from nicegui import run, ui

from cubo.web.auth import PasswordError
from cubo.web.forms import apply_config, updated
from cubo.web.layout import section
from cubo.web.panel import Panel
from cubo.web.session import client_address

CERTIFICATE_COMMAND = (
    'openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=cubo" '
    "-keyout chave.pem -out certificado.pem"
)


def build(panel: Panel) -> None:
    service = panel.service
    settings = service.config.panel

    async def change_password() -> None:
        client = f"senha:{client_address()}"
        if wait := panel.throttle.seconds_locked(client):
            ui.notify(
                f"Muitas tentativas erradas. Tente de novo em {wait} segundos.", type="negative"
            )
            return
        if not await run.io_bound(panel.auth.verify, current.value):
            panel.throttle.fail(client)
            ui.notify("A senha atual está incorreta.", type="negative")
            return
        if new.value != repeat.value:
            ui.notify("As senhas novas não são iguais.", type="negative")
            return
        try:
            await run.io_bound(panel.auth.set_password, new.value)
        except PasswordError as error:
            ui.notify(str(error), type="negative")
            return
        panel.throttle.succeed(client)
        for field in (current, new, repeat):
            field.set_value("")
        ui.notify("Senha alterada.", type="positive")

    async def save_access() -> None:
        certificate, key = certificate_path.value.strip(), key_path.value.strip()
        missing = [path for path in (certificate, key) if path and not Path(path).is_file()]
        if missing:
            ui.notify(f"Arquivo não encontrado: {missing[0]}", type="negative")
            return
        new_settings = updated(
            service.config,
            panel={
                "listen": "network" if network.value else "local",
                "port": int(port.value or 0),
                "ssl_certfile": certificate,
                "ssl_keyfile": key,
            },
        )
        if await apply_config(service, new_settings):
            ui.notify("Estas mudanças valem na próxima vez que o Cubô for iniciado.", type="info")

    with section("Senha do painel"):
        current = ui.input("Senha atual", password=True).classes("w-full")
        new = ui.input("Nova senha", password=True, password_toggle_button=True).classes("w-full")
        repeat = ui.input("Repita a nova senha", password=True).classes("w-full")
        ui.button("Alterar a senha", icon="lock", on_click=change_password)
    with section("Acesso ao painel", "Valem depois de reiniciar o Cubô."):
        network = ui.switch(
            "Permitir acesso de outros aparelhos da rede (celular, outro PC)",
            value=settings.listen == "network",
        )
        port = ui.number("Porta", value=settings.port, min=1, max=65535, step=1).classes("w-full")
        warning = ui.label(
            "Sem HTTPS, a senha viaja sem criptografia pela rede. Use HTTPS se outros "
            "aparelhos forem acessar."
        ).classes("text-amber-600 text-sm")
        warning.bind_visibility_from(network, "value")
        ui.label(
            "HTTPS é opcional. Com um certificado e uma chave, o painel passa a usar https."
        ).classes("text-sm opacity-70")
        certificate_path = ui.input("Certificado (.pem)", value=settings.ssl_certfile).classes(
            "w-full"
        )
        key_path = ui.input("Chave do certificado (.pem)", value=settings.ssl_keyfile).classes(
            "w-full"
        )
        ui.label("Para gerar um certificado próprio, no terminal:").classes("text-sm opacity-70")
        ui.code(CERTIFICATE_COMMAND).classes("w-full")
        ui.button("Salvar o acesso", icon="save", on_click=save_access)
