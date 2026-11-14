"""O que as páginas do painel recebem: o serviço, a senha e o bloqueio de tentativas."""

from dataclasses import dataclass

from cubo.service import CuboService
from cubo.web.auth import LoginThrottle, PanelAuth


@dataclass
class Panel:
    service: CuboService
    auth: PanelAuth
    throttle: LoginThrottle
