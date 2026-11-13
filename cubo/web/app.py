"""Registro das páginas do painel e subida do servidor."""

from collections.abc import Callable
from pathlib import Path

import ifaddr
from nicegui import app, ui
from nicegui.storage import Storage

from cubo.config import PanelSettings
from cubo.web import layout, session
from cubo.web.pages import home, login
from cubo.web.panel import Panel

PAGES: dict[str, Callable[[Panel], None]] = {
    "/": home.build,
}


def register_pages(panel: Panel) -> None:
    @ui.page("/entrar")
    def sign_in_page() -> None:
        login.build_sign_in(panel)

    @ui.page("/primeiro-acesso")
    def first_access_page() -> None:
        login.build_first_access(panel)

    for path, build in PAGES.items():
        _register_protected(panel, path, build)


def _register_protected(panel: Panel, path: str, build: Callable[[Panel], None]) -> None:
    @ui.page(path)
    def protected_page() -> None:
        if not panel.auth.has_password:
            ui.navigate.to("/primeiro-acesso")
        elif not session.is_signed_in():
            ui.navigate.to("/entrar")
        else:
            with layout.frame(path, _sign_out):
                build(panel)


def _sign_out() -> None:
    session.sign_out()
    ui.navigate.to("/entrar")


def run_panel(panel: Panel, settings: PanelSettings, storage_dir: Path) -> None:
    """Sobe o painel e só retorna quando o servidor for encerrado."""
    Storage.path = storage_dir
    register_pages(panel)
    app.on_shutdown(panel.service.stop)
    ui.run(
        host=settings.host,
        port=settings.port,
        title="Cubô",
        favicon="🤖",
        dark=None,
        language="pt-BR",
        reload=False,
        show=False,
        show_welcome_message=False,
        storage_secret=panel.auth.session_secret(),
        **(
            {"ssl_certfile": settings.ssl_certfile, "ssl_keyfile": settings.ssl_keyfile}
            if settings.https
            else {}
        ),
    )


def panel_urls(settings: PanelSettings) -> list[str]:
    """Endereços para abrir o painel, conforme o modo de acesso."""
    scheme = "https" if settings.https else "http"
    if settings.listen == "local":
        return [f"{scheme}://localhost:{settings.port}"]
    addresses = [
        ip.ip
        for adapter in ifaddr.get_adapters()
        for ip in adapter.ips
        if ip.is_IPv4 and not str(ip.ip).startswith("127.")
    ]
    return [f"{scheme}://{address}:{settings.port}" for address in addresses]
