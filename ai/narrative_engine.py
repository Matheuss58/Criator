# -*- coding: utf-8 -*-
import numpy as np
from typing import Dict, List

from config import normalize_mode


class NarrativeEngine:
    NARRATIVE_ARCS = {
        "legendado": [
            ("hook", 0.00, 0.08, 0.82, "attention_grab"),
            ("context", 0.08, 0.25, 0.50, "informative"),
            ("build", 0.25, 0.45, 0.68, "rising_interest"),
            ("revelation", 0.45, 0.62, 0.94, "mind_blown"),
            ("impact", 0.62, 0.78, 0.88, "emotional_peak"),
            ("reflection", 0.78, 0.92, 0.48, "contemplative"),
            ("payoff", 0.92, 1.00, 0.82, "satisfying_end"),
        ],
        "ritmico": [
            ("intro", 0.00, 0.10, 0.55, "anticipation"),
            ("buildup", 0.10, 0.28, 0.70, "rising_energy"),
            ("drop", 0.28, 0.56, 0.96, "explosive"),
            ("switch", 0.56, 0.74, 0.82, "peak_action"),
            ("release", 0.74, 0.88, 0.58, "release"),
            ("final_hit", 0.88, 1.00, 0.90, "climax"),
        ],
    }

    def __init__(self, mode: str, duration: float, music_engine=None):
        self.mode = normalize_mode(mode)
        self.duration = max(0.1, float(duration or 30.0))
        self.music_engine = music_engine
        self.arc = self.NARRATIVE_ARCS.get(self.mode, self.NARRATIVE_ARCS["legendado"])
        self.state_history: List[Dict] = []
        self.visual_fatigue = 0.0
        self.last_intensity = 0.5
        self.consecutive_high_energy = 0
        self.consecutive_low_energy = 0

    def get_narrative_state(self, current_time: float) -> Dict:
        progress = min(max(float(current_time) / self.duration, 0.0), 1.0)
        music_tension = 0.5
        music_emotion = "neutral"
        if self.music_engine:
            music_tension = self.music_engine.get_tension_at(current_time)
            music_emotion = self.music_engine.get_emotion_at(current_time).get("emotion", "neutral")

        phase = self._phase_for_progress(progress)
        music_weight = 0.54 if self.mode == "ritmico" else 0.45
        combined_energy = phase["base_energy"] * (1.0 - music_weight) + music_tension * music_weight
        combined_energy *= 1.0 - self.visual_fatigue * 0.28
        combined_energy = float(np.clip(combined_energy, 0.0, 1.0))

        if combined_energy > 0.84:
            pacing = "ultra_fast"
            target_cut_duration = 0.16
        elif combined_energy > 0.68:
            pacing = "fast"
            target_cut_duration = 0.26
        elif combined_energy > 0.48:
            pacing = "moderate"
            target_cut_duration = 0.42
        elif combined_energy > 0.26:
            pacing = "slow"
            target_cut_duration = 0.72
        else:
            pacing = "breathe"
            target_cut_duration = 1.18

        actions = {
            "should_emphasize": combined_energy > 0.68,
            "should_breathe": combined_energy < 0.30 or phase["emotion"] == "release",
            "should_build_anticipation": phase["emotion"] in ("anticipation", "rising_energy", "silence_tension"),
            "should_explode": phase["emotion"] in ("explosive", "climax", "peak_action"),
            "is_climax": phase["emotion"] in ("mind_blown", "climax", "explosive"),
            "is_intro": progress < 0.10,
            "is_outro": progress > 0.90,
        }

        if combined_energy > 0.80:
            self.visual_fatigue = min(1.0, self.visual_fatigue + 0.045)
            self.consecutive_high_energy += 1
            self.consecutive_low_energy = 0
        elif combined_energy < 0.30:
            self.visual_fatigue = max(0.0, self.visual_fatigue - 0.08)
            self.consecutive_low_energy += 1
            self.consecutive_high_energy = 0
        else:
            self.visual_fatigue = max(0.0, self.visual_fatigue - 0.025)

        self.last_intensity = combined_energy
        state = {
            "time": float(current_time),
            "progress": progress,
            "phase": phase["name"],
            "energy": combined_energy,
            "emotion": phase["emotion"],
            "music_tension": float(music_tension),
            "music_emotion": music_emotion,
            "pacing": pacing,
            "target_cut_duration": target_cut_duration,
            "visual_fatigue": float(self.visual_fatigue),
            "actions": actions,
        }
        self.state_history.append(state)
        return state

    def _phase_for_progress(self, progress: float) -> Dict:
        for name, start_pct, end_pct, energy, emotion in self.arc:
            if start_pct <= progress < end_pct:
                return {
                    "name": name,
                    "start_pct": start_pct,
                    "end_pct": end_pct,
                    "base_energy": energy,
                    "emotion": emotion,
                }
        name, start_pct, end_pct, energy, emotion = self.arc[-1]
        return {
            "name": name,
            "start_pct": start_pct,
            "end_pct": end_pct,
            "base_energy": energy,
            "emotion": emotion,
        }

    def get_pacing_multiplier(self, current_time: float) -> float:
        state = self.get_narrative_state(current_time)
        pacing_map = {"ultra_fast": 0.6, "fast": 0.8, "moderate": 1.0, "slow": 1.4, "breathe": 2.0}
        return pacing_map.get(state["pacing"], 1.0)

    def get_emotion_for_scene_selection(self, current_time: float) -> str:
        state = self.get_narrative_state(current_time)
        mapping = {
            "attention_grab": "action",
            "informative": "calm",
            "rising_interest": "tense",
            "mind_blown": "emotional",
            "emotional_peak": "emotional",
            "contemplative": "calm",
            "satisfying_end": "emotional",
            "anticipation": "tense",
            "rising_energy": "action",
            "explosive": "action",
            "peak_action": "action",
            "release": "calm",
            "climax": "action",
        }
        return mapping.get(state["emotion"], "action")

    def get_state_history(self) -> List[Dict]:
        return self.state_history
