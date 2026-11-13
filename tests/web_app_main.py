"""Arquivo principal do painel nos testes: registra as páginas com o painel do teste.

O nome não pode terminar em ``_test.py``: o pytest executaria o arquivo na coleta e subiria um
servidor de verdade (e abriria o navegador).
"""

from nicegui import ui

from cubo.web.app import register_pages
from tests.web_support import current

register_pages(current.panel)
ui.run(storage_secret="segredo-de-teste", reload=False, show=False, title="Cubô (teste)")
