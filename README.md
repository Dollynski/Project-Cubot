# Cubô

Assistente de voz open source em português, integrado ao Home Assistant. Feito para rodar numa placa ARM64 (como uma Orange Pi) ou num PC Linux.

> **Em refatoração** ([#14](https://github.com/Dollynski/Project-Cubot/issues/14)). O Cubô funciona por **voz**, em **modo texto** e tem um **painel web** para configurar tudo. Ainda faltam a otimização da latência e a instalação como serviço (Fases 4 e 5).

## O que ele faz

- Fica esperando a palavra de ativação ("hey jarvis"), escuta o pedido, responde falando e volta a esperar. Tudo na sua máquina, exceto a conversa com o provedor de IA escolhido.
- Tem um painel web (no celular ou no PC) para configurar áudio, voz, IA e Home Assistant sem editar arquivos.
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
stream_speech = true            # fala a primeira frase sem esperar a IA terminar
```

O Cubô fala **frase por frase enquanto a IA ainda escreve a resposta**, em vez de esperar a resposta inteira (dá para desligar em **Voz e fala**). Ao iniciar, e ao trocar um modelo no painel, os modelos são "aquecidos" com uma execução de teste, para o primeiro pedido não pagar a inicialização.

Sem a voz do Piper, o Cubô usa o `espeak-ng` (`sudo apt install espeak-ng`), se estiver instalado, com um aviso.

### Medir e comparar modelos

O script `scripts/bench.py` mede, na máquina em que for rodado (por exemplo, a Orange Pi), quanto tempo cada modelo do Whisper leva e quanto erra. As frases do teste são geradas pela própria voz do Piper, então não precisa gravar nada:

```bash
python scripts/bench.py --modelos base,small --baixar
```

A tabela mostra o tempo de carga, o tempo por frase, o "fator" (tempo gasto por segundo de áudio; abaixo de 1 é mais rápido que a fala) e a proporção de palavras erradas. Sem `--baixar`, ele só usa os modelos já baixados.

## Painel web

Ao rodar `cubo`, o painel sobe junto com a voz. O terminal mostra o endereço (por padrão, `http://localhost:8080`).

No **primeiro acesso** o painel pede uma senha nova e o **código que o terminal mostrou** ao iniciar. Assim, quem está só na mesma rede não consegue definir a senha antes de você. Depois disso, o acesso é por senha, e o login é bloqueado por alguns minutos depois de 5 tentativas erradas.

Páginas:

- **Início:** o que o Cubô está fazendo (aguardando, ouvindo, pensando, falando), o volume do microfone, a conversa recente, o **tempo de resposta por etapa** (transcrição, IA, começar a falar) e o uso da IA.
- **Áudio:** escolha do microfone e do alto-falante, com teste de som.
- **Voz e fala:** palavra de ativação e sensibilidade, tempo de silêncio, modelo do Whisper e voz do Piper. Se faltar algum modelo, o painel avisa o tamanho e oferece baixar.
- **IA:** provedor, modelo, chave de API, personalidade, memória e limites de uso.
- **Casa:** endereço e token do Home Assistant, com teste de conexão, e os dispositivos.
- **Segurança:** troca de senha e como o painel pode ser acessado.

Detalhes:

- As **chaves e tokens são só de escrita**: o painel nunca mostra o valor salvo, só os 4 últimos caracteres. Cada chave é conferida com o provedor antes de ser salva, e uma chave recusada não é guardada.
- **Salvar recarrega só o que mudou**: trocar a voz não reinicia a transcrição, trocar o silêncio não reinicia nada além da gravação, e assim por diante. Se algo não carregar (modelo ausente, dispositivo inexistente), a configuração não é salva e o painel explica o motivo.
- **Limites de uso:** chamadas à IA por minuto e por dia (zero desliga o limite) e um contador de tokens. O total do dia fica salvo, então o limite vale também depois de reiniciar.
- **Só neste aparelho (padrão):** o painel só atende `localhost`. Em **Segurança** dá para liberar o acesso de outros aparelhos da rede (celular, outro PC); isso vale depois de reiniciar. Nesse caso use HTTPS: informe um certificado e uma chave, ou gere um próprio com `openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=cubo" -keyout chave.pem -out certificado.pem`.
- **Esqueci a senha:** rode `cubo senha --redefinir` no aparelho e abra o painel de novo.

Variações de uso:

```bash
cubo painel        # só o painel, sem ligar o microfone (para configurar sem áudio)
cubo --sem-painel  # só a voz, sem o painel
```

As mesmas opções ficam no `config.toml`, na seção `[panel]`:

```toml
[panel]
listen = "local"    # ou "network"
port = 8080
ssl_certfile = ""   # caminho do certificado, para usar HTTPS
ssl_keyfile = ""    # caminho da chave do certificado
```

e os limites de uso, em `[llm]`: `max_calls_per_minute = 20` e `max_calls_per_day = 500`.

## Uso

```bash
cubo
```

O Cubô fica ouvindo: diga "hey jarvis", espere o bipe e faça o pedido. `Ctrl+C` sai. O painel web sobe junto (veja [Painel web](#painel-web)).

Para conversar digitando, sem áudio:

```bash
cubo texto
```

`Ctrl+D` sai. Com `cubo -v` ou `cubo -v texto` aparecem os logs detalhados, sempre com as chaves mascaradas.

Exemplos: "liga a luz da sala com 30% de brilho", "qual a temperatura do quarto?", "canta uma música".

## Licença

GPL-3.0. Veja o arquivo [LICENSE](LICENSE).
