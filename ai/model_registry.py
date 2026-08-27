# -*- coding: utf-8 -*-
"""
AI Model Registry — Singleton para modelos de IA.
Carrega cada modelo UMA vez e mantém em memória.
"""
from logger import log


class ModelRegistry:
    """
    Gerencia modelos de IA como singletons.
    Evita recarregar YOLO, MediaPipe, CLIP a cada execução.
    """
    _models = {}
    _device = None

    @classmethod
    def _get_device(cls):
        if cls._device is None:
            try:
                import torch
                cls._device = "cuda" if torch.cuda.is_available() else "cpu"
            except:
                cls._device = "cpu"
        return cls._device

    @classmethod
    def get_yolo(cls):
        """Retorna instância única do YOLOv8n."""
        if "yolo" not in cls._models:
            from ultralytics import YOLO
            log("REGISTRY", "Carregando YOLOv8n (singleton)...")
            device = 0 if cls._get_device() == "cuda" else "cpu"
            cls._models["yolo"] = YOLO("yolov8n.pt")
            if cls._get_device() == "cuda":
                cls._models["yolo"].to("cuda")
        return cls._models["yolo"]

    @classmethod
    def get_mediapipe_pose(cls):
        """Retorna instância única do MediaPipe Pose."""
        if "mediapipe_pose" not in cls._models:
            import mediapipe as mp
            log("REGISTRY", "Carregando MediaPipe Pose (singleton)...")
            cls._models["mediapipe_pose"] = mp.solutions.pose.Pose(
                static_image_mode=False,
                min_detection_confidence=0.5,
                model_complexity=0  # 0 = mais leve
            )
        return cls._models["mediapipe_pose"]

    @classmethod
    def get_mediapipe_face(cls):
        """Retorna instância única do MediaPipe Face Mesh."""
        if "mediapipe_face" not in cls._models:
            import mediapipe as mp
            log("REGISTRY", "Carregando MediaPipe Face (singleton)...")
            cls._models["mediapipe_face"] = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                min_detection_confidence=0.5
            )
        return cls._models["mediapipe_face"]

    @classmethod
    def get_clip(cls):
        """Retorna instância única do CLIP ViT-B-32."""
        if "clip" not in cls._models:
            import open_clip
            import torch
            log("REGISTRY", "Carregando CLIP ViT-B-32 (singleton)...")
            model, _, preprocess = open_clip.create_model_and_transforms(
                'ViT-B-32', pretrained='laion2b_s34b_b79k'
            )
            tokenizer = open_clip.get_tokenizer('ViT-B-32')
            if cls._get_device() == "cuda":
                model = model.cuda().half()  # FP16 na GPU
            model.eval()
            cls._models["clip"] = (model, preprocess, tokenizer)
        return cls._models["clip"]