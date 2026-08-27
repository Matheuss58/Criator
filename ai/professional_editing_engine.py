# -*- coding: utf-8 -*-
"""
Professional Editing Engine - Cortes dinâmicos e variação rítmica
"""

import random
import numpy as np

class ProfessionalEditingEngine:
    def __init__(self):
        self.shot_sizes = ['wide', 'medium', 'closeup', 'extreme_closeup']
        self.transitions = ['cut', 'zoom_in', 'zoom_out', 'slide_left', 'slide_right']
        self.last_shot_type = 'medium'
        self.last_transition = 'cut'
        self.rhythm_pattern = []
        
    def get_next_shot(self, energy, motion, has_face):
        """Escolhe o próximo tipo de plano baseado no conteúdo"""
        
        # Alta energia + ação = closeups rápidos
        if energy > 0.7 and motion > 20:
            shot = random.choice(['closeup', 'extreme_closeup'])
            duration = random.uniform(0.18, 0.35)
            
        # Energia média = alternância wide/medium
        elif energy > 0.4:
            if self.last_shot_type in ['wide', 'medium']:
                shot = random.choice(['medium', 'closeup'])
            else:
                shot = 'wide'
            duration = random.uniform(0.35, 0.65)
        
        # Baixa energia = planos abertos
        else:
            shot = 'wide'
            duration = random.uniform(0.6, 1.2)
        
        # Rosto detectado = closeup
        if has_face and random.random() > 0.4:
            shot = 'closeup'
            duration = min(duration, 0.5)
        
        self.last_shot_type = shot
        return shot, duration
    
    def get_transition(self, energy, beat_strength):
        """Escolhe transição entre cortes"""
        
        # Batida forte = transição rápida
        if beat_strength > 0.8:
            transitions = ['cut', 'zoom_in']
        # Energia alta = transições dinâmicas
        elif energy > 0.6:
            transitions = ['cut', 'zoom_in', 'zoom_out']
        # Energia baixa = transições suaves
        else:
            transitions = ['cut', 'fade']
        
        selected = random.choice(transitions)
        self.last_transition = selected
        return selected
    
    def get_rhythm_variation(self, beat_index, total_beats):
        """Varia o ritmo dos cortes para não ficar monótono"""
        
        # Padrão: rápido, rápido, médio, rápido, lento, repetir
        pattern = [0.6, 0.6, 0.8, 0.6, 1.2]
        pos = beat_index % len(pattern)
        multiplier = pattern[pos]
        
        # No climax, acelera tudo
        if beat_index > total_beats * 0.3 and beat_index < total_beats * 0.7:
            multiplier *= 0.7
        
        return multiplier
