# -*- coding: utf-8 -*-
"""
Visual Intelligence Engine — Análise visual hierárquica.
- Passo 1: Análise leve (motion, brilho) — todas as cenas
- Passo 2: YOLO — top 15 cenas
- Passo 3: CLIP + MediaPipe — apenas top 5 cenas
"""
import cv2
import numpy as np
from typing import Dict, List, Tuple
from logger import log
from model_registry import ModelRegistry


class VisualIntelligence:
    """
    Compreende o vídeo como um editor humano.
    Usa análise hierárquica para performance máxima.
    """

    def __init__(self):
        self._models_loaded = False

    def _ensure_models(self):
        """Pré-carrega modelos via registry (singleton)."""
        if self._models_loaded:
            return
        ModelRegistry.get_yolo()
        ModelRegistry.get_mediapipe_pose()
        ModelRegistry.get_clip()
        self._models_loaded = True

    def analyze_scene_light(self, video_path: str, start: float, end: float) -> Dict:
        """
        Análise LEVE — apenas motion e brilho.
        Rápido, para filtrar cenas.
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int((end - start) * fps)
        if total_frames < 1:
            cap.release()
            return {'visual_emotion': 'neutral', 'cinematic_score': 0.5, 'has_person': None}

        # Apenas 1 frame central
        mid_frame = total_frames // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps) + mid_frame)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return {'visual_emotion': 'neutral', 'cinematic_score': 0.5, 'has_person': None}

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90))
        sharpness = float(cv2.Laplacian(small, cv2.CV_64F).var())
        brightness = float(np.mean(small))

        # Score simples
        cinematic_score = min(sharpness / 100.0, 1.0) * 0.5 + (1.0 - abs(brightness - 128) / 128) * 0.5

        return {
            'visual_emotion': 'neutral',
            'cinematic_score': float(cinematic_score),
            'has_person': None,
            'gaze_direction': None,
            'composition': {},
        }

    def analyze_scene_yolo(self, video_path: str, start: float, end: float) -> Dict:
        """
        Análise MÉDIA — YOLO para detectar pessoas e objetos.
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int((end - start) * fps)
        if total_frames < 1:
            cap.release()
            return {'visual_emotion': 'neutral', 'has_person': False, 'objects': [], 'cinematic_score': 0.5}

        mid_frame = total_frames // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps) + mid_frame)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return {'visual_emotion': 'neutral', 'has_person': False, 'objects': [], 'cinematic_score': 0.5}

        h, w = frame.shape[:2]
        objects = []
        has_person = False
        emotion = 'neutral'

        try:
            yolo = ModelRegistry.get_yolo()
            result = yolo(frame, verbose=False)[0]
            names = yolo.names
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if conf > 0.4:
                    name = names[cls_id]
                    objects.append({'name': name, 'confidence': conf})
                    if name == 'person':
                        has_person = True

            # Emoção baseada em objetos
            if any(o['name'] in ['explosion', 'gun', 'knife'] for o in objects):
                emotion = 'action'
            elif any(o['name'] in ['car', 'motorcycle', 'truck'] for o in objects):
                emotion = 'action'
            elif has_person:
                emotion = 'emotional'
        except Exception as e:
            log("VISUAL", f"YOLO erro: {e}")

        return {
            'visual_emotion': emotion,
            'has_person': has_person,
            'objects': [o['name'] for o in objects],
            'cinematic_score': 0.7 if has_person else 0.5,
        }

    def analyze_scene_deep(self, video_path: str, start: float, end: float) -> Dict:
        """
        Análise PESADA — CLIP + MediaPipe.
        SÓ para as melhores cenas.
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int((end - start) * fps)
        if total_frames < 1:
            cap.release()
            return {'visual_emotion': 'neutral', 'semantic_context': 'unknown',
                    'gaze_direction': None, 'cinematic_score': 0.5}

        mid_frame = total_frames // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps) + mid_frame)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return {'visual_emotion': 'neutral', 'semantic_context': 'unknown',
                    'gaze_direction': None, 'cinematic_score': 0.5}

        h, w = frame.shape[:2]
        result = {
            'visual_emotion': 'neutral',
            'semantic_context': 'unknown',
            'gaze_direction': None,
            'cinematic_score': 0.5,
        }

        # CLIP
        try:
            clip_model, preprocess, tokenizer = ModelRegistry.get_clip()
            import torch
            from PIL import Image

            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image_input = preprocess(image).unsqueeze(0)
            if torch.cuda.is_available():
                image_input = image_input.cuda()

            texts = ["intense action scene", "calm landscape", "emotional close-up",
                     "explosion or impact", "dark cinematic atmosphere"]
            text_tokens = tokenizer(texts)
            if torch.cuda.is_available():
                text_tokens = text_tokens.cuda()

            with torch.no_grad():
                img_feat = clip_model.encode_image(image_input)
                txt_feat = clip_model.encode_text(text_tokens)
                img_feat /= img_feat.norm(dim=-1, keepdim=True)
                txt_feat /= txt_feat.norm(dim=-1, keepdim=True)
                sim = (100.0 * img_feat @ txt_feat.T).softmax(dim=-1)

            top_idx = sim[0].argmax().item()
            result['semantic_context'] = texts[top_idx]

            ctx = texts[top_idx]
            if 'action' in ctx or 'explosion' in ctx:
                result['visual_emotion'] = 'action'
                result['cinematic_score'] = 0.85
            elif 'emotional' in ctx:
                result['visual_emotion'] = 'emotional'
                result['cinematic_score'] = 0.7
            elif 'calm' in ctx:
                result['visual_emotion'] = 'calm'
                result['cinematic_score'] = 0.3
            elif 'dark' in ctx:
                result['visual_emotion'] = 'tense'
                result['cinematic_score'] = 0.7
        except Exception as e:
            log("VISUAL", f"CLIP erro: {e}")

        # MediaPipe Pose
        try:
            pose = ModelRegistry.get_mediapipe_pose()
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pose_result = pose.process(frame_rgb)
            if pose_result.pose_landmarks:
                landmarks = pose_result.pose_landmarks.landmark
                left_eye = landmarks[2]
                right_eye = landmarks[5]
                result['gaze_direction'] = (
                    float((left_eye.x + right_eye.x) / 2),
                    float((left_eye.y + right_eye.y) / 2)
                )
                result['has_pose'] = True
        except Exception as e:
            log("VISUAL", f"MediaPipe erro: {e}")

        return result

    def compute_eye_trace_compatibility(self, scene_a: Dict, scene_b: Dict) -> float:
        gaze_a = scene_a.get('gaze_direction')
        gaze_b = scene_b.get('gaze_direction')
        if gaze_a is None or gaze_b is None:
            return 0.5
        dist = np.sqrt((gaze_a[0] - gaze_b[0])**2 + (gaze_a[1] - gaze_b[1])**2)
        return float(max(0, 1.0 - dist * 3))