import os
from dotenv import load_dotenv
from pathlib import Path
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from scipy.signal import resample
import subprocess

# Carrega Configurações do Ambiente
dotenv_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path)

# Configurações de STT (Whisper.cpp e SoundDevice)
MIC_SAMPLE_RATE = 48000      # Taxa de amostragem nativa do microfone
WHISPER_SAMPLE_RATE = 16000  # Taxa de amostragem que o Whisper espera
CHANNELS = 1
DTYPE = 'int16'
TEMP_WAV_FILE = "temp_audio.wav" 

# Carrega o índice do microfone do .env
try:
    DEVICE_INDEX = int(os.getenv("MIC_DEVICE_INDEX", 1))
except (ValueError, TypeError):
    print("[AVISO] MIC_DEVICE_INDEX no .env não é um número válido. Usando o padrão 1.")
    DEVICE_INDEX = 1

# Caminhos para o whisper.cpp 
WHISPER_CPP_DIR = Path.home() / "whisper.cpp"
WHISPER_EXECUTABLE = WHISPER_CPP_DIR / "build" / "bin" / "whisper-cli"
MODEL_PATH = WHISPER_CPP_DIR / "models/ggml-base.bin"


# Função de Síntese de Voz (Texto para Fala) 
def texto_para_voz(texto):
    if not texto:
        print("[AVISO] TTS: Texto vazio, nada para falar.")
        return True 
        
    try:
        # Comando para executar o espeak-ng:
        # -v pt: Usa voz em Português
        # -s 160: Define a velocidade de fala
        command = [
            "espeak-ng", 
            "-v", "pt", 
            "-s", "160",
            texto
        ]
        
        # Executa o comando, esperando que ele termine
        subprocess.run(command, check=True)
        
        return True 
        
    except FileNotFoundError:
        print("[ERRO] Espeak-NG não encontrado. Instale o programa no sistema.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[ERRO] Espeak-NG falhou: {e}")
        return False
    except Exception as e:
        print(f"[ERRO] TTS: {e}")
        return False


# Função de Reconhecimento de Voz (Fala para Texto)
def reconhecer_fala():
    try:
        print(f"\nOuvindo por 5 segundos a {MIC_SAMPLE_RATE} Hz no dispositivo {DEVICE_INDEX}... Fale agora!")
        recording = sd.rec(int(5 * MIC_SAMPLE_RATE), samplerate=MIC_SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE, device=DEVICE_INDEX)
        sd.wait()
        print("Gravação concluída.")

        print("Reamostrando áudio para 16000 Hz...")
        number_of_samples = round(len(recording) * float(WHISPER_SAMPLE_RATE) / MIC_SAMPLE_RATE)
        resampled_recording = resample(recording, number_of_samples)

        write(TEMP_WAV_FILE, WHISPER_SAMPLE_RATE, resampled_recording.astype('int16'))
        print("Processando com Whisper...")
        
        command = [
            str(WHISPER_EXECUTABLE),
            "-m", str(MODEL_PATH),
            "-f", TEMP_WAV_FILE,
            "-l", "pt"
        ]
        
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        lines = result.stdout.strip().split('\n')
        texto_reconhecido = lines[-1].strip() if lines else ""

        if texto_reconhecido:
            return texto_reconhecido
        else:
            print("Não foi possível transcrever o áudio.")
            return None

    except FileNotFoundError:
        print(f"[ERRO] Executável do whisper.cpp não encontrado em '{WHISPER_EXECUTABLE}'")
        print("   Verifique se o caminho está correto e se o whisper.cpp foi compilado.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"[ERRO] O whisper.cpp terminou com um erro:")
        error_lines = e.stderr.strip().split('\n')
        print(f"   - {error_lines[-1]}" if error_lines else "   - Erro desconhecido na execução.")
        return None
    except sd.PortAudioError as e:
         print(f"[ERRO] SoundDevice: Erro ao aceder ao dispositivo de áudio (índice {DEVICE_INDEX}).")
         print(f"   - Detalhe: {e}")
         print(f"   - Verifique se o índice do microfone em .env (MIC_DEVICE_INDEX={DEVICE_INDEX}) está correto.")
         return None
    except Exception as e:
        print(f"[ERRO] Ocorreu um erro crítico no processo de áudio: {e}")
        return None
    finally:
        # 5. Limpeza
        if os.path.exists(TEMP_WAV_FILE):
            os.remove(TEMP_WAV_FILE)
