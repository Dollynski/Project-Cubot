"""Compara modelos do Whisper (e mede a voz) na máquina em que for rodado, como a Orange Pi.

Uso:
    python scripts/bench.py                       # base e small, com os modelos já baixados
    python scripts/bench.py --modelos tiny,base   # outros modelos
    python scripts/bench.py --baixar              # baixa o que faltar antes de medir

As frases do teste são geradas pela própria voz do Piper, então o resultado mostra o tempo de
transcrição e o quanto cada modelo erra em português, sem precisar gravar nada.
"""

import argparse
import os
import platform
import sys

from cubo.config import CONFIG_FILE_NAME, default_config_dir, load_config
from cubo.errors import SetupError
from cubo.voice.benchmark import benchmark_models, format_report, synthesize_phrases
from cubo.voice.builder import load_synthesizer
from cubo.voice.models import (
    DownloadError,
    default_data_dir,
    download_piper_voice,
    download_whisper,
    whisper_dir,
    whisper_downloaded,
)
from cubo.voice.stt import Transcriber


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--modelos", default="base,small", help="modelos do Whisper, separados por vírgula"
    )
    parser.add_argument("--precisao", default="int8", help="int8 (padrão) ou float32")
    parser.add_argument(
        "--repeticoes", type=int, default=2, help="vezes que cada frase é transcrita"
    )
    parser.add_argument("--baixar", action="store_true", help="baixa os modelos que faltarem")
    args = parser.parse_args(argv)

    models = [name.strip() for name in args.modelos.split(",") if name.strip()]
    data_dir = default_data_dir()
    voice = load_config(default_config_dir() / CONFIG_FILE_NAME).voice

    try:
        if args.baixar:
            download_piper_voice(voice.piper_voice, data_dir)
            for model in models:
                download_whisper(model, data_dir)
        missing = [model for model in models if not whisper_downloaded(model, data_dir)]
        if missing:
            print(f"Faltam os modelos: {', '.join(missing)}. Use --baixar.", file=sys.stderr)
            return 2
        synthesizer = load_synthesizer(voice, data_dir, [])
    except (DownloadError, SetupError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2

    print(f"{platform.machine()}, {os.cpu_count()} núcleos, precisão {args.precisao}\n")
    clips, synthesis = synthesize_phrases(synthesizer)
    results = benchmark_models(
        models,
        lambda model: Transcriber(model, args.precisao, whisper_dir(data_dir)),
        clips,
        repetitions=args.repeticoes,
    )
    print(format_report(results, synthesis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
