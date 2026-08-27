# -*- coding: utf-8 -*-
"""
Music Engine V4.
Detects rhythmic events, repeated hooks, drops, buildup/release and silence
zones without relying only on the loudest RMS peak.
"""
from typing import Dict, List, Tuple

import librosa
import numpy as np

from logger import log


def _safe_norm(values):
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values
    min_v = float(np.min(values))
    max_v = float(np.max(values))
    if max_v - min_v < 1e-9:
        return np.zeros_like(values)
    return (values - min_v) / (max_v - min_v)


def _smooth(values, size=7):
    values = np.asarray(values, dtype=float)
    if values.size < 3:
        return values
    size = max(3, int(size))
    kernel = np.ones(size) / size
    return np.convolve(values, kernel, mode="same")


class MusicEngine:
    def __init__(
        self,
        audio_path: str,
        target_duration: float = 30.0,
        vocal_path: str = None,
        instrumental_path: str = None,
    ):
        self.audio_path = audio_path
        self.vocal_path = vocal_path
        self.instrumental_path = instrumental_path
        self.target_duration = float(target_duration or 30.0)
        self.sr = 22050
        self.hop_length = 512
        self.frame_time = self.hop_length / self.sr

        max_duration = max(self.target_duration * 5.0, self.target_duration + 20.0)
        self.y, self.sr = librosa.load(audio_path, sr=self.sr, mono=True, duration=max_duration)
        self.duration = len(self.y) / self.sr if self.sr else 0.0

        self.times = np.array([])
        self.rms = np.array([])
        self.rms_smooth = np.array([])
        self.onset_strength = np.array([])
        self.spectral_centroid = np.array([])
        self.chroma = np.array([])
        self.mfcc = np.array([])
        self.repetition_curve = np.array([])
        self.band_curves: Dict[str, np.ndarray] = {}
        self.tension_curve = np.array([])
        self.sections: List[Dict] = []
        self.emotion_map: List[Dict] = []
        self.climax_zones: List[Tuple[float, float]] = []
        self.impact_moments: List[float] = []
        self.beat_events: List[Dict] = []
        self.silence_zones: List[Tuple[float, float]] = []
        self.best_segment: Tuple[float, float] = (0.0, min(self.duration, self.target_duration))

        self._analyze()

    def _analyze(self):
        log("MUSIC", "Extraindo features musicais")
        self._extract_features()
        log("MUSIC", "Detectando repeticao, hooks e silencio")
        self._detect_repetition()
        self._detect_silence_zones()
        log("MUSIC", "Construindo curva de tensao")
        self._build_tension_curve()
        log("MUSIC", "Classificando eventos ritmicos")
        self._find_impact_moments()
        log("MUSIC", "Mapeando estrutura musical")
        self._detect_structure()
        self._build_emotion_map()
        self._find_climax_zones()
        self._select_best_segment()
        log("MUSIC", f"{len(self.sections)} secoes | {len(self.impact_moments)} impactos | melhor {self.best_segment[0]:.1f}-{self.best_segment[1]:.1f}s")

    def _extract_features(self):
        if len(self.y) == 0: return
        self.rms = librosa.feature.rms(y=self.y, hop_length=self.hop_length)[0]
        self.rms_smooth = _smooth(self.rms, 9)
        self.times = librosa.frames_to_time(np.arange(len(self.rms)), sr=self.sr, hop_length=self.hop_length)
        self.onset_strength = librosa.onset.onset_strength(y=self.y, sr=self.sr, hop_length=self.hop_length)
        self.spectral_centroid = librosa.feature.spectral_centroid(y=self.y, sr=self.sr, hop_length=self.hop_length)[0][:len(self.rms)]
        self.chroma = librosa.feature.chroma_stft(y=self.y, sr=self.sr, hop_length=self.hop_length)
        self.mfcc = librosa.feature.mfcc(y=self.y, sr=self.sr, hop_length=self.hop_length, n_mfcc=8)
        self.band_curves = self._extract_band_curves()

    def _extract_band_curves(self):
        spec = np.abs(librosa.stft(self.y, n_fft=1024, hop_length=self.hop_length))
        freqs = librosa.fft_frequencies(sr=self.sr, n_fft=1024)
        bands = {"low": (35, 160), "mid": (160, 1200), "high": (1200, 5200)}
        curves = {}
        for name, (low, high) in bands.items():
            mask = (freqs >= low) & (freqs <= high)
            value = np.mean(spec[mask], axis=0) if np.any(mask) else np.zeros(spec.shape[1])
            curves[name] = _smooth(_safe_norm(value[:len(self.rms)]), 5)
        return curves

    def _detect_repetition(self):
        if self.chroma.size == 0:
            self.repetition_curve = np.zeros_like(self.rms_smooth)
            return
        fps = max(1, int(round(self.sr / self.hop_length)))
        blocks = []
        for start in range(0, self.chroma.shape[1], fps):
            block = self.chroma[:, start:start+fps]
            if block.size: blocks.append(np.mean(block, axis=1))
        if len(blocks) < 3:
            self.repetition_curve = np.zeros_like(self.rms_smooth)
            return
        matrix = np.stack(blocks, axis=1)
        matrix = matrix / (np.linalg.norm(matrix, axis=0, keepdims=True) + 1e-9)
        similarity = np.dot(matrix.T, matrix)
        np.fill_diagonal(similarity, 0.0)
        rep_seconds = _safe_norm(np.mean(similarity, axis=1))
        second_times = np.arange(len(rep_seconds), dtype=float)
        self.repetition_curve = np.interp(self.times, second_times, rep_seconds, left=0.0, right=0.0)
        self.repetition_curve = _smooth(self.repetition_curve, 13)

    def _detect_silence_zones(self):
        source = self.vocal_path if self.vocal_path else self.audio_path
        try:
            y, sr = librosa.load(source, sr=self.sr, mono=True, duration=max(self.duration, 1.0))
            rms = librosa.feature.rms(y=y, hop_length=self.hop_length)[0]
            rms_norm = _safe_norm(_smooth(rms, 7))
            times = librosa.frames_to_time(np.arange(len(rms_norm)), sr=sr, hop_length=self.hop_length)
        except Exception:
            rms_norm = _safe_norm(self.rms_smooth)
            times = self.times
        if len(rms_norm) == 0: return
        threshold = max(0.08, float(np.percentile(rms_norm, 18)))
        in_zone, zone_start = False, 0.0
        for idx, value in enumerate(rms_norm):
            t = float(times[idx])
            if value <= threshold and not in_zone:
                in_zone, zone_start = True, t
            elif value > threshold * 1.6 and in_zone:
                if t - zone_start >= 0.25: self.silence_zones.append((zone_start, t))
                in_zone = False
        if in_zone and len(times):
            end = float(times[-1])
            if end - zone_start >= 0.25: self.silence_zones.append((zone_start, end))

    def _build_tension_curve(self):
        if len(self.rms_smooth) == 0: self.tension_curve = np.zeros(1); return
        rms_norm = _safe_norm(self.rms_smooth)
        onset = _safe_norm(_smooth(self.onset_strength[:len(rms_norm)], 5))
        centroid = _safe_norm(_smooth(self.spectral_centroid[:len(rms_norm)], 9))
        low = self.band_curves.get("low", np.zeros_like(rms_norm))[:len(rms_norm)]
        high = self.band_curves.get("high", np.zeros_like(rms_norm))[:len(rms_norm)]
        rep = self.repetition_curve[:len(rms_norm)] if len(self.repetition_curve) else np.zeros_like(rms_norm)
        self.tension_curve = np.clip(rms_norm*0.34 + onset*0.22 + centroid*0.10 + low*0.12 + high*0.08 + rep*0.14, 0.0, 1.0)
        for start, end in self.silence_zones:
            mask = (self.times >= start) & (self.times <= end)
            self.tension_curve[mask] *= 0.35

    def _find_impact_moments(self):
        if len(self.onset_strength) == 0: return
        onset = _safe_norm(self.onset_strength)
        threshold = max(0.45, float(np.percentile(onset, 78)))
        candidates = librosa.util.localmax(onset) & (onset >= threshold)
        times = librosa.frames_to_time(np.flatnonzero(candidates), sr=self.sr, hop_length=self.hop_length)
        mean_strength = float(np.mean(onset[candidates])) if np.any(candidates) else 1.0
        for t in times:
            idx = min(int(t/self.frame_time), len(onset)-1)
            strength = float(onset[idx]/(mean_strength+1e-9))
            self.impact_moments.append(float(t))
            self.beat_events.append({"time": float(t), "type": self._classify_event(float(t), strength), "strength": max(0.25, min(1.5, strength))})
        self.beat_events.sort(key=lambda x: x["time"])

    def _classify_event(self, time_sec, strength):
        start, end = max(0, int((time_sec-0.045)*self.sr)), min(len(self.y), int((time_sec+0.095)*self.sr))
        sample = self.y[start:end]
        if len(sample) < 128: return "kick"
        spectrum = np.abs(np.fft.rfft(sample*np.hanning(len(sample))))
        freqs = np.fft.rfftfreq(len(sample), d=1/self.sr)
        total = float(np.sum(spectrum)+1e-9)
        low = float(np.sum(spectrum[(freqs>=35)&(freqs<=160)]))/total
        mid = float(np.sum(spectrum[(freqs>160)&(freqs<=1200)]))/total
        high = float(np.sum(spectrum[(freqs>1200)&(freqs<=5200)]))/total
        if low > 0.42 and strength >= 0.75: return "kick"
        if high > 0.34 and strength >= 0.55: return "snare"
        if low > 0.31: return "bass"
        if mid > 0.46: return "vocal_peak"
        return "kick" if strength >= 0.9 else "bass"

    def _detect_structure(self):
        if len(self.tension_curve) == 0: self.sections = [{"start": 0.0, "end": self.duration, "type": "sustain"}]; return
        frame_types = []
        energy = _safe_norm(self.rms_smooth)
        onset = _safe_norm(self.onset_strength[:len(energy)])
        rep = self.repetition_curve[:len(energy)] if len(self.repetition_curve) else np.zeros_like(energy)
        rising = np.gradient(_smooth(energy, 15)) if len(energy) else np.zeros_like(energy)
        for idx, t in enumerate(self.times):
            if self.is_silence_zone(float(t)): frame_types.append("break")
            elif rep[idx] > 0.62 and self.tension_curve[idx] > 0.52: frame_types.append("hook")
            elif self.tension_curve[idx] > 0.70 and onset[idx] > 0.52: frame_types.append("drop")
            elif rising[idx] > 0.012 and self.tension_curve[idx] > 0.42: frame_types.append("buildup")
            elif self.tension_curve[idx] > 0.58: frame_types.append("chorus")
            else: frame_types.append("verse")
        self.sections = self._merge_frame_types(frame_types)

    def _merge_frame_types(self, frame_types):
        if not frame_types: return [{"start": 0.0, "end": self.duration, "type": "sustain"}]
        sections, current, start = [], frame_types[0], 0.0
        for idx, st in enumerate(frame_types[1:], start=1):
            if st == current: continue
            end = float(self.times[idx])
            if end - start < 0.45 and sections: sections[-1]["end"] = end
            else: sections.append({"start": start, "end": end, "type": current})
            start, current = end, st
        sections.append({"start": start, "end": self.duration, "type": current})
        return sections

    def _build_emotion_map(self):
        self.emotion_map = []
        for idx, t in enumerate(self.times):
            section = self.get_section_at(float(t))
            tension = self.tension_curve[idx] if idx < len(self.tension_curve) else 0.5
            if section == "drop": emotion = "explosive"
            elif section == "hook": emotion = "peak_action"
            elif section == "buildup": emotion = "anticipation"
            elif section == "break": emotion = "silence_tension"
            elif tension > 0.72: emotion = "aggressive"
            elif tension < 0.25: emotion = "calm"
            else: emotion = "energetic"
            self.emotion_map.append({"time": float(t), "emotion": emotion, "intensity": float(tension), "tension": float(tension), "section": section})

    def _find_climax_zones(self):
        if len(self.tension_curve) < 3: return
        threshold = max(0.62, float(np.percentile(self.tension_curve, 82)))
        in_zone, start = False, 0.0
        for idx, value in enumerate(self.tension_curve):
            t = float(self.times[idx])
            is_peak = value >= threshold or self.get_section_at(t) in ("drop", "hook")
            if is_peak and not in_zone: start, in_zone = t, True
            elif not is_peak and in_zone:
                if t - start >= 0.65: self.climax_zones.append((start, t))
                in_zone = False
        if in_zone and len(self.times):
            end = float(self.times[-1])
            if end - start >= 0.65: self.climax_zones.append((start, end))

    def _select_best_segment(self):
        if self.duration <= self.target_duration: self.best_segment = (0.0, self.duration); return
        step, window = 0.5, min(self.target_duration, self.duration)
        best_start, best_score = 0.0, -1.0
        current = 0.0
        while current + window <= self.duration + 1e-6:
            score = self._score_window(current, window)
            if score > best_score: best_score, best_start = score, current
            current += step
        self.best_segment = (float(best_start), float(best_start+window))

    def _score_window(self, start, duration):
        end = start + duration
        mask = (self.times >= start) & (self.times <= end)
        if not np.any(mask): return 0.0
        tension = self.tension_curve[mask]
        rep = self.repetition_curve[mask] if len(self.repetition_curve) else np.zeros_like(tension)
        sections = [s for s in self.sections if s["start"] < end and s["end"] > start]
        hook_drop = sum(max(0.0, min(end, s["end"]) - max(start, s["start"])) for s in sections if s["type"] in ("hook", "drop", "chorus")) / max(duration, 1e-6)
        impacts = [m for m in self.impact_moments if start <= m <= end]
        impact_density = min(1.0, len(impacts) / max(duration*2.0, 1.0))
        silence_bonus = 0.0
        for ss, se in self.silence_zones:
            if start <= se <= end:
                after = min(se + 0.5, self.duration)
                if self.get_section_at(after) in ("drop", "hook", "chorus"):
                    silence_bonus = 0.18
                    break
        return float(np.mean(tension)*0.30 + np.max(tension)*0.14 + np.mean(rep)*0.24 + hook_drop*0.22 + impact_density*0.07 + silence_bonus)

    def get_sections(self): return self.sections
    def get_tension_at(self, time_sec):
        if len(self.tension_curve) == 0: return 0.5
        idx = min(max(0, int(float(time_sec)/self.frame_time)), len(self.tension_curve)-1)
        return float(self.tension_curve[idx])
    def get_emotion_at(self, time_sec):
        if not self.emotion_map: return {"emotion": "neutral", "intensity": 0.5, "tension": 0.5, "section": "sustain"}
        idx = min(max(0, int(float(time_sec)/self.frame_time)), len(self.emotion_map)-1)
        return self.emotion_map[idx]
    def get_section_at(self, time_sec):
        for s in self.sections:
            if s["start"] <= time_sec < s["end"]: return s["type"]
        return self.sections[-1]["type"] if self.sections else "sustain"
    def is_climax(self, time_sec, tolerance=0.3): return any(start-tolerance <= time_sec <= end+tolerance for start, end in self.climax_zones)
    def is_impact_moment(self, time_sec, tolerance=0.1): return any(abs(float(time_sec)-m) <= tolerance for m in self.impact_moments)
    def is_silence_zone(self, time_sec): return any(start <= float(time_sec) <= end for start, end in self.silence_zones)
    def get_tension_curve(self): return self.tension_curve if len(self.tension_curve) else np.zeros(1)
    def get_emotion_map(self): return self.emotion_map
    def get_impact_moments(self): return self.impact_moments
    def get_beat_events(self, start_offset=0.0, duration=None):
        duration = float(duration if duration is not None else self.duration)
        events = []
        for e in self.beat_events:
            rel = float(e["time"]) - float(start_offset)
            if 0.0 <= rel <= duration + 0.2: events.append({**e, "time": rel})
        if len(events) < 5:
            count = max(8, int(duration/0.45))
            events = [{"time": i*duration/max(count,1), "type": "kick", "strength": 0.75} for i in range(count)]
        return events
    def get_best_segment(self): return self.best_segment
