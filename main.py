import os
from dotenv import load_dotenv
import time

# Importando funções do Cubô
from integracoes.api import enviar_mensagem_gemini
from integracoes.audio import texto_para_voz
from integracoes.audio import reconhecer_fala
from integracoes.smarthome import diagnose_ha_connection
from integracoes.smarthome import handle_smart_home_command # Adicionado para processar comandos

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

def main():
    try:
        # Mensagens de inicialização para o usuário
        print("="*50)
        print("Cubô iniciado em modo de escuta contínua.")
        print("Fale seu comando a qualquer momento.")
        print("Diga 'desligar' para encerrar o programa.")
        print("="*50)

        # Mensagem de boas-vindas em voz
        diagnose_ha_connection() # Roda o diagnóstico (Token/URL)
        texto_para_voz("Assistente iniciado. Já estou ouvindo.")
        
        # Loop Principal
        while True:
            
            tts_sucesso = False
            resposta_final = "" # Armazena a resposta final (Gemini ou Smart Home)

            # Chamamos diretamente a função de reconhecimento de fala.
            print("\nOuvindo...")
            entrada_usuario = reconhecer_fala()

            if entrada_usuario:
                print(f"Você disse: {entrada_usuario}")

                if "desligar" in entrada_usuario.lower():
                    print("Cubô encerrando. Até logo!")
                    texto_para_voz("Até logo!")
                    break 

                # Envia para o Gemini e obtém a resposta bruta
                print("Pensando...")
                resposta_bruta = enviar_mensagem_gemini(entrada_usuario)
                
                if resposta_bruta.startswith("[SMART_HOME]"):
                    print("Comando Smart Home detectado.")
                    
                    # Extrai a ação/leitura e a entidade: "[SMART_HOME]domain.service:entidade_alvo"
                    action_entity = resposta_bruta[len("[SMART_HOME]"):].strip()
                    
                    if ':' in action_entity:
                        try:
                            # Ação/Comando (light.turn_on ou read.temperature) e Entidade Alvo (lampada_led ou sensor)
                            action, entity = action_entity.split(':', 1)
                            
                            # Chama a função de automação/leitura no smarthome.py
                            resposta_final = handle_smart_home_command(action, entity)
                        except ValueError:
                            resposta_final = "Erro no formato do comando de automação."
                    else:
                        resposta_final = "Comando de automação incompleto."
                        
                else:
                    # Se não for comando, é a resposta de texto normal do Gemini
                    resposta_final = resposta_bruta

                print(f"Cubô: {resposta_final}")

                # Converte a resposta final em voz e armazena o status de sucesso
                tts_sucesso = texto_para_voz(resposta_final)
            
            # Lógica de Sincronização de Áudio
            if tts_sucesso:
                time.sleep(0.5) 
                
            else:
                # Caso o reconhecimento de fala tenha falhado ou retornado None (silêncio/ruído)
                print("Não consegui entender ou nenhum som foi detectado. Ouvindo novamente...")
                time.sleep(0.1) 


    except KeyboardInterrupt:
        print("\nEncerrado pelo usuário (Ctrl+C).")
    except Exception as e:
        print(f"[ERRO GERAL] Ocorreu um erro inesperado: {e}")
    finally:
        print("Programa finalizado.")

if __name__ == "__main__":
    main()