"""Núcleo do Cubô: recebe o pedido em texto e devolve a resposta pronta para ser falada."""

import logging

from cubo.llm.base import ChatProvider, ProviderError
from cubo.llm.memory import ConversationMemory
from cubo.speech_text import to_speech
from cubo.tools.registry import ToolRegistry
from cubo.usage import UsageTracker

logger = logging.getLogger(__name__)


class Assistant:
    def __init__(
        self,
        *,
        provider: ChatProvider,
        tools: ToolRegistry,
        memory: ConversationMemory,
        system_prompt: str,
        usage: UsageTracker | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._memory = memory
        self._system_prompt = system_prompt
        self._usage = usage

    def reply(self, user_text: str) -> str:
        """Responde ao pedido. Falhas do provedor viram uma frase explicando o problema."""
        try:
            if self._usage is not None:
                self._usage.acquire()
            reply = self._provider.reply(
                system=self._system_prompt,
                history=self._memory.history(),
                user_text=user_text,
                tools=self._tools,
            )
        except ProviderError as error:
            # Já tratada e comunicada ao usuário na resposta; fica registrada só em INFO.
            logger.info("Falha no provedor de IA: %s", error.user_message)
            logger.debug("Detalhes da falha", exc_info=True)
            return error.user_message
        if self._usage is not None:
            self._usage.add_tokens(reply.usage)
        self._memory.add(reply.exchange)
        return to_speech(reply.text)
