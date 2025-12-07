🤖 Projeto Cubô: Assistente de Voz Open Source (Python/Raspberry Pi)

O Cubô é um assistente de voz modular, de código aberto e baixo custo, projetado para rodar em hardware embarcado (como o Raspberry Pi). Ele utiliza uma arquitetura híbrida, processando o reconhecimento de fala localmente (whisper.cpp) e utilizando a API do Google Gemini para o processamento de linguagem natural (PLN) e interação com Smart Home (Home Assistant).

Este guia detalha o processo de instalação e configuração para que o Cubô funcione em um ambiente de desenvolvimento (Windows/Linux).

⚠️ Pré-requisitos do Sistema

Para rodar o Cubô, você precisa das seguintes ferramentas instaladas no seu ambiente:

Python 3.9+

Git

Ambiente de Compilação C/C++ (Necessário para o whisper.cpp e espeak-ng):

Windows: MSYS2 (recomendado) ou Visual Studio com ferramentas de desenvolvimento Desktop C++.

Linux/Raspberry Pi: build-essential e cmake.

Espeak-NG (Motor de TTS):

Windows: Instale via winget install espeak-ng (ou instalador oficial).

Linux/Raspberry Pi: sudo apt-get install espeak-ng.

Home Assistant (Servidor): Rodando na sua rede local (via Docker, VM ou instalação dedicada).

⚙️ 1. Configuração do Ambiente Python

1.1. Clonar o Repositório e Criar Ambiente

# 1. Clone o projeto
git clone [https://gitlab.com/senac-projetos-de-desenvolvimento/2025-jo-o-dolinski/projeto-de-desenvolvimento-assistente-de-ia]
cd projeto-cubo

# 2. Crie e ative um ambiente virtual (Recomendado)
python -m venv venv
# No Windows:
.\venv\Scripts\activate
# No Linux/macOS:
source venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt


1.2. Instalação do whisper.cpp (Speech-to-Text Local)

O Cubô utiliza o whisper.cpp para transcrição local de alta performance.

Obter o Código: Clone o repositório do whisper.cpp na sua pasta de usuário (~ ou C:\Users\SeuUsuario):

cd ~
git clone [https://github.com/ggerganov/whisper.cpp.git](https://github.com/ggerganov/whisper.cpp.git)
cd whisper.cpp


Baixar Modelo: Baixe o modelo base (usado no projeto) e o executável de download.

bash ./models/download-ggml-model.sh base


Nota: No Windows, use o terminal Git Bash para executar o comando acima.

Compilar: Compile o executável.

# Se 'make' não funcionar, tente 'mingw32-make'
make 


O executável whisper-cli (ou whisper-cli.exe) será criado em ~/whisper.cpp/build/bin.

Verificar Caminho: O arquivo integracoes/audio.py está configurado para procurar o executável em ~/whisper.cpp/build/bin. Certifique-se de que o executável está lá.

🔑 2. Configuração das Credenciais (APIs)

O Cubô precisa de chaves de acesso do Google (Gemini) e do Home Assistant.

2.1. Criar o Arquivo .env

Crie um arquivo chamado .env na pasta raiz do projeto com as seguintes variáveis:

# --- 1. GOOGLE GEMINI ---
# Obtido em Google AI Studio ou Google Cloud
GEMINI_API_KEY="SUA_CHAVE_API_GEMINI_AQUI"

# --- 2. CONFIGURAÇÕES DO HOME ASSISTANT ---
# URL: O endereço IP da sua instância do Home Assistant (HA)
# Ex: [http://192.168.1.10:8123](http://192.168.1.10:8123) (Se estiver rodando em outra máquina)
# Ex: http://localhost:8123 (Se estiver rodando em Docker no mesmo PC)
HOME_ASSISTANT_URL="http://localhost:8123"

# TOKEN: O token de acesso de longa duração do Home Assistant
HOME_ASSISTANT_TOKEN="SEU_TOKEN_LONGO_HA_AQUI"

# --- 3. CONFIGURAÇÃO DE ÁUDIO ---
# Índice do microfone (0, 1, 2...). Use 'python -m sounddevice' para listar.
MIC_DEVICE_INDEX=1 


2.2. Obter o Token do Home Assistant (HA)

Abra a interface web do Home Assistant.

Clique no ícone do seu Perfil (canto inferior esquerdo).

Role até a seção "Tokens de Acesso de Longa Duração" (Long-Lived Access Tokens).

Clique em + CRIAR TOKEN, dê um nome (ex: Cubot_API), e COPIE a chave longa gerada e cole-a no seu .env.

💡 3. Configuração da Smart Home (POC)

Para que a função de controle de luz e leitura de temperatura funcione, você precisa das seguintes entidades configuradas no seu Home Assistant.

3.1. Entidade de Controle (Lâmpada - POC)

O Cubô foi configurado para controlar uma entidade virtual que simula a lâmpada, garantindo que a POC funcione em qualquer ambiente.

Crie um Assistente: No HA, vá para Configurações -> Dispositivos e Serviços -> Assistentes (+ Criar Assistente).

Tipo: Selecione Alternar (Toggle).

Nome: Lâmpada LED.

ID: O HA cria input_boolean.lampada_led.

3.2. Entidade de Leitura (Temperatura)

O Cubô lê a temperatura a partir do sensor de clima padrão.

Verifique a Entidade: Certifique-se de que a entidade weather.forecast_home está ativa e visível no seu HA (geralmente ativada ao configurar a localização).

Dashboard: Crie um cartão no seu dashboard do HA para exibir o estado de input_boolean.lampada_led e weather.forecast_home para monitorar a interação do Cubô.

▶️ 4. Como Executar o Cubô

Com as dependências instaladas e o .env configurado:

Abra o Terminal/PowerShell.

Ative o ambiente virtual (.\venv\Scripts\activate).

Execute o arquivo principal:

python main.py


O Cubô irá iniciar o diagnóstico de conexão HA e, em seguida, começar a ouvir.

Comandos de Teste

Categoria

Comando de Voz

Resultado Esperado

Controle

"Cubô, ligue a luz."

O botão Lâmpada LED no seu Home Assistant alterna para ON.

Leitura

"Cubô, qual é a temperatura?"

O assistente responde com o valor da temperatura lido de weather.forecast_home.

Conversa

"Cubô, quem é você?"

O assistente responde com a sua apresentação.

Encerramento

"Desligar"

O programa encerra.