# Cubô

Assistente de voz open source em português, integrado ao Home Assistant. Feito para rodar numa placa ARM64 (como uma Orange Pi) ou num PC Linux.

> **Em refatoração** ([#14](https://github.com/Dollynski/Project-Cubot/issues/14)). O Cubô já funciona por **voz** e em **modo texto**. O painel web de configuração chega na Fase 3 ([#20](https://github.com/Dollynski/Project-Cubot/issues/20)); por enquanto a configuração é feita pelo `config.toml`.

## O que ele faz

- Fica esperando a palavra de ativação ("hey jarvis"), escuta o pedido, responde falando e volta a esperar. Tudo na sua máquina, exceto a conversa com o provedor de IA escolhido.
- Conversa em português com o provedor de IA que você escolher: Gemini, Claude, OpenAI ou Ollama (local).
- Controla e consulta dispositivos do Home Assistant (luzes, tomadas, sensores) e só confirma uma ação depois de ver o estado mudar.

## Requisitos

- Linux (x86_64 ou ARM64) com Python 3.11 ou mais novo.
- Para usar por voz: microfone, alto-falante e a biblioteca PortAudio (`sudo apt install libportaudio2`).
- Cerca de 300 MB livres para os modelos de voz.
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

Em seguida, baixe os modelos de voz (veja [Voz](#voz)). Para desenvolver, instale com `pip install -e ".[dev]"` e rode `ruff check .` e `pytest`.

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

## Voz

Os modelos de voz são baixados uma vez, para `~/.local/share/cubo/` (ou a pasta de `CUBO_DATA_DIR`):

```bash
cubo preparar
```

Isso baixa a palavra de ativação (conferida por SHA-256), a voz [Piper](https://github.com/OHF-voice/piper1-gpl) e o modelo de transcrição Whisper. Depois disso o Cubô não precisa de internet para ouvir e falar; só para falar com o provedor de IA.

Para escolher o microfone e o alto-falante, liste os dispositivos:

```bash
cubo audio
```

e ponha parte do nome (como `"USB"`) no `config.toml`. Prefira o nome ao número: os números mudam quando um dispositivo é ligado ou desligado. Vazio usa o padrão do sistema. Todos os campos são opcionais:

```toml
[voice]
input_device = "USB"            # microfone
output_device = ""              # alto-falante
wake_word = "hey_jarvis"        # ou hey_livekit, ou o caminho de um .onnx treinado por você
wake_word_threshold = 0.5       # menor ativa mais fácil, maior evita ativações falsas
silence_seconds = 0.8           # silêncio que encerra o pedido
max_listening_seconds = 15      # duração máxima de um pedido
whisper_model = "base"          # tiny, base, small... (maior = mais preciso e mais lento)
whisper_compute_type = "int8"
piper_voice = "pt_BR-faber-medium"
speech_speed = 1.0              # de 0,5 a 2
```

Sem a voz do Piper, o Cubô usa o `espeak-ng` (`sudo apt install espeak-ng`), se estiver instalado, com um aviso.

## Uso

```bash
cubo
```

O Cubô fica ouvindo: diga "hey jarvis", espere o bipe e faça o pedido. `Ctrl+C` sai.

Para conversar digitando, sem áudio:

```bash
cubo texto
```

`Ctrl+D` sai. Com `cubo -v` ou `cubo -v texto` aparecem os logs detalhados, sempre com as chaves mascaradas.

Exemplos: "liga a luz da sala com 30% de brilho", "qual a temperatura do quarto?", "canta uma música".

## Licença

GPL-3.0. Veja o arquivo [LICENSE](LICENSE).
