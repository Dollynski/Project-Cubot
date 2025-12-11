import os
import requests
import json
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do .env
load_dotenv()

# Configurações do Home Assistant
HA_URL = os.getenv("HOME_ASSISTANT_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN") 

# ID das Entidades Home Assistant
ENTIDADE_LAMPADA = "input_boolean.lampada_led"
ENTIDADE_TEMPERATURA = "weather.forecast_home" 

def diagnose_ha_connection():
    if not HA_TOKEN:
        print("[HA DIAGNÓSTICO] ERRO: Token do Home Assistant não configurado no arquivo .env.")
        return

    url = f"{HA_URL}/api/"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    
    print("\n--- DIAGNÓSTICO DE CONEXÃO HA ---")
    print(f"Tentando URL: {url}")
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            print("[HA DIAGNÓSTICO] SUCESSO (200)! Token e URL estão CORRETOS.")
        elif response.status_code == 401:
            print("[HA DIAGNÓSTICO] ERRO (401)! Token INVÁLIDO/EXPIRADO.")
        else:
            print(f"[HA DIAGNÓSTICO] ERRO (Status {response.status_code}): Falha desconhecida. Resposta: {response.text}")

    except requests.exceptions.ConnectionError:
        print(f"[HA DIAGNÓSTICO] ERRO: Falha de Conexão. O Home Assistant NÃO está acessível em {HA_URL}.")
    except Exception as e:
        print(f"[HA DIAGNÓSTICO] ERRO GERAL: {e}")
    
    print("-----------------------------------")

def get_ha_entity_state(entity_id: str):
    if not HA_TOKEN:
        print("[HA ERROR] Token do Home Assistant não configurado.")
        return None
        
    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            # LÓGICA DE EXTRAÇÃO DE TEMPERATURA
            if entity_id == ENTIDADE_TEMPERATURA:
                # Busca o atributo 'temperature' ou 'current_temperature'
                temp_value = data.get('attributes', {}).get('temperature')
                if temp_value is None:
                    temp_value = data.get('attributes', {}).get('current_temperature')

                if temp_value is not None:
                    return str(temp_value)
                else:
                    return None
            
            return data.get('state')
            
        else:
            print(f"[HA ERROR] Falha ao ler estado ({response.status_code}): {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"[HA ERROR] Falha de Conexão ao ler estado em: {HA_URL}")
        return None
    except Exception as e:
        print(f"[HA ERRO GERAL ao ler estado]: {e}")
        return None

def call_ha_service(domain: str, service: str, entity_id: str):
    if not HA_TOKEN:
        return False
        
    url = f"{HA_URL}/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"entity_id": entity_id}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        
        if response.status_code == 200 or response.status_code == 201:
            print(f"[HA SUCCESS] Chamada: {domain}.{service} em {entity_id}")
            return True
        else:
            # Tratamento de Erros Detalhado
            if response.status_code == 401:
                print("[HA ERROR] 401 Não Autorizado. Token inválido.")
            elif response.status_code == 404:
                print(f"[HA ERROR] 404 URL não encontrada.")
            elif response.status_code == 400:
                print(f"[HA ERROR] 400 Bad Request. O domínio/serviço '{domain}.{service}' não existe para a entidade {entity_id}")
            else:
                print(f"[HA ERROR] Falha na API: {response.status_code}")
            
            print(f"[HA ERROR] Resposta: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"[HA ERROR] Falha de Conexão. Home Assistant não acessível em: {HA_URL}.")
        return False
    except Exception as e:
        print(f"[HA ERRO GERAL]: {e}")
        return False

def handle_smart_home_command(action: str, entity: str):
    try:
        if action.startswith("read."):
            domain, data_type = action.split('.')
            if data_type == 'temperature':
                temp_value = get_ha_entity_state(ENTIDADE_TEMPERATURA)
                if temp_value is not None:
                    return f"A temperatura ambiente atual é de {temp_value} graus Celsius."
                return "Desculpe, não consegui obter a leitura da temperatura."
            
            return f"Não tenho suporte para ler dados do tipo {data_type}."

        domain, service = action.split('.')
    except ValueError:
        return "Comando de automação inválido. Formato esperado: domain.service."

    if domain == 'light':
        domain = 'input_boolean' 
        target_entity_id = ENTIDADE_LAMPADA
        feedback_entity_name = "a lâmpada LED de teste"
    else:
        return f"Não encontrei mapeamento para o domínio '{domain}'."

    if call_ha_service(domain, service, target_entity_id):
        if service == 'turn_on' or service == 'start':
            feedback_service = "ligado"
        elif service == 'turn_off' or service == 'stop':
            feedback_service = "desligado"
        elif service == 'toggle':
            feedback_service = "alternado (ligado/desligado)"
        else:
            feedback_service = "executado"
            
        return f"Comando '{feedback_service}' executado com sucesso para {feedback_entity_name}."
    else:
        # Se a chamada falhar, o erro detalhado é impresso em call_ha_service
        return f"Desculpe, a automação falhou para {feedback_entity_name}. Verifique o log para o erro da API."