# -*- coding: utf-8 -*-
"""
Timeline State — Estado temporal unificado.
TODOS os módulos leem e escrevem aqui.
É a "consciência" do Criator.
"""
from typing import Dict, Optional


class TimelineState:
    """
    Estado temporal compartilhado por todos os engines.
    Representa a "atenção humana" ao longo do tempo.
    """

    def __init__(self):
        self.energy = 0.5           # 0-1 energia atual
        self.tension = 0.5          # 0-1 tensão acumulada
        self.focus = 0.5            # 0-1 intensidade do foco visual
        self.fatigue = 0.0          # 0-1 fadiga do espectador
        self.dopamine = 0.5         # 0-1 janela dopaminérgica
        self.phase = "intro"        # fase narrativa
        self.visual_density = 0.5   # 0-1 densidade visual
        self.lyric_importance = 0.5 # 0-1 importância da letra atual
        self.impact_probability = 0.0  # 0-1 probabilidade de impacto
        self.time = 0.0             # tempo atual
        self.progress = 0.0         # 0-1 progresso do vídeo

    def update(self, **kwargs):
        """Atualiza múltiplos campos de uma vez."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def snapshot(self) -> Dict:
        """Retorna uma cópia do estado atual."""
        return {
            "energy": self.energy,
            "tension": self.tension,
            "focus": self.focus,
            "fatigue": self.fatigue,
            "dopamine": self.dopamine,
            "phase": self.phase,
            "visual_density": self.visual_density,
            "lyric_importance": self.lyric_importance,
            "impact_probability": self.impact_probability,
            "time": self.time,
            "progress": self.progress,
        }

    def needs_break(self) -> bool:
        return self.fatigue > 0.7

    def can_explode(self) -> bool:
        return self.dopamine > 0.7 and self.fatigue < 0.5

    def should_breathe(self) -> bool:
        return self.energy < 0.25 or self.fatigue > 0.6