# -*- coding: utf-8 -*-
import cv2
from scenedetect import ContentDetector, SceneManager, open_video
from logger import log

def video_duration(video_path):
    cap = cv2.VideoCapture(video_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        return float(frames / fps) if fps else 0.0
    finally:
        cap.release()

def find_scenes(video_path, threshold=27.0):
    try:
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video)
        scenes = scene_manager.get_scene_list()
        result = [(s.get_seconds(), e.get_seconds()) for s, e in scenes]
    except Exception as exc:
        log("SCENES", f"PySceneDetect falhou, usando fallback: {exc}")
        result = []
    duration = video_duration(video_path)
    if not result and duration > 0:
        result = [(0.0, duration)]
    result = [(float(s), float(e)) for s, e in result if float(e) - float(s) > 0.18]
    log("SCENES", f"{len(result)} cenas detectadas")
    return result