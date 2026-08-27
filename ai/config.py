# -*- coding: utf-8 -*-
import math, os, tempfile

TEMP_ROOT = os.environ.get("CRIATOR_TEMP_ROOT", os.path.join(tempfile.gettempdir(), "criator"))
CACHE_DIR = os.environ.get("CRIATOR_CACHE_DIR", os.path.join(TEMP_ROOT, "cache"))
FFMPEG_BIN = os.environ.get("CRIATOR_FFMPEG", "ffmpeg")
FFPROBE_BIN = os.environ.get("CRIATOR_FFPROBE", "ffprobe")

WHISPER_MODEL = os.environ.get("CRIATOR_WHISPER_MODEL", "medium")
WHISPER_LANGUAGE = os.environ.get("CRIATOR_WHISPER_LANGUAGE", "pt")
WHISPER_OFFSET = float(os.environ.get("CRIATOR_WHISPER_OFFSET", "0.12"))
TRANSCRIPTION_CACHE_TTL_DAYS = int(os.environ.get("CRIATOR_TRANSCRIPTION_CACHE_TTL_DAYS", "7"))

DEMUCS_REQUIRED = os.environ.get("CRIATOR_DEMUCS_REQUIRED", "0").lower() in ("1", "true", "yes", "sim")
DEMUCS_MODEL = os.environ.get("CRIATOR_DEMUCS_MODEL", "htdemucs")
ENABLE_STEMS = os.environ.get("CRIATOR_ENABLE_STEMS", "0").lower() in ("1", "true", "yes", "sim")
ENABLE_DEEP_VISION = os.environ.get("CRIATOR_ENABLE_DEEP_VISION", "0").lower() in ("1", "true", "yes", "sim")

MIN_DURATION = 3
DEFAULT_DURATION = 30
DEFAULT_FPS = 60
PROCESS_TIMEOUT_SECONDS = int(os.environ.get("CRIATOR_PROCESS_TIMEOUT", "2700"))
ENABLE_SHAKE = os.environ.get("CRIATOR_ENABLE_SHAKE", "0").lower() in ("1", "true", "yes", "sim")
CAPTION_PRESET = os.environ.get("CRIATOR_CAPTION_PRESET", "reels")

ASS_FONT_CANDIDATES = [os.environ.get("CRIATOR_ASS_FONT", "Montserrat"), "Montserrat SemiBold", "Segoe UI Black", "Segoe UI", "Arial"]
ASS_STYLE = {"font_size_ratio": 0.092, "outline": 5, "shadow": 2, "y_position_ratio": 0.72, "alignment": 5, "primary_color": "&H00FFFFFF", "secondary_color": "&H0000FFFF", "outline_color": "&H00000000", "shadow_color": "&H88000000"}

MODE_ALIASES = {"": "legendado", "legenda": "legendado", "legendado": "legendado", "caption": "legendado", "captions": "legendado", "motivacional": "legendado", "cinematico": "legendado", "cinematic": "legendado", "phonk": "ritmico", "ritmico": "ritmico", "ritmo": "ritmico", "gameplay": "ritmico", "music": "ritmico", "musica": "ritmico"}

PRESETS = {
    "legendado": {"name": "Legenda", "subtitles": True, "uses_speech_segment": True, "max_duration": 180, "fps_min": 24, "fps_max": 60, "cut_density": 0.72, "min_cut": 0.42, "max_cut": 1.55, "zoom": 0.45, "flash": 0.25, "shake": False, "shake_threshold": 9.0, "speed": 0.35, "contrast": 1.08, "saturation": 1.12, "brightness": 0.01, "deep_visual_top": 5, "yolo_top": 15},
    "ritmico": {"name": "Phonk", "subtitles": False, "uses_speech_segment": False, "max_duration": 180, "fps_min": 24, "fps_max": 60, "cut_density": 0.92, "min_cut": 0.28, "max_cut": 1.15, "zoom": 0.62, "flash": 0.38, "shake": ENABLE_SHAKE, "shake_threshold": 0.86, "speed": 0.48, "contrast": 1.12, "saturation": 1.22, "brightness": 0.015, "deep_visual_top": 4, "yolo_top": 18},
}

EFFECT_FATIGUE = {"flash": 1.5, "shake": 2.0, "speed_ramp": 2.5, "zoom": 1.8, "glow": 1.2}
MAX_REPETITION_PENALTY = 0.85

def clamp(value, min_val, max_val): return max(min_val, min(max_val, value))
def normalize_mode(mode): return MODE_ALIASES.get(str(mode or "").strip().lower(), "legendado")
def get_mode_config(mode):
    normalized = normalize_mode(mode)
    return dict(PRESETS[normalized], mode=normalized)
def adaptive_scene_pool(duration): return int(clamp(math.ceil(float(duration) * 0.75), 12, 40))
def adaptive_chunk_size(clip_count):
    clip_count = max(1, int(clip_count))
    target_chunks = int(clamp(math.ceil(clip_count / 10), 4, 8))
    return max(1, int(math.ceil(clip_count / target_chunks)))
def ensure_runtime_dirs():
    os.makedirs(TEMP_ROOT, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
