# -*- coding: utf-8 -*-
"""
Viral Moment Engine.
Uses the shared contextual ImpactScorer instead of fixed trigger word lists.
"""
from typing import Dict, List, Optional, Tuple

import numpy as np

from impact_scorer import ImpactScorer
from logger import log


class ViralMomentEngine:
    def __init__(self, music_engine=None, narrative_engine=None, timeline_state=None):
        self.music_engine = music_engine
        self.narrative_engine = narrative_engine
        self.timeline = timeline_state
        self.scorer = ImpactScorer(music_engine, narrative_engine, timeline_state)
        self.detected_moments: List[Dict] = []
        self.scored_words: List[Dict] = []

    def analyze_words(self, words: List[Dict]) -> List[Dict]:
        scored = self.scorer.analyze_words(words or [])
        self.set_scored_words(scored)
        return scored

    def set_scored_words(self, scored_words: List[Dict]):
        self.scored_words = scored_words or []
        self._find_viral_sequences()

    def _find_viral_sequences(self):
        self.detected_moments = []
        if not self.scored_words:
            return

        sequence = []
        for word in self.scored_words:
            if word.get("is_viral") or float(word.get("impact_score", 0.0)) >= 0.55:
                sequence.append(word)
                continue
            self._flush_sequence(sequence)
            sequence = []
        self._flush_sequence(sequence)

        log("VIRAL", f"Detectados {len(self.detected_moments)} momentos de impacto")

    def _flush_sequence(self, sequence: List[Dict]):
        if not sequence:
            return
        scores = [float(w.get("impact_score", 0.0)) for w in sequence]
        self.detected_moments.append({
            "start": float(sequence[0].get("start", 0.0)),
            "end": float(sequence[-1].get("end", sequence[-1].get("start", 0.0) + 0.3)),
            "words": sequence,
            "avg_score": float(np.mean(scores)) if scores else 0.0,
            "type": sequence[0].get("moment_type", "normal"),
            "word_count": len(sequence),
        })

    def get_best_speech_segment(self, target_duration: float = 30.0) -> Tuple[float, float]:
        if not self.scored_words:
            return 0.0, float(target_duration)

        first_time = float(self.scored_words[0].get("start", 0.0))
        last_time = float(self.scored_words[-1].get("end", self.scored_words[-1].get("start", target_duration)))
        if last_time - first_time <= target_duration:
            return first_time, min(last_time, first_time + target_duration)

        step = 0.5
        best_start = first_time
        best_score = -1.0
        current = first_time
        while current + target_duration <= last_time + 1e-6:
            window_words = [
                w for w in self.scored_words
                if current <= float(w.get("start", 0.0)) <= current + target_duration
            ]
            if window_words:
                density = len(window_words) / max(target_duration, 1.0)
                impact = sum(float(w.get("impact_score", 0.0)) for w in window_words)
                music_bonus = self._music_window_bonus(current, target_duration)
                score = impact + density * 0.8 + music_bonus
                if score > best_score:
                    best_score = score
                    best_start = current
            current += step

        best_end = best_start + target_duration
        log("SPEECH", f"Melhor fala: {best_start:.1f}s - {best_end:.1f}s | score {best_score:.2f}")
        return float(best_start), float(best_end)

    def _music_window_bonus(self, start: float, duration: float) -> float:
        if not self.music_engine:
            return 0.0
        samples = np.linspace(start, start + duration, num=8)
        tension = [self.music_engine.get_tension_at(float(t)) for t in samples]
        return float(np.mean(tension)) * 1.2 if tension else 0.0

    def get_moment_at(self, time_sec: float, tolerance: float = 0.15) -> Optional[Dict]:
        for moment in self.detected_moments:
            if moment["start"] - tolerance <= time_sec <= moment["end"] + tolerance:
                return moment
        return None

    def is_viral_moment(self, time_sec: float) -> bool:
        return self.get_moment_at(time_sec) is not None

    def get_moment_intensity(self, time_sec: float) -> float:
        moment = self.get_moment_at(time_sec)
        return float(moment.get("avg_score", 0.0)) if moment else 0.0

    def get_treatment_for_moment(self, time_sec: float) -> Dict:
        moment = self.get_moment_at(time_sec)
        if not moment:
            return {
                "treatment": "normal",
                "caption_emphasis": 0.5,
                "effect_boost": 1.0,
                "pacing_boost": 1.0,
                "should_freeze": False,
            }

        intensity = float(moment.get("avg_score", 0.5))
        treatment_type = moment.get("type", "normal")
        return {
            "treatment": treatment_type,
            "caption_emphasis": min(1.0, 0.55 + intensity * 0.45),
            "effect_boost": 1.0 + intensity * 0.45,
            "pacing_boost": 1.0 + intensity * 0.3,
            "should_freeze": treatment_type in ("silence_reveal", "emotional_peak") and intensity > 0.72,
        }
