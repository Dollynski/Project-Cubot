# Cubô

Assistente de voz open source em português, integrado ao Home Assistant. Feito para rodar numa placa ARM64 (como uma Orange Pi) ou num PC Linux, e configurado por um painel web no celular ou no computador.

## O que ele faz

- Fica esperando a palavra de ativação ("hey jarvis"), escuta o pedido, responde falando e volta a esperar. O som e o reconhecimento da fala ficam na sua máquina; só a conversa vai ao provedor de IA que você escolher.
- Conversa em português com Gemini, Claude, OpenAI ou Ollama (local).
- Controla e consulta dispositivos do Home Assistant (luzes, tomadas, sensores) e só confirma uma ação depois de ver o estado mudar.
- Começa a falar na primeira frase, sem esperar a IA terminar a resposta.
- Tem um painel web para configurar tudo e acompanhar a conversa e o tempo de resposta.

## Instalação rápida (Orange Pi ou outro Linux com apt)

Precisa de Debian, Ubuntu ou Armbian com **Python 3.11 ou mais novo** (o Debian 12 e o Armbian Bookworm já têm), microfone e alto-falante.

```bash
git clone https://github.com/Dollynski/Project-Cubot.git
cd Project-Cubot
./deploy/install.sh
```

O script instala as dependências do sistema, o Cubô e os modelos de voz (cerca de 215 MB), e liga o Cubô como **serviço do usuário**: ele sobe sozinho quando a placa liga e reinicia se cair. No fim, mostra o endereço do painel e o código do primeiro acesso.

Se a placa não tem tela, libere o painel para a rede, para abrir pelo celular. Com `--rede` o script também gera um certificado HTTPS próprio, para a senha não viajar aberta:

```bash
./deploy/install.sh --rede
```

Outras opções:

| Opção | O que faz |
| --- | --- |
| `--hostname cubo` | troca o nome da máquina (pede confirmação), para abrir em `cubo.local` |
| `--sem-espeak` | não instala o `espeak-ng` (voz de reserva) |
| `--sem-avahi` | não instala o `avahi` (o endereço `nome.local`) |
| `--sem-modelos` | não baixa os modelos agora (veja `cubo preparar`) |
| `--simular` | só mostra o que faria, sem mudar nada |

Para atualizar, baixe as mudanças e rode o script de novo; ele reinstala e reinicia o serviço:

```bash
git pull
./deploy/install.sh
```

## Primeiros passos

1. Abra o endereço do painel que o script mostrou (por padrão, `http://localhost:8080`).
2. Informe o **código de primeiro acesso** e defina a senha. O código só aparece no terminal (ou no log do serviço, veja [Operação](#operação)); assim, quem está na mesma rede não consegue definir a senha antes de você.
3. Em **IA**, escolha o provedor, cole a chave de API e salve. A chave é conferida com o provedor antes de ser guardada.
4. Em **Áudio**, escolha o microfone e o alto-falante e use "Testar som".
5. Diga "hey jarvis", espere o bipe e faça o pedido.

Exemplos de pedido: "liga a luz da sala com 30% de brilho", "qual a temperatura do quarto?", "canta uma música".

## Instalação manual (PC ou desenvolvimento)

```bash
sudo apt-get install -y python3-venv libportaudio2
git clone https://github.com/Dollynski/Project-Cubot.git
cd Project-Cubot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cubo preparar
cubo
```

`cubo preparar` baixa os modelos de voz. O `espeak-ng` (`sudo apt-get install -y espeak-ng`) é opcional: serve de voz de reserva se a voz do Piper não estiver baixada.

## Comandos

| Comando | O que faz |
| --- | --- |
| `cubo` | liga a voz e o painel |
| `cubo painel` | só o painel, sem ligar o microfone (para configurar sem áudio) |
| `cubo --sem-painel` | só a voz, sem o painel |
| `cubo texto` | conversa digitando, sem áudio (`Ctrl+D` sai) |
| `cubo preparar` | baixa os modelos de voz |
| `cubo audio` | lista os microfones e alto-falantes |
| `cubo chave gemini` | guarda a chave de API (também `claude`, `openai` e `home_assistant`) |
| `cubo senha --redefinir` | apaga a senha do painel, para definir outra |
| `cubo -v` | logs detalhados, com as chaves mascaradas; vai antes do comando, como em `cubo -v texto` |

## Configuração

Quase tudo se configura pelo painel. Os arquivos ficam em `~/.config/cubo/` (ou na pasta de `CUBO_CONFIG_DIR`):

- `config.toml`: provedor, modelo, personalidade, voz, Home Assistant, dispositivos e painel. Escreva só o que quiser mudar; o resto usa o padrão.
- `secrets.toml`: chaves e tokens, com permissão de leitura só para o dono. As variáveis `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` e `HOME_ASSISTANT_TOKEN` têm prioridade sobre o arquivo.
- `panel.toml`: o hash da senha do painel e o segredo das sessões.

Os modelos de voz ficam em `~/.local/share/cubo/` (ou na pasta de `CUBO_DATA_DIR`), junto com o total de uso da IA do dia.

### IA

```toml
[llm]
provider = "claude"  # gemini, claude, openai ou ollama
max_calls_per_minute = 20  # freio de custo; zero desliga o limite
max_calls_per_day = 500

[llm.models]
gemini = "gemini-3.5-flash"
claude = "claude-opus-5-5"
openai = ""          # preencha com o modelo que quiser usar
ollama = "llama3.2"  # um modelo já baixado no Ollama
```

Para o Ollama, o endereço padrão é `http://localhost:11434/v1`; outro endereço vai em `llm.ollama_url`. A chave se guarda pelo painel ou, no terminal, por `cubo chave gemini`, `cubo chave claude` ou `cubo chave openai`.

### Voz

Para escolher o microfone e o alto-falante, liste os dispositivos com `cubo audio` e ponha parte do nome (como `"USB"`) no `config.toml`. Prefira o nome ao número: os números mudam quando um dispositivo é ligado ou desligado. Vazio usa o padrão do sistema. Todos os campos são opcionais:

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

Ao iniciar, e ao trocar um modelo pelo painel, os modelos são "aquecidos" com uma execução de teste, para o primeiro pedido não pagar a inicialização.

### Home Assistant

1. No Home Assistant, abra seu perfil, vá em **Segurança** e crie um **token de acesso de longa duração**.
2. No painel, em **Casa**, informe o endereço, cole o token ("Testar conexão" confere) e cadastre os dispositivos, cada um com o nome pelo qual você vai chamá-lo. Ou, pelo terminal, `cubo chave home_assistant` e o `config.toml`:

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

Para ter um Home Assistant de teste com Docker:

```bash
docker run -d --name homeassistant --restart unless-stopped -p 8123:8123 -e TZ=America/Sao_Paulo -v "$HOME/homeassistant/config:/config" ghcr.io/home-assistant/home-assistant:stable
```

Depois de alguns minutos, abra `http://localhost:8123` e crie a conta de administrador. Para o Home Assistant descobrir aparelhos na sua rede, troque `-p 8123:8123` por `--network host`.

### Painel

```toml
[panel]
listen = "local"    # "local" atende só este aparelho; "network" atende a rede
port = 8080
ssl_certfile = ""   # caminho do certificado, para usar HTTPS
ssl_keyfile = ""    # caminho da chave do certificado
```

- **Só neste aparelho (padrão):** o painel só atende `localhost`. Em **Segurança**, ou com `./deploy/install.sh --rede`, dá para liberar a rede (celular, outro PC); isso vale depois de reiniciar. Sem HTTPS, a senha viaja sem criptografia pela rede, então use HTTPS: informe um certificado e uma chave, ou gere um próprio com `openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=cubo" -keyout chave.pem -out certificado.pem`. O navegador avisa uma vez que o certificado não é de uma autoridade conhecida.
- **Login:** é bloqueado por alguns minutos depois de 5 senhas erradas. As sessões duram 12 horas.
- **Chaves e tokens são só de escrita:** o painel nunca mostra o valor salvo, só os 4 últimos caracteres.
- **Salvar recarrega só o que mudou:** trocar a voz não reinicia a transcrição, trocar o silêncio não reinicia nada além da gravação, e assim por diante. Se algo não carregar (modelo ausente, dispositivo inexistente), a configuração não é salva e o painel explica o motivo.

## Operação

O serviço se chama `cubo`:

```bash
systemctl --user status cubo
journalctl --user -u cubo -f
systemctl --user restart cubo
systemctl --user stop cubo
```

Para ver o código de primeiro acesso depois de ter fechado o terminal:

```bash
journalctl --user -u cubo -b | grep "Primeiro acesso"
```

Para remover o serviço (mantém a configuração e os modelos; `--apagar-dados` apaga também):

```bash
./deploy/uninstall.sh
```

## Solução de problemas

| Problema | O que fazer |
| --- | --- |
| Não ouve ou não fala | Rode `cubo audio` e escolha os dispositivos pelo nome em **Áudio**. Confira se a `libportaudio2` está instalada. |
| "modelo não foi baixado" | Rode `cubo preparar`, ou confirme o download na página **Voz e fala**. |
| Microfone USB que aparece tarde, depois de ligar a placa | A voz fica desligada e o painel avisa; clique em "Ligar a voz" na página **Início**. |
| Esqueci a senha do painel | Rode `cubo senha --redefinir` no aparelho e abra o painel de novo. |
| O painel não abre pelo celular | Libere a rede em **Segurança** (e reinicie) ou instale com `--rede`. Confira se a porta 8080 não está bloqueada. |
| O serviço não sobe | Veja `systemctl --user status cubo` e `journalctl --user -u cubo -n 50`. Depois de 10 quedas em 5 minutos o systemd para de tentar: corrija o problema e rode `systemctl --user reset-failed cubo` e `systemctl --user restart cubo`. |
| O instalador reclama do Python | O Cubô precisa do Python 3.11 ou mais novo. O Ubuntu 22.04 traz o 3.10 e não serve; use o Debian 12 ou o Armbian Bookworm. |
| A resposta demora | A página **Início** mostra o tempo de cada etapa. Se a transcrição for a lenta, teste o modelo `tiny` ou `base` (veja abaixo). |

### Medir e comparar modelos

O script `scripts/bench.py` mede, na máquina em que for rodado (por exemplo, a Orange Pi), quanto tempo cada modelo do Whisper leva e quanto erra. As frases do teste são geradas pela própria voz do Piper, então não precisa gravar nada:

```bash
python scripts/bench.py --modelos base,small --baixar
```

A tabela mostra o tempo de carga, o tempo por frase, o "fator" (tempo gasto por segundo de áudio; abaixo de 1 é mais rápido que a fala) e a proporção de palavras erradas. Sem `--baixar`, ele só usa os modelos já baixados.

## Desenvolvimento

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
shellcheck -x deploy/*.sh
pytest
```

O código fica em `cubo/`: `llm/` (provedores de IA), `voice/` (palavra de ativação, escuta, transcrição, fala), `web/` (painel), `tools/` (Home Assistant) e `service.py` (junta tudo e recarrega só o que mudou). Os testes não usam rede, áudio nem modelos: tudo isso é trocado por peças falsas.

## Licença

GPL-3.0. Veja o arquivo [LICENSE](LICENSE).
