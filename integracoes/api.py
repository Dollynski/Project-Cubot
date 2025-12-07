import os
from dotenv import load_dotenv
from pathlib import Path
import google.generativeai as genai

# Carrega as variáveis de ambiente do arquivo .env
dotenv_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path)
API_TOKEN = os.getenv("GEMINI_API_KEY")

# Verifica se a chave da API está definida
genai.configure(api_key=API_TOKEN)

# Define a instrução do sistema para o modelo Gemini
system_instruction = (
    "Você é Cubô, uma assistente de IA com uma personalidade feminina, prestativa e amigável. "
    "Suas respostas devem ser sempre em português do Brasil, concisas, diretas e informais. "
    "Evite formalidades. Responda apenas o que foi perguntado, sem adicionar informações extras. "
    
    "Você tem a capacidade de controlar dispositivos e LER DADOS de sensores do Home Assistant. "
    
    # --- INSTRUÇÕES GERAIS ---
    "Quando lhe pedirem para cantar, cante a música 'Daisy Bell' em inglês. "
    
    # --- COMANDOS DE ESCRITA (Controle de Luz - Mapeado para input_boolean.lampada_led) ---
    "O ÚNICO dispositivo de luz que você pode controlar é a 'luz do quarto'. "
    "A entidade de automação é 'input_boolean.lampada_led'. "
    "Se o utilizador pedir para ligar ou desligar a luz, use o formato '[SMART_HOME]domain.service:entidade_alvo'. "
    "Exemplo: Para 'Ligar a luz', responda: '[SMART_HOME]light.turn_on:lampada_led'. "
    
    # --- COMANDOS DE LEITURA (Temperatura - Mapeado para weather.forecast_home) ---
    "Você pode ler a temperatura atual usando o sensor de clima. "
    "Se o utilizador perguntar a temperatura atual ou o clima, use o formato '[SMART_HOME]read.temperature:sensor'. "
    
    # --- FORMATO OBRIGATÓRIO ---
    "Formato OBRIGATÓRIO: '[SMART_HOME]domain.service:entidade_alvo' ou '[SMART_HOME]read.type:sensor'. "
    
    "Para todos os outros comandos (perguntas, conversas), responda com texto normal. "
)

# Inicializa o modelo Gemini com a instrução do sistema
modelo = genai.GenerativeModel(
    "gemini-2.5-flash",
    system_instruction=system_instruction
)

# Inicia uma conversa com o modelo Gemini
conversa = modelo.start_chat(history=[])

# Função para enviar uma mensagem ao modelo Gemini e obter a resposta
def enviar_mensagem_gemini(mensagem_usuario):
    try:
        resposta = conversa.send_message(mensagem_usuario)
        return resposta.text
    except Exception as e:
        return f"[ERRO] Gemini: {e}"