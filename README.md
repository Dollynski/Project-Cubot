# 🤖 Projeto Cubô: Assistente de Voz Open Source (Python/Raspberry Pi) | PT-BR

O Cubô é um assistente de voz modular, de código aberto e baixo custo, projetado para rodar em hardware embarcado (como o Raspberry Pi, por exemplo). Ele utiliza uma arquitetura híbrida, processando o reconhecimento de fala localmente (whisper.cpp) e utilizando a API do Google Gemini para o processamento de linguagem natural (PLN) e interação com Smart Home (Home Assistant).

Este guia detalha o processo de instalação e configuração para que o Cubô funcione em um ambiente de desenvolvimento (Windows/Linux).

# ⚠️ Pré-requisitos do Sistema

Para rodar o Cubô, você precisa das seguintes ferramentas instaladas no seu ambiente:

- Python 3.9+
- Git
- Ambiente de Compilação C/C++ (Necessário para o whisper.cpp e espeak-ng):
- Windows: MSYS2 (recomendado) ou Visual Studio com ferramentas de desenvolvimento Desktop C++.
- Linux/Raspberry Pi: build-essential e cmake.
- Espeak-NG (Motor de TTS):
- Windows: Instale via winget install espeak-ng (ou instalador oficial).
- Linux/Raspberry Pi: sudo apt-get install espeak-ng.
- Home Assistant (Servidor): Rodando na sua rede local (via Docker, VM ou instalação dedicada).

# ⚙️ 1. Configuração do Ambiente Python

## 1.1. Clone o projeto
`git clone https://github.com/Dollynski/Project-Cubot`
`cd projeto-cubo`

## 1.2. Crie e ative um ambiente virtual (Recomendado)
`python -m venv venv`

No Windows:
`.\venv\Scripts\activate`

No Linux/macOS:
`source venv/bin/activate`

## 1.3. Instale as dependências
`pip install -e .`

Para desenvolver (lint e testes): `pip install -e ".[dev]"`


# 1.4. Instalação do whisper.cpp (Speech-to-Text Local)

O Cubô utiliza o whisper.cpp para transcrição local de alta performance.

## 1.5. Obter o Código: Clone o repositório do whisper.cpp na sua pasta de usuário (~ ou C:\Users\SeuUsuario):

`cd ~
git clone [https://github.com/ggerganov/whisper.cpp.git](https://github.com/ggerganov/whisper.cpp.git)
cd whisper.cpp`


## 1.6. Baixar Modelo: Baixe o modelo base (usado no projeto) e o executável de download.

`bash ./models/download-ggml-model.sh base`

Nota: No Windows, use o terminal Git Bash para executar o comando acima.

## 1.7. Compilar: Compile o executável.

`make`

Nota: Se 'make' não funcionar, tente 'mingw32-make'

O executável whisper-cli (ou whisper-cli.exe) será criado em ~/whisper.cpp/build/bin.

## 1.8. Verificar Caminho: O arquivo integracoes/audio.py está configurado para procurar o executável em ~/whisper.cpp/build/bin. Certifique-se de que o executável está lá.

# 💻 2. Configuração do Servidor Home Assistant (Docker)

Esta secção detalhe como instalar a biblioteca Home Assistant (HA) como servidor central de automação no seu ambiente de desenvolvimento.

## 2.1 . Instalação do Docker Engine
- Windows/ macOS: Instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Linux (Debian/Ubuntu): Siga os comandos de instalação do Docker engine.
  
  `sudo apt-get update
  sudo apt get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker $USER`

## 2.2 Iniciar o Servidor HA
Abra o terminal e execute o comando para baixar e rodar a imagem estável do Home Assistant na porta 8123:

`docker run-d --name homeassistant --restart unless-stopped -p 8123:8123 -v $HOME/homeassistant/config:/config homeassistant/home-assistant:stable`

Nota: Este comando funciona tanto no PowerShell quanto no Terminal Linux. 

## 2.3 Acesso e Configuração
- Acesso Inicial: Após 2-5 minutos, acesse ao HA no seu navegador: `http://localhost:8123`
- Criação de Conta: Crie sua conta de administrador local.

# 🔑 3. Configuração das Credenciais (APIs)

O Cubô precisa de chaves de acesso da sua LLM de preferência. O uso do Google Gemini é o recomendado, mas não é um requerimento para este projeto. Por fim, também será necessário obter chaves de acesso da API Home Assistant.

## 3.1. Criar o Arquivo .env

Crie um arquivo chamado .env na pasta raiz do projeto com as seguintes variáveis:

`# --- 1. GOOGLE GEMINI ---`
`# Obtido em Google AI Studio ou Google Cloud`
`GEMINI_API_KEY="SUA_CHAVE_API_GEMINI_AQUI"`

`# --- 2. CONFIGURAÇÕES DO HOME ASSISTANT ---`
`# - URL: O endereço IP da sua instância do Home Assistant (HA)`
`# Ex: [http://192.168.1.10:8123](http://192.168.1.10:8123) (Se estiver rodando em outra máquina)`
`# Ex: http://localhost:8123 (Se estiver rodando em Docker no mesmo PC)`
`HOME_ASSISTANT_URL="http://localhost:8123"`
`# - TOKEN: O token de acesso de longa duração do Home Assistant`
`HOME_ASSISTANT_TOKEN="SEU_TOKEN_LONGO_HA_AQUI"`

`# --- 3. CONFIGURAÇÃO DE ÁUDIO ---`
`# Índice do microfone (0, 1, 2...). Use 'python -m sounddevice' para listar.`
`MIC_DEVICE_INDEX=1 `

## 3.2. Obter o Token do Home Assistant (HA)

Abra a interface web do Home Assistant.

Clique no ícone do seu Perfil (canto inferior esquerdo).

Role até a seção "Tokens de Acesso de Longa Duração" (Long-Lived Access Tokens).

Clique em + CRIAR TOKEN, dê um nome (ex: Cubot_API), e COPIE a chave longa gerada e cole-a no seu .env.

# 💡 4. Configuração da Smart Home 

Nesta etapa, será configurada a função de uma lâmpada smart e da chamada para obter a temperatura atual. Use esse passo a passo de exemplo para adicionar novas funcionalidades conforme achar necessário.

## 4.1. Entidade de Controle (Lâmpada)

Para controlar uma lâmpada física, você deve primeiro adicioná-la ao Home Assistant através de sua respectiva integração.

- No HA, vá para Configurações -> Dispositivos e Serviços
- Clique em + Adicionar Integração. Procure a marca do seu dispositivo (Ex: Tuya, Philips Hue, IKEA, MQTT, etc).
- Siga o processo do dashboard para vincular sua conta de nuvem ou rede local.
- O HA irá criar a entidade real (Ex: light.luz_da_sala).
- Vá para Ferramentas de Desenvolvedor -> Estados e localize a entidade que o HA criou para sua lâmpada (Ex: light.minha_luz_de_verdade).
- Você deve garantir que a constante ENTIDADE_LAMPADA no seu código Python use o ID real e completo dessa entidade (Ex: ENTIDADE_LAMPADA = "light.minha_luz_de_verdade")

## 4.2. Entidade de Leitura (Temperatura)

O Cubô lê a temperatura a partir do sensor de clima padrão já incluso no Home Assistant. Para garantir que o assistente tem acesso ao sensor, você deve:

- Verifique a entidade: Certifique-se de que a entidade `weather.forecast_home` está ativa e visível no seu HA (Geralmente é ativada ao configurar sua localização.)

# ▶️ 5. Como Executar o Cubô

Com as dependências instaladas e o .env configurado:

Abra o Terminal/PowerShell.

Ative o ambiente virtual (.\venv\Scripts\activate).

Execute o arquivo principal:

`python main.py`

Nota: O Cubô está configurado para ter seu programa encerrado sempre que o usuário disser o comando `"Desligar"`.

O Cubô irá iniciar o diagnóstico de conexão HA e, em seguida, começar a ouvir.

Tente conversar com ele, dê boa tarde ou peça para cantar uma música. 

Também é possível testar os comandos programados, como um pedido para acender ou apagar a luz. 

Lembre-se de que quaisquer outras interações fora as duas iniciais dependem do usuário modificar o código com seus próprios periféricos inteligentes. 

Divirta-se com o Cubô! 
