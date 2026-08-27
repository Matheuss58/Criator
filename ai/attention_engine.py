# -*- coding: utf-8 -*-
"""
Attention Engine — Modela fadiga, antecipação e janelas de recompensa.
Simula a psicologia do espectador.
"""
from logger import log


class AttentionEngine:
    """
    Simula a atenção humana:
    - Fadiga acumulada
    - Janelas de recompensa (dopamina)
    - Antecipação
    - Overstimulation
    """

    def __init__(self, timeline_state):
        self.state = timeline_state
        self.stimulus_count = 0
        self.high_intensity_count = 0
        self.last_reward_time = 0.0

    def register_stimulus(self, intensity: float):
        """Registra um estímulo visual/sonoro."""
        self.stimulus_count += 1

        # Atualiza dopamina
        if intensity > 0.75:
            self.state.dopamine = min(1.0, self.state.dopamine + 0.12)
            self.high_intensity_count += 1
        else:
            self.state.dopamine = max(0.1, self.state.dopamine - 0.03)

        # Atualiza fadiga
        if intensity > 0.8:
            self.state.fatigue = min(1.0, self.state.fatigue + 0.06)
        elif intensity < 0.3:
            self.state.fatigue = max(0.0, self.state.fatigue - 0.05)

        # Overstimulation
        if self.high_intensity_count > 6:
            self.state.fatigue = min(1.0, self.state.fatigue + 0.2)
            self.high_intensity_count = 0

        # Atualiza tensão
        self.state.tension += (intensity - self.state.tension) * 0.2

    def update(self, dt: float = 0.04):
        """Decaimento natural ao longo do tempo."""
        self.state.fatigue = max(0.0, self.state.fatigue - 0.01 * dt)
        self.state.dopamine = max(0.1, self.state.dopamine - 0.02 * dt)
        self.state.tension = max(0.1, self.state.tension - 0.015 * dt)

        # Reseta contador de alta intensidade periodicamente
        if self.state.fatigue < 0.3:
            self.high_intensity_count = max(0, self.high_intensity_count - 1)

    def should_reward(self) -> bool:
        """Retorna True se é um bom momento para impacto visual."""
        return (
            self.state.dopamine > 0.6 and
            self.state.fatigue < 0.6 and
            self.state.tension > 0.5
        )

    def get_recommended_intensity(self) -> float:
        """Intensidade recomendada para o próximo estímulo."""
        if self.state.needs_break():
            return 0.2
        if self.state.can_explode():
            return 0.9
        if self.state.fatigue > 0.5:
            return 0.5
        return self.state.energy