# -*- coding: utf-8 -*-
"""
Cinematic Engine — Eventos cinematográficos com memória temporal,
cooldown adaptativo e lógica narrativa.
"""
import random
from typing import Dict, Optional, List
from logger import log


class TemporalMemory:
    """Memória temporal para evitar repetição de eventos."""

    def __init__(self, cooldowns: Optional[Dict[str, float]] = None):
        self.history: List[tuple] = []
        self.cooldowns = cooldowns or {
            'freeze_impact': 4.0,
            'zoom_crash': 2.5,
            'velocity_ramp': 3.0,
            'flash_hit': 1.8,
            'chromatic_aberration': 5.0,
            'bass_distortion': 3.5,
            'directional_blur': 4.0,
            'glitch_transition': 6.0,
            'beat_anticipation': 3.0,
            'dramatic_silence': 8.0,
            'camera_whip': 5.0,
            'frame_echo': 5.0,
        }
        self.max_history = 50

    def update(self, event_type: str, intensity: float, timestamp: float):
        self.history.append((timestamp, event_type, intensity))
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def can_use(self, event_type: str, current_time: float) -> bool:
        cooldown = self.cooldowns.get(event_type, 2.5)
        for t, et, _ in reversed(self.history):
            if et == event_type and current_time - t < cooldown:
                return False
        return True

    def recent_intensity(self, window: float = 5.0) -> float:
        if not self.history:
            return 0.5
        now = self.history[-1][0]
        recent = [intens for t, _, intens in self.history if now - t <= window]
        return sum(recent) / len(recent) if recent else 0.5

    def recent_events(self, n: int = 5) -> List[str]:
        return [e for _, e, _ in self.history[-n:]]

    def count_recent(self, event_type: str, window: float = 10.0) -> int:
        if not self.history:
            return 0
        now = self.history[-1][0]
        return sum(1 for t, et, _ in self.history
                   if et == event_type and now - t <= window)


class CinematicEngine:
    """
    Catálogo de eventos cinematográficos com:
    - Intensidade adaptativa
    - Cooldown por evento
    - Variação procedural
    - Contexto narrativo
    """

    @staticmethod
    def freeze_impact(strength: float, is_climax: bool = False) -> Dict:
        scale = 1.15 + strength * 0.15 if is_climax else 1.08 + strength * 0.08
        return {
            'type': 'freeze_impact',
            'freeze_frame': True,
            'freeze_duration': 0.08 + strength * 0.1,
            'zoom_scale': scale,
            'flash': True,
            'flash_intensity': 0.7 + strength * 0.3,
            'speed_change': 0.7 if is_climax else 0.85,
            'shake_intensity': 2 if is_climax else 0,
        }

    @staticmethod
    def velocity_ramp(strength: float, is_climax: bool = False) -> Dict:
        ramp_type = random.choice(['speed_up', 'slow_down', 'wave'])
        if ramp_type == 'speed_up':
            speed = 0.4 + strength * 0.3
        elif ramp_type == 'slow_down':
            speed = 1.6 + strength * 0.5
        else:
            speed = 0.6
        return {
            'type': 'velocity_ramp',
            'ramp_type': ramp_type,
            'speed_change': speed,
            'zoom_scale': 1.0,
            'flash': False,
            'shake_intensity': 0,
        }

    @staticmethod
    def zoom_crash(strength: float, is_climax: bool = False) -> Dict:
        return {
            'type': 'zoom_crash',
            'zoom_scale': 1.2 + strength * 0.2 if is_climax else 1.1 + strength * 0.1,
            'shake_intensity': 5 if is_climax else 3,
            'flash': is_climax,
            'speed_change': 1.0,
            'freeze_frame': is_climax,
            'freeze_duration': 0.06 if is_climax else 0,
        }

    @staticmethod
    def flash_hit(strength: float, is_climax: bool = False) -> Dict:
        return {
            'type': 'flash_hit',
            'flash': True,
            'flash_intensity': 0.5 + strength * 0.5,
            'zoom_scale': 1.0,
            'shake_intensity': 1,
            'speed_change': 1.0,
        }

    @staticmethod
    def chromatic_aberration(strength: float, is_climax: bool = False) -> Dict:
        return {
            'type': 'chromatic_aberration',
            'rgb_split': True,
            'split_intensity': 2 + int(strength * 6),
            'zoom_scale': 1.02,
            'flash': False,
        }

    @staticmethod
    def bass_distortion(strength: float, is_climax: bool = False) -> Dict:
        return {
            'type': 'bass_distortion',
            'distort': True,
            'distort_intensity': 3 + int(strength * 8),
            'shake_intensity': 6,
            'flash': True,
            'zoom_scale': 1.05,
        }

    @staticmethod
    def directional_blur(strength: float, is_climax: bool = False, direction: str = None) -> Dict:
        if direction is None:
            direction = random.choice(['left', 'right', 'up', 'down'])
        return {
            'type': 'directional_blur',
            'blur_direction': direction,
            'blur_intensity': 5 + int(strength * 15),
            'zoom_scale': 1.0,
        }

    @staticmethod
    def camera_whip(strength: float, is_climax: bool = False) -> Dict:
        return {
            'type': 'camera_whip',
            'whip_direction': random.choice(['horizontal', 'vertical', 'diagonal']),
            'whip_speed': 0.3 + strength * 0.4,
            'motion_blur': True,
            'zoom_scale': 1.0,
        }

    @staticmethod
    def beat_anticipation(strength: float) -> Dict:
        return {
            'type': 'beat_anticipation',
            'slow_mo_before': True,
            'slow_factor': 0.5,
            'anticipation_duration': 0.15 + strength * 0.1,
            'zoom_scale': 1.0,
            'flash': False,
        }

    @staticmethod
    def dramatic_silence(strength: float = 0.5) -> Dict:
        return {
            'type': 'dramatic_silence',
            'freeze_frame': True,
            'freeze_duration': 0.3,
            'zoom_scale': 1.0,
            'flash': False,
            'speed_change': 1.0,
            'mute_visual': True,
        }

    @staticmethod
    def frame_echo(strength: float, is_climax: bool = False) -> Dict:
        return {
            'type': 'frame_echo',
            'echo_count': 2 + int(strength * 3),
            'echo_delay': 0.04,
            'zoom_scale': 1.0,
            'flash': False,
        }

    @classmethod
    def select_event(cls,
                     beat_type: str,
                     strength: float,
                     is_drop: bool,
                     is_climax: bool,
                     should_breathe: bool,
                     memory: TemporalMemory,
                     current_time: float) -> Dict:
        """
        Seleciona o melhor evento cinematográfico baseado em:
        - Tipo de batida
        - Força
        - Contexto narrativo (clímax, respiro)
        - Memória temporal
        """

        # Eventos disponíveis com pesos
        candidates = []

        if is_climax and is_drop:
            candidates = [
                (cls.freeze_impact, 0.35),
                (cls.zoom_crash, 0.25),
                (cls.bass_distortion, 0.20),
                (cls.chromatic_aberration, 0.10),
                (cls.camera_whip, 0.10),
            ]
        elif is_drop and strength > 0.8:
            candidates = [
                (cls.freeze_impact, 0.25),
                (cls.zoom_crash, 0.30),
                (cls.velocity_ramp, 0.20),
                (cls.flash_hit, 0.25),
            ]
        elif should_breathe:
            candidates = [
                (cls.dramatic_silence, 0.5),
                (cls.beat_anticipation, 0.3),
                (cls.directional_blur, 0.2),
            ]
        elif beat_type == "kick" and strength > 0.7:
            candidates = [
                (cls.zoom_crash, 0.25),
                (cls.flash_hit, 0.25),
                (cls.velocity_ramp, 0.20),
                (cls.frame_echo, 0.15),
                (cls.directional_blur, 0.15),
            ]
        elif beat_type == "snare" and strength > 0.6:
            candidates = [
                (cls.flash_hit, 0.35),
                (cls.velocity_ramp, 0.25),
                (cls.chromatic_aberration, 0.20),
                (cls.frame_echo, 0.20),
            ]
        else:
            candidates = [
                (cls.flash_hit, 0.5),
                (cls.velocity_ramp, 0.3),
                (cls.directional_blur, 0.2),
            ]

        # Filtra por cooldown
        valid_candidates = []
        for event_fn, weight in candidates:
            # Corrige chamada para eventos que não aceitam is_climax
            if event_fn.__name__ in ['dramatic_silence', 'beat_anticipation']:
                event = event_fn(strength)
            elif event_fn.__name__ in ['directional_blur']:
                event = event_fn(strength, is_climax)
            else:
                event = event_fn(strength, is_climax)

            if memory.can_use(event['type'], current_time):
                # Penaliza se usou muitas vezes recentemente
                recent_count = memory.count_recent(event['type'], window=8.0)
                adjusted_weight = weight * (0.5 ** recent_count)
                valid_candidates.append((event, adjusted_weight))

        if not valid_candidates:
            # Fallback: evento nulo
            return {
                'type': 'none',
                'freeze_frame': False,
                'zoom_scale': 1.0,
                'flash': False,
                'speed_change': 1.0,
                'shake_intensity': 0,
            }

        # Seleciona por peso
        events, weights = zip(*valid_candidates)
        total_weight = sum(weights)
        probs = [w / total_weight for w in weights]
        selected = random.choices(events, weights=probs, k=1)[0]

        return selected