# -*- coding: utf-8 -*-
"""
Continuity Engine - Sistema de continuidade visual procedural.
Analisa fluxo visual entre cenas para evitar cortes caoticos.
"""
import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional
from logger import log


class ContinuityEngine:
    """
    Analisa e pontua compatibilidade visual entre cenas.
    Garante que cortes consecutivos tenham fluidez visual.
    """

    def __init__(self):
        self.scene_features: Dict[int, Dict] = {}
        self.compatibility_cache: Dict[Tuple[int, int], float] = {}

    def extract_features(self, video_path: str, scene_id: int,
                         start_time: float, end_time: float) -> Dict:
        """
        Extrai features visuais de uma cena.
        """
        cap = cv2.VideoCapture(video_path)
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            sample_times = np.linspace(start_time, end_time, min(5, max(1, int(end_time - start_time))))
            features = {
                'motion_direction': [],
                'motion_magnitude': [],
                'brightness': [],
                'dominant_color': [],
                'subject_position': [],
                'motion_density': [],
            }
            prev_gray = None
            for t in sample_times:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
                ret, frame = cap.read()
                if not ret:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                features['brightness'].append(float(np.mean(gray)))
                features['dominant_color'].append(float(np.mean(hsv[:, :, 0])))
                if prev_gray is not None:
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
                    )
                    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                    total_mag = np.sum(mag)
                    if total_mag > 0:
                        mean_ang = np.sum(ang * mag) / total_mag
                        features['motion_direction'].append(float(mean_ang))
                        features['motion_magnitude'].append(float(np.mean(mag)))
                        h, w = mag.shape
                        y_idx, x_idx = np.indices((h, w))
                        cx = np.sum(x_idx * mag) / total_mag / w
                        cy = np.sum(y_idx * mag) / total_mag / h
                        features['subject_position'].append((float(cx), float(cy)))
                        motion_pixels = np.sum(mag > 1.0)
                        features['motion_density'].append(float(motion_pixels / (h * w)))
                prev_gray = gray
        finally:
            cap.release()

        aggregated = {
            'motion_direction': float(np.mean(features['motion_direction'])) if features['motion_direction'] else 0.0,
            'motion_magnitude': float(np.mean(features['motion_magnitude'])) if features['motion_magnitude'] else 0.0,
            'brightness': float(np.mean(features['brightness'])) if features['brightness'] else 128.0,
            'dominant_color': float(np.mean(features['dominant_color'])) if features['dominant_color'] else 0.0,
            'subject_position': (
                float(np.mean([p[0] for p in features['subject_position']])) if features['subject_position'] else 0.5,
                float(np.mean([p[1] for p in features['subject_position']])) if features['subject_position'] else 0.5,
            ),
            'motion_density': float(np.mean(features['motion_density'])) if features['motion_density'] else 0.0,
        }
        self.scene_features[scene_id] = aggregated
        return aggregated

    def compute_compatibility(self, scene_a: Dict, scene_b: Dict) -> float:
        """Calcula score de compatibilidade (0-1) entre duas cenas."""
        score = 0.0
        weights = {
            'motion_continuity': 0.30,
            'brightness_similarity': 0.20,
            'color_harmony': 0.15,
            'subject_position': 0.15,
            'density_match': 0.20,
        }

        dir_a = scene_a.get('motion_direction', 0)
        dir_b = scene_b.get('motion_direction', 0)
        angle_diff = abs(dir_a - dir_b)
        if angle_diff > np.pi / 2:
            motion_score = max(0, 1.0 - (angle_diff - np.pi/2) / np.pi)
        else:
            motion_score = 1.0 - angle_diff / np.pi
        score += motion_score * weights['motion_continuity']

        bright_a = scene_a.get('brightness', 128) / 255.0
        bright_b = scene_b.get('brightness', 128) / 255.0
        bright_diff = abs(bright_a - bright_b)
        bright_score = 1.0 - bright_diff
        score += bright_score * weights['brightness_similarity']

        hue_a = scene_a.get('dominant_color', 0) / 180.0
        hue_b = scene_b.get('dominant_color', 0) / 180.0
        hue_diff = min(abs(hue_a - hue_b), 1.0 - abs(hue_a - hue_b))
        color_score = 1.0 - hue_diff
        score += color_score * weights['color_harmony']

        pos_a = scene_a.get('subject_position', (0.5, 0.5))
        pos_b = scene_b.get('subject_position', (0.5, 0.5))
        pos_dist = np.sqrt((pos_a[0] - pos_b[0])**2 + (pos_a[1] - pos_b[1])**2)
        pos_score = max(0, 1.0 - pos_dist * 2)
        score += pos_score * weights['subject_position']

        dens_a = scene_a.get('motion_density', 0)
        dens_b = scene_b.get('motion_density', 0)
        dens_diff = abs(dens_a - dens_b)
        dens_score = 1.0 - dens_diff
        score += dens_score * weights['density_match']

        return float(np.clip(score, 0.0, 1.0))

    def get_compatibility(self, scene_id_a: int, scene_id_b: int) -> float:
        """Retorna compatibilidade entre duas cenas (com cache)."""
        cache_key = (scene_id_a, scene_id_b)
        if cache_key in self.compatibility_cache:
            return self.compatibility_cache[cache_key]

        feat_a = self.scene_features.get(scene_id_a)
        feat_b = self.scene_features.get(scene_id_b)

        if feat_a is None or feat_b is None:
            return 0.5

        compat = self.compute_compatibility(feat_a, feat_b)
        self.compatibility_cache[cache_key] = compat
        return compat

    def rank_scenes_by_compatibility(self, target_scene_id: int,
                                     candidate_scenes: List[Dict]) -> List[Dict]:
        """Ordena cenas candidatas por compatibilidade com a cena alvo."""
        ranked = []
        for scene in candidate_scenes:
            compat = self.get_compatibility(target_scene_id, scene['id'])
            combined_score = scene.get('score', 5.0) * 0.6 + compat * 40.0 * 0.4
            ranked.append((scene, combined_score, compat))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return [
            {**scene, 'continuity_score': compat}
            for scene, _, compat in ranked
        ]

    def should_allow_jump_cut(self, scene_a_id: int, scene_b_id: int,
                              narrative_energy: float) -> bool:
        """Decide se um jump cut e aceitavel."""
        compat = self.get_compatibility(scene_a_id, scene_b_id)

        if narrative_energy > 0.8:
            return compat > 0.2
        elif narrative_energy > 0.6:
            return compat > 0.4
        elif narrative_energy > 0.4:
            return compat > 0.55
        else:
            return compat > 0.7
