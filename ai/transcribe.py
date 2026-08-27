# -*- coding: utf-8 -*-
"""
Whisper transcription with CUDA detection, automatic language and temp cache.
"""
import gc
import hashlib
import json
import os
import subprocess
import time
from typing import Dict, List

import numpy as np

from config import (
    CACHE_DIR,
    FFMPEG_BIN,
    TRANSCRIPTION_CACHE_TTL_DAYS,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
    ensure_runtime_dirs,
)
from logger import log

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER = True
except ImportError:
    FASTER_WHISPER = False


def _cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        try:
            import torch
            return bool(torch.cuda.is_available())
        except Exception:
            return False


def _file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = os.stat(path)
    digest.update(str(stat.st_size).encode("utf-8"))
    return digest.hexdigest()


def _cache_path(audio_path: str, model_name: str, language: str) -> str:
    ensure_runtime_dirs()
    key = hashlib.sha256(f"{_file_hash(audio_path)}|{model_name}|{language}|v4".encode("utf-8")).hexdigest()
    path = os.path.join(CACHE_DIR, "transcriptions")
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, f"{key}.json")


def _load_cache(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return None
    max_age = TRANSCRIPTION_CACHE_TTL_DAYS * 24 * 3600
    if time.time() - os.path.getmtime(path) > max_age:
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    log("WHISPER", f"Cache encontrado: {len(payload.get('words', []))} palavras")
    return payload.get("words", [])


def _save_cache(path: str, words: List[Dict]):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"created_at": time.time(), "words": words}, handle, ensure_ascii=False)
    except OSError as exc:
        log("WHISPER", f"Nao foi possivel salvar cache: {exc}")


def _convert_audio(audio_path: str, wav_path: str) -> None:
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        audio_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        wav_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio convert failed:\n{(result.stderr or result.stdout)[-3000:]}")


def _temp_wav(audio_path: str, workdir: str = None) -> str:
    workdir = workdir or os.path.dirname(audio_path) or "."
    base = os.path.splitext(os.path.basename(audio_path))[0]
    return os.path.abspath(os.path.join(workdir, f"{base}_whisper_16k.wav"))


def _merge_punctuation(words: List[Dict]) -> List[Dict]:
    punctuation = {".", ",", "!", "?", ";", ":", ")", "]", "}", '"', "'"}
    merged = []
    for word in words:
        text = str(word.get("word", "")).strip()
        if not text:
            continue
        if len(text) == 1 and text in punctuation and merged:
            merged[-1]["word"] += text
            merged[-1]["end"] = max(merged[-1]["end"], word.get("end", merged[-1]["end"]))
            continue
        while text and text[0] in punctuation and len(text) > 1 and merged:
            merged[-1]["word"] += text[0]
            text = text[1:]
        if text:
            word["word"] = text
            merged.append(word)
    return merged


def _remove_hallucinations(words: List[Dict], confidence_threshold: float = 0.35) -> List[Dict]:
    filtered = []
    for word in words:
        text = str(word.get("word", "")).strip()
        confidence = float(word.get("confidence", 0.85) or 0.85)
        if not text:
            continue
        if len(text) <= 1 and confidence < 0.55:
            continue
        if confidence < confidence_threshold:
            continue
        filtered.append(word)
    removed = len(words) - len(filtered)
    if removed:
        log("WHISPER", f"Removidas {removed} palavras de baixa confianca")
    return filtered


def _analyze_intensity(wav_path: str, words: List[Dict]) -> List[Dict]:
    try:
        import librosa
        y, sr = librosa.load(wav_path, sr=16000)
        hop_length = 80
        energy = librosa.feature.rms(y=y, frame_length=160, hop_length=hop_length)[0]
        if len(energy) and float(np.max(energy)) > 0:
            energy = energy / np.max(energy)
        for word in words:
            start_idx = int(float(word["start"]) * sr / hop_length)
            end_idx = int(float(word["end"]) * sr / hop_length)
            start_idx = max(0, min(start_idx, max(0, len(energy) - 1)))
            end_idx = max(start_idx + 1, min(end_idx, len(energy)))
            if end_idx > start_idx and len(energy):
                chunk = energy[start_idx:end_idx]
                word_energy = float(np.mean(chunk) * 0.6 + np.max(chunk) * 0.4)
                word["intensity"] = float(np.clip(word_energy * 1.8, 0.2, 1.0))
            else:
                word["intensity"] = 0.5
    except Exception as exc:
        log("INTENSITY", f"Falhou: {exc}")
        for word in words:
            word["intensity"] = 0.5
    return words


def _detect_phonetic_onset(wav_path: str, word_start: float, word_end: float) -> float:
    try:
        import librosa
        offset = max(0.0, float(word_start) - 0.12)
        duration = min(0.32, max(0.12, float(word_end) - float(word_start) + 0.12))
        y, sr = librosa.load(wav_path, sr=16000, offset=offset, duration=duration)
        if len(y) < 100:
            return word_start
        hop_length = 80
        energy = librosa.feature.rms(y=y, frame_length=160, hop_length=hop_length)[0]
        if len(energy) == 0 or np.max(energy) <= 0:
            return word_start
        energy = energy / np.max(energy)
        onset_frame = 0
        for idx, value in enumerate(energy):
            if value > 0.15:
                onset_frame = idx
                break
        onset_time = offset + onset_frame * hop_length / sr
        return max(float(word_start), float(onset_time))
    except Exception:
        return word_start


def _post_process(words: List[Dict], wav_path: str) -> List[Dict]:
    words = _merge_punctuation(words)
    words = _remove_hallucinations(words)
    words = _analyze_intensity(wav_path, words)
    for word in words:
        start = _detect_phonetic_onset(wav_path, float(word["start"]), float(word["end"]))
        word["start"] = max(0.0, start)
        word["end"] = max(word["start"] + 0.05, float(word.get("end", word["start"] + 0.3)))
    return words


def _transcribe_faster(wav_path: str, model_name: str, language: str) -> List[Dict]:
    device = "cuda" if _cuda_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    log("WHISPER", f"Carregando faster-whisper {model_name} em {device}")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    language_arg = None if language == "auto" else language
    segments, info = model.transcribe(
        wav_path,
        language=language_arg,
        beam_size=5,
        best_of=5,
        vad_filter=False,
        word_timestamps=True,
        without_timestamps=False,
        condition_on_previous_text=False,
        no_speech_threshold=0.4,
    )
    detected = getattr(info, "language", None)
    if detected:
        log("WHISPER", f"Idioma detectado: {detected}")

    words = []
    for segment in segments:
        if getattr(segment, "words", None):
            for item in segment.words:
                words.append({
                    "word": str(item.word or "").strip(),
                    "start": float(item.start or 0.0),
                    "end": float(item.end or 0.0),
                    "confidence": float(getattr(item, "probability", 0.85) or 0.85),
                    "intensity": 0.5,
                })
        elif str(segment.text or "").strip():
            words.append({
                "word": segment.text.strip(),
                "start": float(segment.start or 0.0),
                "end": float(segment.end or 0.0),
                "confidence": 0.75,
                "intensity": 0.5,
            })

    del model
    gc.collect()
    if device == "cuda":
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
    return words


def _transcribe_openai_whisper(wav_path: str, model_name: str, language: str) -> List[Dict]:
    try:
        import whisper
        import torch
    except ImportError as exc:
        raise RuntimeError("faster-whisper falhou e openai-whisper nao esta instalado.") from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log("WHISPER", f"Carregando whisper {model_name} em {device} (fallback)")
    model = whisper.load_model(model_name, device=device)
    result = model.transcribe(
        wav_path,
        word_timestamps=True,
        language=None if language == "auto" else language,
        fp16=(device == "cuda"),
        without_timestamps=False,
        no_speech_threshold=0.4,
    )
    words = []
    for segment in result.get("segments", []):
        for item in segment.get("words", []):
            words.append({
                "word": str(item.get("word", "")).strip(),
                "start": float(item.get("start", 0.0) or 0.0),
                "end": float(item.get("end", 0.0) or 0.0),
                "confidence": float(item.get("probability", item.get("confidence", 0.85)) or 0.85),
                "intensity": 0.5,
            })
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return words


def transcribe_audio(audio_path: str, workdir: str = None, model_name: str = None, language: str = None) -> List[Dict]:
    model_name = model_name or WHISPER_MODEL
    language = language or WHISPER_LANGUAGE
    cache = _cache_path(audio_path, model_name, language)
    cached = _load_cache(cache)
    if cached is not None:
        return cached

    wav_path = _temp_wav(audio_path, workdir)
    _convert_audio(audio_path, wav_path)
    try:
        if FASTER_WHISPER:
            try:
                words = _transcribe_faster(wav_path, model_name, language)
            except Exception as exc:
                log("WHISPER", f"faster-whisper falhou: {exc}")
                words = _transcribe_openai_whisper(wav_path, model_name, language)
        else:
            words = _transcribe_openai_whisper(wav_path, model_name, language)
        words = _post_process(words, wav_path)
        _save_cache(cache, words)
        log("WHISPER", f"Transcrito: {len(words)} palavras")
        return words
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
