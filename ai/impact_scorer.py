# -*- coding: utf-8 -*-
"""
Unified contextual impact scoring for captions and speech selection.
No fixed trigger word lists: scores come from vocal dynamics, timing, music,
narrative state, silence, numbers and local contrast.
"""
import math
import re
from typing import Dict, List, Optional

import numpy as np


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value)))


def _word_text(word_data: Dict) -> str:
    return str(word_data.get("word", "") or "").strip()


def normalize_text(text: str) -> str:
    text = str(text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


class ImpactScorer:
    def __init__(self, music_engine=None, narrative_engine=None, timeline_state=None):
        self.music_engine = music_engine
        self.narrative_engine = narrative_engine
        self.timeline = timeline_state
        self.avg_intensity = 0.5
        self.std_intensity = 0.0
        self.avg_duration = 0.28
        self.words: List[Dict] = []

    def analyze_words(self, words: List[Dict]) -> List[Dict]:
        if not words:
            self.words = []
            return []

        intensities = [float(w.get("intensity", 0.5) or 0.5) for w in words]
        durations = [
            max(0.05, float(w.get("end", w.get("start", 0.0) + 0.25)) - float(w.get("start", 0.0)))
            for w in words
        ]
        self.avg_intensity = float(np.mean(intensities)) if intensities else 0.5
        self.std_intensity = float(np.std(intensities)) if intensities else 0.0
        self.avg_duration = float(np.mean(durations)) if durations else 0.28

        scored = []
        total = len(words)
        for index, word in enumerate(words):
            scored.append(self.score_word(word, index, total, words))
        self.words = scored
        return scored

    def score_word(self, word_data: Dict, index: int, total: int, words: Optional[List[Dict]] = None) -> Dict:
        words = words or self.words
        text = normalize_text(_word_text(word_data))
        start = float(word_data.get("start", 0.0) or 0.0)
        end = float(word_data.get("end", start + 0.25) or (start + 0.25))
        duration = max(0.05, end - start)
        intensity = _clamp(word_data.get("intensity", 0.5), 0.0, 1.5)

        intensity_score = self._score_intensity(intensity)
        contrast_score = self._score_local_contrast(index, words, intensity)
        duration_score = self._score_duration(duration)
        position_score = self._score_position(index, total)
        musical_score = self._score_music(start)
        narrative_score = self._score_narrative(start)
        silence_score = self._score_silence(start, index, words)
        text_shape_score = self._score_text_shape(text)

        impact_score = (
            intensity_score * 0.23
            + contrast_score * 0.16
            + duration_score * 0.08
            + position_score * 0.08
            + musical_score * 0.20
            + narrative_score * 0.10
            + silence_score * 0.08
            + text_shape_score * 0.07
        )
        impact_score = _clamp(impact_score)

        moment_type = self._classify_moment(impact_score, musical_score, silence_score, text_shape_score)
        scored = {
            **word_data,
            "impact_score": impact_score,
            "viral_score": impact_score,
            "caption_score": impact_score,
            "is_viral": impact_score >= 0.58,
            "moment_type": moment_type,
            "caption_rank": self.rank_for_score(impact_score),
            "score_parts": {
                "intensity": intensity_score,
                "contrast": contrast_score,
                "duration": duration_score,
                "position": position_score,
                "music": musical_score,
                "narrative": narrative_score,
                "silence": silence_score,
                "text_shape": text_shape_score,
            },
        }
        return scored

    @staticmethod
    def rank_for_score(score: float) -> str:
        if score >= 0.74:
            return "dominant"
        if score >= 0.54:
            return "secondary"
        return "support"

    def _score_intensity(self, intensity: float) -> float:
        if self.std_intensity <= 1e-6:
            return _clamp(intensity)
        z_score = (intensity - self.avg_intensity) / self.std_intensity
        return _clamp(0.5 + z_score * 0.22)

    def _score_local_contrast(self, index: int, words: List[Dict], intensity: float) -> float:
        if not words:
            return 0.3
        start = max(0, index - 3)
        end = min(len(words), index + 4)
        neighbors = [float(w.get("intensity", 0.5) or 0.5) for w in words[start:end] if w is not words[index]]
        if not neighbors:
            return 0.3
        local_avg = float(np.mean(neighbors))
        return _clamp(abs(intensity - local_avg) * 1.8)

    def _score_duration(self, duration: float) -> float:
        if self.avg_duration <= 1e-6:
            return 0.3
        ratio = duration / self.avg_duration
        return _clamp(abs(math.log(max(ratio, 1e-3))) * 0.7 + 0.25)

    def _score_position(self, index: int, total: int) -> float:
        if total <= 1:
            return 0.5
        ratio = index / max(total - 1, 1)
        if ratio < 0.08:
            return 0.65
        if ratio > 0.78:
            return 0.75
        if 0.42 <= ratio <= 0.62:
            return 0.55
        return 0.32

    def _score_music(self, time_sec: float) -> float:
        if not self.music_engine:
            return 0.35
        score = _clamp(self.music_engine.get_tension_at(time_sec)) * 0.35
        if self.music_engine.is_impact_moment(time_sec, tolerance=0.12):
            score += 0.28
        if self.music_engine.is_climax(time_sec, tolerance=0.45):
            score += 0.25
        section = self.music_engine.get_section_at(time_sec)
        if section == "drop":
            score += 0.22
        elif section in ("hook", "chorus", "buildup"):
            score += 0.14
        return _clamp(score)

    def _score_narrative(self, time_sec: float) -> float:
        if self.timeline:
            phase_weights = {
                "intro": 0.3,
                "buildup": 0.62,
                "climax": 0.92,
                "sustain": 0.55,
                "release": 0.38,
                "outro": 0.45,
            }
            return phase_weights.get(getattr(self.timeline, "phase", "sustain"), 0.45)
        if self.narrative_engine:
            state = self.narrative_engine.get_narrative_state(time_sec)
            return _clamp(float(state.get("energy", 0.45)))
        return 0.35

    def _score_silence(self, time_sec: float, index: int, words: List[Dict]) -> float:
        score = 0.0
        if self.music_engine and self.music_engine.is_silence_zone(max(0.0, time_sec - 0.12)):
            score += 0.58
        if index > 0 and words:
            prev_end = float(words[index - 1].get("end", time_sec) or time_sec)
            gap = time_sec - prev_end
            if gap > 0.35:
                score += _clamp(gap / 1.2) * 0.55
        return _clamp(score)

    def _score_text_shape(self, text: str) -> float:
        if not text:
            return 0.0
        score = 0.15
        if any(ch.isdigit() for ch in text):
            score += 0.35
        if len(text) <= 3:
            score += 0.16
        elif len(text) >= 9:
            score += 0.18
        if "!" in text or "?" in text:
            score += 0.20
        return _clamp(score)

    @staticmethod
    def _classify_moment(impact_score: float, musical_score: float, silence_score: float, text_shape_score: float) -> str:
        if silence_score > 0.55:
            return "silence_reveal"
        if musical_score > 0.72:
            return "music_peak"
        if text_shape_score > 0.62:
            return "semantic_impact"
        if impact_score > 0.72:
            return "emotional_peak"
        return "normal"
