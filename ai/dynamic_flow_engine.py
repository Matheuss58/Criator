# -*- coding: utf-8 -*-
"""
Dynamic Flow Engine - Substitui COMPLETAMENTE o sistema antigo de pacing
Edição baseada em análise REAL, não curva fixa.
"""

class DynamicFlowEngine:
    """
    Controla o fluxo baseado em:
    - Movimento REAL das cenas
    - Detecção de faces/emoções
    - Intensidade musical real
    """

    def __init__(self, timeline_state, duration: float):
        self.state = timeline_state
        self.duration = duration
        self.motion_samples = []
        self.face_samples = []
        self.action_peaks = []

    def update(self, current_time: float):
        """Interface compatível com o loop principal"""
        self.state.time = current_time
        self.state.progress = min(1.0, current_time / self.duration)

        if not self.motion_samples:
            progress = self.state.progress
            if progress < 0.2:
                self.state.energy = 0.4
            elif progress < 0.5:
                self.state.energy = 0.7
            elif progress < 0.8:
                self.state.energy = 0.9
            else:
                self.state.energy = 0.6

    def update_with_scene(self, scene_data: dict, current_time: float, music_intensity: float):
        """Atualiza o estado baseado na cena REAL"""
        motion = scene_data.get("motion", 5)
        has_face = scene_data.get("face_score", 0) > 0.15
        face_emotion = scene_data.get("visual_data", {}).get("visual_emotion", "neutral")

        raw_energy = min(1.0, motion / 30.0)

        if has_face and face_emotion in ["surprise", "anger"]:
            raw_energy += 0.3

        raw_energy = (raw_energy + music_intensity) / 2
        self.state.energy = min(1.0, max(0.1, raw_energy))

        if motion > 25:
            self.state.phase = "action_peak"
        elif motion > 15:
            self.state.phase = "dynamic"
        elif has_face and face_emotion in ["sadness", "contemplative"]:
            self.state.phase = "dramatic"
        elif motion < 5:
            self.state.phase = "calm"
        else:
            self.state.phase = "neutral"

        self.state.time = current_time
        self.state.progress = min(1.0, current_time / self.duration)

        self.motion_samples.append(motion)
        self.face_samples.append(1 if has_face else 0)

        if motion > 25:
            self.action_peaks.append(current_time)

    def get_pacing_multiplier(self) -> float:
        if self.state.energy > 0.8:
            return 0.4
        elif self.state.energy > 0.6:
            return 0.6
        elif self.state.energy > 0.4:
            return 0.9
        elif self.state.energy > 0.2:
            return 1.3
        else:
            return 1.8

    def get_subtitle_energy(self) -> float:
        return self.state.energy

    def get_camera_intensity(self) -> float:
        return min(0.9, self.state.energy * 0.8)
