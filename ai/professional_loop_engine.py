# -*- coding: utf-8 -*-
"""
Professional Loop Engine - Sistema de loop cinematográfico para TikTok/Reels
"""

class ProfessionalLoopEngine:
    def __init__(self, continuity_engine):
        self.continuity = continuity_engine
        self.first_scene = None
        self.first_scene_id = None
        self.loop_created = False
    
    def register_first_scene(self, scene):
        """Registra a primeira cena do vídeo"""
        self.first_scene = scene
        self.first_scene_id = scene["id"]
        print(f"[LOOP] Primeira cena registrada: {scene['tipo']}")
    
    def create_cinematic_loop(self, clips, scene_pool, continuity_engine):
        """Cria loop cinematográfico - conecta fim com início"""
        if not clips or self.first_scene is None:
            return clips
        
        # Opção 1: Loop simples - última cena = primeira cena
        clips[-1]["scene"] = self.first_scene
        clips[-1]["dur"] = min(clips[-1]["dur"], 0.35)  # Mais curto para loop rápido
        
        print(f"[LOOP] Loop simples criado: última cena = primeira cena")
        
        # Opção 2: Adicionar clip extra de loop (opcional)
        if len(clips) > 3:
            loop_clip = dict(clips[0])
            loop_clip["dur"] = min(clips[0]["dur"], 0.28)
            clips.append(loop_clip)
            print(f"[LOOP] Clip extra de loop adicionado")
        
        return clips
    
    def find_best_loop_match(self, clips, scene_pool, continuity_engine):
        """Encontra a melhor cena para fazer match com o início"""
        if not clips or self.first_scene is None:
            return clips
        
        # Procurar cena visualmente similar à primeira
        candidates = [s for s in scene_pool if s["id"] != self.first_scene_id]
        
        if candidates and continuity_engine:
            ranked = continuity_engine.rank_scenes_by_compatibility(
                self.first_scene_id, 
                candidates
            )
            if ranked:
                best_match = ranked[0]
                clips[-1]["scene"] = best_match
                clips[-1]["dur"] = min(clips[-1]["dur"], 0.4)
                print(f"[LOOP] Match inteligente: {best_match['tipo']} (score: {best_match.get('continuity_score', 0):.2f})")
        
        return clips
    
    def apply_intelligent_cooldown(self, scene_id, used_recently, cooldown=3):
        """Permite reutilização inteligente de cenas após cooldown"""
        if scene_id in used_recently[-cooldown:]:
            return False  # Ainda em cooldown
        
        # Máximo de usos por cena
        max_uses = 3
        if used_recently.count(scene_id) >= max_uses:
            return False
        
        return True
