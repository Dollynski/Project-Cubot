# Cubô

Assistente de voz open source em português, integrado ao Home Assistant. Feito para rodar numa placa ARM64 (como uma Orange Pi) ou num PC Linux.

> **Em refatoração** ([#14](https://github.com/Dollynski/Project-Cubot/issues/14)). Por enquanto o Cubô funciona em **modo texto**. O pipeline de voz volta na Fase 2 ([#19](https://github.com/Dollynski/Project-Cubot/issues/19)) e o painel web de configuração chega na Fase 3 ([#20](https://github.com/Dollynski/Project-Cubot/issues/20)).

## O que ele faz

- Conversa em português com o provedor de IA que você escolher: Gemini, Claude, OpenAI ou Ollama (local).
- Controla e consulta dispositivos do Home Assistant (luzes, tomadas, sensores) e só confirma uma ação depois de ver o estado mudar.

## Requisitos

- Linux (x86_64 ou ARM64) com Python 3.11 ou mais novo.
- Uma chave de API do provedor escolhido. Com o Ollama não precisa.
- Opcional: Home Assistant na sua rede, para controlar a casa.

## Instalação

```bash
git clone https://github.com/Dollynski/Project-Cubot.git
cd Project-Cubot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Para desenvolver, instale com `pip install -e ".[dev]"` e rode `ruff check .` e `pytest`.

## Configuração

Os arquivos ficam em `~/.config/cubo/` (ou na pasta indicada por `CUBO_CONFIG_DIR`):

- `config.toml`: provedor, modelo, personalidade, Home Assistant e dispositivos. Escreva só o que quiser mudar; o resto usa o padrão.
- `secrets.toml`: chaves e tokens, com permissão de leitura só para o dono do arquivo.

Se houver um `.env` do protótipo antigo na pasta onde você rodar o Cubô pela primeira vez, a chave do Gemini, o token e o endereço do Home Assistant são importados automaticamente.

### Chave da IA

```bash
cubo chave gemini
```

Troque `gemini` por `claude` ou `openai` conforme o provedor. A chave é pedida sem aparecer na tela. As variáveis `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` e `OPENAI_API_KEY` também funcionam e têm prioridade sobre o arquivo.

### Provedor e modelo

```toml
[llm]
provider = "claude"  # gemini, claude, openai ou ollama

[llm.models]
gemini = "gemini-3.5-flash"
claude = "claude-opus-5-5"
openai = ""          # preencha com o modelo que quiser usar
ollama = "llama3.2"  # um modelo já baixado no Ollama
```

Para o Ollama, o endereço padrão é `http://localhost:11434/v1`; outro endereço vai em `llm.ollama_url`.

### Home Assistant

1. No Home Assistant, abra seu perfil, vá em **Segurança** e crie um **token de acesso de longa duração**.
2. Salve o token:

   ```bash
   cubo chave home_assistant
   ```

3. No `config.toml`, informe o endereço e os dispositivos, cada um com o nome pelo qual você vai chamá-lo:

   ```toml
   [home_assistant]
   url = "http://192.168.0.10:8123"

   [[home_assistant.devices]]
   entity_id = "light.sala"
   alias = "luz da sala"

   [[home_assistant.devices]]
   entity_id = "sensor.temperatura_quarto"
   alias = "temperatura do quarto"
   ```

O ID de cada entidade aparece no Home Assistant em **Ferramentas de desenvolvedor → Estados**. Luzes (`light`), tomadas (`switch`), interruptores virtuais (`input_boolean`) e ventiladores (`fan`) podem ser ligados e desligados; qualquer entidade pode ser consultada.

Para testar sem dispositivos reais, crie um auxiliar do tipo **Alternar** em **Configurações → Dispositivos e serviços → Auxiliares**; ele vira uma entidade `input_boolean`.

#### Home Assistant em Docker (opcional)

```bash
docker run -d --name homeassistant --restart unless-stopped -p 8123:8123 -v "$HOME/homeassistant/config:/config" homeassistant/home-assistant:stable
```

Depois de alguns minutos, abra `http://localhost:8123` e crie a conta de administrador.

## Uso

```bash
cubo texto
```

Converse digitando; `Ctrl+D` sai. Com `cubo -v texto` aparecem os logs detalhados, sempre com as chaves mascaradas.

Exemplos: "liga a luz da sala com 30% de brilho", "qual a temperatura do quarto?", "canta uma música".

## Licença

GPL-3.0. Veja o arquivo [LICENSE](LICENSE).
