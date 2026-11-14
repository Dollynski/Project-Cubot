"""Ponte entre os testes e o arquivo principal que o NiceGUI executa na simulação."""

from types import SimpleNamespace

# O arquivo principal roda por runpy, no mesmo processo: o teste deixa o painel aqui antes.
current = SimpleNamespace(panel=None)
