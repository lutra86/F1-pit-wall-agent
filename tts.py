"""TTS router: chirp (Google AU bloke) -> kokoro (local) -> edge (fallback).

TTS_BACKEND env picks primary: chirp | kokoro | edge. Failures fall down
the chain automatically. Every backend prints time-to-first-audio.

Google Chirp needs credentials (service account JSON, billing enabled):
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcp-key.json
"""
import os
import subprocess
import time

TTS_BACKEND = os.getenv("TTS_BACKEND", "chirp")
CHIRP_VOICE = os.getenv("CHIRP_VOICE", "en-AU-Chirp-HD-D")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "bm_george")  # closest male, UK
EDGE_VOICE = os.getenv("TTS_VOICE", "en-AU-WilliamMultilingualNeural")

_koko = None


def _play_pcm(samples, rate):
    import sounddevice as sd
    import numpy as np
    sd.play(np.asarray(samples, dtype="float32"), rate)
    sd.wait()


KOKORO_MODEL_FILE = os.getenv("KOKORO_MODEL", "model_q4f16.onnx")


def _ensure_kokoro_files(kd):
    """Download q4 model + bm_george voice on first run (~160MB total)."""
    from pathlib import Path
    model = kd / "onnx" / KOKORO_MODEL_FILE
    voice = kd / "voices" / "bm_george.bin"
    npz = kd / "voices.npz"
    if model.exists() and voice.exists() and npz.exists():
        return
    print("[tts] downloading kokoro files (once)…", flush=True)
    from huggingface_hub import hf_hub_download
    hf_hub_download("onnx-community/Kokoro-82M-v1.0-ONNX",
                    "onnx/" + KOKORO_MODEL_FILE, local_dir=str(kd))
    hf_hub_download("onnx-community/Kokoro-82M-v1.0-ONNX",
                    "voices/bm_george.bin", local_dir=str(kd))
    hf_hub_download("onnx-community/Kokoro-82M-v1.0-ONNX",
                    "voices/bm_george.bin", local_dir=str(kd))
    import numpy as np
    raw = np.fromfile(voice, dtype=np.float32)
    np.savez(kd / "voices.npz", bm_george=raw.reshape(510, 1, 256))


def _koko_init():
    """Load q4 model + bm_george voice."""
    global _koko
    if _koko is not None:
        return _koko
    print("[tts] loading kokoro-82m q4 (local)…", flush=True)
    from pathlib import Path
    import numpy as np
    from kokoro_onnx import Kokoro
    kd = Path(__file__).parent / "assets" / "kokoro"
    _ensure_kokoro_files(kd)
    ko = Kokoro(str(kd / "onnx" / KOKORO_MODEL_FILE),
                str(kd / "voices.npz"))
    raw = np.fromfile(kd / "voices" / "bm_george.bin", dtype=np.float32)
    voice = raw.reshape(510, 1, 256)
    _koko = (ko, voice)
    return _koko


def preload_kokoro():
    try:
        _koko_init()
    except Exception as e:
        print(f"[tts] kokoro preload failed: {str(e)[:100]}", flush=True)


def speak_kokoro(text: str):
    """Local Kokoro-82M ONNX. Offline after first download."""
    import time
    import numpy as np
    t0 = time.time()
    ko, voice = _koko_init()
    phonemes = ko.tokenizer.phonemize(text, "en-gb")
    parts = ko._split_phonemes(phonemes)
    from kokoro_onnx import trim_audio
    out = []
    for ph in parts:
        tokens = np.array(ko.tokenizer.tokenize(ph), dtype=np.int64)
        style = np.array(voice[len(tokens)], dtype=np.float32)
        inputs = {"input_ids": np.array([[0, *tokens, 0]], dtype=np.int64),
                  "style": style,
                  "speed": np.array([1.0], dtype=np.float32)}
        audio = ko.sess.run(None, inputs)[0]
        audio, _ = trim_audio(audio)
        out.append(np.asarray(audio).ravel())
    samples = np.concatenate(out).astype(np.float32)
    rate = 24000
    print(f"[tts] kokoro synth took {time.time()-t0:.2f}s "
          f"for {len(samples)/rate:.1f}s audio", flush=True)
    _play_pcm(samples, rate)
    return "kokoro"


def speak_chirp(text: str):
    """Google Chirp 3 HD, streaming straight into ffplay."""
    from google.cloud import texttospeech
    t0 = time.time()
    client = texttospeech.TextToSpeechClient()
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-AU", name=CHIRP_VOICE)
    stream_cfg = texttospeech.StreamingSynthesizeConfig(
        voice=voice,
        streaming_audio_config=texttospeech.StreamingAudioConfig(
            audio_encoding=texttospeech.AudioEncoding.OGG_OPUS))
    first = True

    def requests():
        yield texttospeech.StreamingSynthesizeRequest(
            streaming_config=stream_cfg)
        yield texttospeech.StreamingSynthesizeRequest(
            input=texttospeech.StreamingSynthesisInput(text=text))

    proc = subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
         "-i", "pipe:0"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    for resp in client.streaming_synthesize(requests()):
        if resp.audio_content:
            if first:
                print(f"[tts] chirp first audio after {time.time()-t0:.1f}s",
                      flush=True)
                first = False
            proc.stdin.write(resp.audio_content)
    proc.stdin.close()
    proc.wait()
    return "chirp"


async def _edge_stream(text: str):
    import edge_tts
    comm = edge_tts.Communicate(text, EDGE_VOICE)
    proc = subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
         "-i", "pipe:0"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    t0 = time.time()
    first = True
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            if first:
                print(f"[tts] edge first audio after {time.time()-t0:.1f}s",
                      flush=True)
                first = False
            proc.stdin.write(chunk["data"])
    proc.stdin.close()
    proc.wait()


def speak_edge(text: str):
    import asyncio
    asyncio.run(_edge_stream(text))
    return "edge"


def speak_text(text: str) -> str:
    """Speak via primary backend, falling down the chain. Returns backend."""
    order = {"chirp": ["chirp", "kokoro", "edge"],
             "kokoro": ["kokoro", "edge"],
             "edge": ["edge"]}.get(TTS_BACKEND, ["chirp", "kokoro", "edge"])
    fns = {"chirp": speak_chirp, "kokoro": speak_kokoro, "edge": speak_edge}
    last = None
    for name in order:
        try:
            return fns[name](text)
        except Exception as e:
            print(f"[tts] {name} failed ({str(e)[:120]}), falling back…",
                  flush=True)
            last = e
    print("[tts] all online/local voices failed, offline Mac voice…",
          flush=True)
    subprocess.run(["say", text], capture_output=True)
    return "say"


if __name__ == "__main__":
    import sys
    sample = sys.argv[1] if len(sys.argv) > 1 else \
        "Copy, mate. Voice check, send it."
    only = sys.argv[2] if len(sys.argv) > 2 else None
    for name in ([only] if only else ["kokoro", "chirp", "edge"]):
        try:
            t0 = time.time()
            used = {"kokoro": speak_kokoro, "chirp": speak_chirp,
                    "edge": speak_edge}[name](sample)
            print(f"{used}: total {time.time()-t0:.1f}s")
        except Exception as e:
            print(f"{name} FAILED: {str(e)[:200]}")
