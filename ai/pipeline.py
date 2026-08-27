# -*- coding: utf-8 -*-
"""
Pipeline Criator Pro - Temporal Multimodal Engine
"""
import os, sys, time, shutil, subprocess, random, tempfile, uuid
import cv2, numpy as np

from config import (
    DEFAULT_DURATION, DEFAULT_FPS, FFMPEG_BIN,
    MIN_DURATION, TEMP_ROOT, ENABLE_STEMS, ENABLE_DEEP_VISION, adaptive_chunk_size, adaptive_scene_pool,
    clamp, ensure_runtime_dirs, get_mode_config
)
from effects import flash_filter
from logger import log, progress, fail
from scene_detect import find_scenes, video_duration
from transcribe import transcribe_audio
from music_vocal_extractor import separate_stems
from music_engine import MusicEngine
from narrative_engine import NarrativeEngine
from cinematic_engine import CinematicEngine, TemporalMemory
from continuity_engine import ContinuityEngine
from caption_engine import CaptionEngine
from viral_engine import ViralMomentEngine
from visual_intelligence import VisualIntelligence
from timeline_state import TimelineState
from dynamic_flow_engine import DynamicFlowEngine
from professional_editing_engine import ProfessionalEditingEngine
from attention_engine import AttentionEngine


def tc_to_sec(value):
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).replace(",", ".").split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(value)


def parse_resolution(value):
    try:
        w, h = str(value).lower().split("x")
        return int(w), int(h)
    except:
        return 1080, 1920


def has_nvidia_encoder():
    try:
        result = subprocess.run([FFMPEG_BIN, "-hide_banner", "-encoders"],
                                capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and "h264_nvenc" in result.stdout
    except:
        return False


def codec_args(codec):
    if codec == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def run_ffmpeg(args, label, retry_with_cpu=True):
    command = [FFMPEG_BIN, "-y", *args]
    log("FFMPEG", label)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        return result
    stderr = result.stderr or ""
    message = (stderr + "\n" + (result.stdout or "")).strip()
    log("FFMPEG", message[-2500:] or "FFmpeg falhou")
    if retry_with_cpu and "h264_nvenc" in args:
        cpu_args = []
        idx = 0
        while idx < len(args):
            if args[idx] == "-c:v" and idx+1 < len(args) and args[idx+1] == "h264_nvenc":
                cpu_args.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])
                idx += 2
                while idx < len(args) and args[idx] in ("-preset", "-cq"):
                    idx += 2
                continue
            cpu_args.append(args[idx])
            idx += 1
        log("FFMPEG", "Retry com libx264")
        retry = subprocess.run([FFMPEG_BIN, "-y", *cpu_args], capture_output=True, text=True)
        if retry.returncode == 0:
            return retry
        message = ((retry.stderr or "") + "\n" + (retry.stdout or "")).strip()
    raise RuntimeError(f"{label} falhou:\n{message[-4000:]}")


def ffmpeg_filter_path(path):
    value = os.path.abspath(path).replace("\\", "/")
    value = value.replace(":", r"\:")
    value = value.replace("'", r"\'")
    return value


def clamp_user_settings(duration, fps, preset):
    duration = float(duration or DEFAULT_DURATION)
    fps = int(fps or DEFAULT_FPS)
    duration = clamp(duration, MIN_DURATION, float(preset["max_duration"]))
    fps = int(clamp(fps, int(preset["fps_min"]), int(preset["fps_max"])))
    return duration, fps


def trim_audio_segment(audio_path, start, duration, output_path):
    run_ffmpeg(["-i", audio_path, "-ss", str(start), "-t", str(duration),
                "-c:a", "libmp3lame", "-q:a", "2", output_path],
               "Cortar audio", retry_with_cpu=False)
    return output_path


def shift_words(words, start_offset, duration):
    shifted = []
    end_limit = float(start_offset) + float(duration)
    for word in words or []:
        start = float(word.get("start", 0.0) or 0.0)
        end = float(word.get("end", start + 0.25) or (start + 0.25))
        if end < start_offset or start > end_limit:
            continue
        item = dict(word)
        item["start"] = max(0.0, start - start_offset)
        item["end"] = min(float(duration), max(item["start"] + 0.05, end - start_offset))
        shifted.append(item)
    return shifted


def analyze_scenes(video_path, scenes, fps, continuity_engine=None, max_samples=12):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Nao foi possivel abrir o video.")
    video_fps = cap.get(cv2.CAP_PROP_FPS) or fps or 30
    face_detector = None
    try:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_detector = cv2.CascadeClassifier(cascade_path)
    except:
        pass

    analyzed = []
    try:
        for idx, (start, end) in enumerate(scenes):
            start = tc_to_sec(start)
            end = tc_to_sec(end)
            duration = max(0.18, end - start)
            sample_count = max(1, min(max_samples, int(duration)))
            sample_times = np.linspace(start, min(end, start + max(duration, 0.3)), sample_count)
            previous_gray = None
            motion_scores, sharpness_scores, brightness_scores, face_hits = [], [], [], 0

            for sample_time in sample_times:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(sample_time * video_fps))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small = cv2.resize(gray, (160, 90))
                sharpness_scores.append(float(cv2.Laplacian(small, cv2.CV_64F).var()))
                brightness_scores.append(float(np.mean(small)))
                if previous_gray is not None:
                    diff = cv2.absdiff(previous_gray, small)
                    motion_scores.append(float(np.mean(diff)))
                previous_gray = small
                if face_detector is not None:
                    try:
                        faces = face_detector.detectMultiScale(small, 1.1, 4)
                        if len(faces):
                            face_hits += 1
                    except:
                        pass

            motion = float(np.mean(motion_scores)) if motion_scores else 0.0
            sharpness = float(np.mean(sharpness_scores)) if sharpness_scores else 0.0
            brightness = float(np.mean(brightness_scores)) if brightness_scores else 0.0
            face_score = face_hits / max(len(sample_times), 1)
            brightness_balance = 1.0 - min(abs(brightness - 118.0) / 118.0, 1.0)
            score = motion * 1.65 + min(sharpness / 18.0, 35.0) + brightness_balance * 10 + face_score * 16

            scene_type = "calm"
            if motion > 18:
                scene_type = "action"
            elif motion > 10:
                scene_type = "tense"
            elif face_score > 0.18:
                scene_type = "emotional"

            analyzed.append({
                "id": idx,
                "inicio": start, "fim": end, "duracao": duration,
                "score": score, "motion": motion, "sharpness": sharpness,
                "brightness": brightness, "face_score": face_score,
                "tipo": scene_type,
                "visual_data": {}
            })

            if continuity_engine:
                continuity_engine.extract_features(video_path, idx, start, end)

    finally:
        cap.release()

    analyzed.sort(key=lambda x: x["score"], reverse=True)
    log("SCENES", f"{len(analyzed)} cenas analisadas")
    return analyzed


def pick_scene_inteligente(pool, used, last_type, emotion_target="action",
                           continuity_engine=None, last_scene_id=None,
                           timeline_state=None, visual_intel=None,
                           last_scene_data=None):
    options = [s for s in pool if s["id"] not in used]
    if not options:
        used.clear()
        options = pool[:]

    if continuity_engine and last_scene_id is not None:
        ranked = continuity_engine.rank_scenes_by_compatibility(last_scene_id, options)
        min_compat = 0.2 if timeline_state and timeline_state.energy > 0.8 else 0.4
        options = [s for s in ranked if s.get('continuity_score', 0.5) > min_compat]
        if not options:
            options = ranked[:max(3, len(ranked)//2)]

    weights = []
    for scene in options:
        weight = max(scene.get("score", 1.0), 1.0)
        if scene["tipo"] == emotion_target:
            weight *= 2.5
        elif scene["tipo"] == "action" and emotion_target == "tense":
            weight *= 1.5
        elif scene["tipo"] == "emotional" and emotion_target == "calm":
            weight *= 1.3
        if scene["tipo"] == last_type:
            weight *= 0.6
        if 'continuity_score' in scene:
            weight *= (0.5 + scene['continuity_score'])
        if visual_intel and last_scene_data:
            eye_compat = visual_intel.compute_eye_trace_compatibility(
                last_scene_data.get('visual_data', {}),
                scene.get('visual_data', {})
            )
            weight *= (0.5 + eye_compat)
        weights.append(weight)

    return random.choices(options, weights=weights, k=1)[0]


def build_clip_filter(clip, preset, fps, width, height, event_params=None):
    filters = []
    intensity = clip.get("intensity", 0.5)

    if event_params and event_params.get('type') != 'none':
        if event_params.get("flash"):
            fl = flash_filter(intensity, clip.get("beat_type", "kick"), clip["dur"], fps)
            if fl:
                filters.append(fl)
        speed_val = event_params.get("speed_change", 1.0)
        if speed_val != 1.0:
            filters.append(f"setpts={speed_val:.2f}*PTS")
    else:
        contrast = float(preset["contrast"]) + intensity * 0.06
        saturation = float(preset["saturation"]) + intensity * 0.08
        brightness = float(preset["brightness"])
        filters.append(f"eq=contrast={contrast:.2f}:saturation={saturation:.2f}:brightness={brightness:.3f}")

    return ",".join(filters) if filters else "null"


def build_clips_director(scene_pool, beat_events, duration, preset,
                         music_engine, narrative_engine, cinematic_engine,
                         temporal_mem, continuity_engine, viral_engine,
                         timeline_state, flow_engine, attention_engine,
                         editing_engine, visual_intel=None):
    beats = [e for e in beat_events if e["time"] <= duration + 0.5]
    if len(beats) < 5:
        beats = [{"time": i * (duration / 10), "type": "kick", "strength": 1.0} for i in range(10)]

    clips = []
    used = set()
    last_type = None
    last_scene_id = None
    last_scene_data = None
    cut_density = float(preset["cut_density"])

    for index, event in enumerate(beats[:-1]):
        beat_time = event["time"]
        strength = float(event.get("strength", 1.0))

        flow_engine.update(beat_time)
        attention_engine.register_stimulus(strength)
        attention_engine.update()

        is_climax = timeline_state.phase == "climax"
        should_breathe = timeline_state.should_breathe()
        can_explode = timeline_state.can_explode()
        is_drop = music_engine.get_section_at(beat_time) == 'drop'

        event_params = cinematic_engine.select_event(
            event.get("type", "kick"), strength, is_drop,
            is_climax or can_explode, should_breathe,
            temporal_mem, beat_time
        )

        intensity = timeline_state.energy
        target_emotion = narrative_engine.get_emotion_for_scene_selection(beat_time)

        scene = pick_scene_inteligente(
            scene_pool, used, last_type, target_emotion,
            continuity_engine, last_scene_id,
            timeline_state, visual_intel, last_scene_data
        )
        used.add(scene["id"])
        last_type = scene["tipo"]
        last_scene_id = scene["id"]
        last_scene_data = scene

        pacing = flow_engine.get_pacing_multiplier()

        # Edição profissional
        shot_type, suggested_dur = editing_engine.get_next_shot(intensity, scene.get("motion", 5), scene.get("face_score", 0) > 0.15)
        rhythm_mult = editing_engine.get_rhythm_variation(index, len(beats))
        clip_dur = suggested_dur * rhythm_mult
        clip_dur = clamp(clip_dur, float(preset["min_cut"]), float(preset["max_cut"]))
        max_scene_dur = max(0.18, scene["fim"] - scene["inicio"])
        clip_dur = min(clip_dur, max_scene_dur)

        clips.append({
            "scene": scene,
            "beat_type": event.get("type", "kick"),
            "intensity": intensity,
            "dur": clip_dur,
            "event_params": event_params,
        })

        temporal_mem.update(event_params["type"], intensity, beat_time)

    total = sum(c["dur"] for c in clips)
    if total <= 0:
        raise RuntimeError("Nao foi possivel montar clipes.")
    scale = duration / total
    for c in clips:
        c["dur"] *= scale
    diff = duration - sum(c["dur"] for c in clips)
    if clips:
        clips[-1]["dur"] += diff

    # LOOP REAL - última cena = primeira cena
    if clips and len(clips) > 1:
        clips[-1]["scene"] = clips[0]["scene"]
        log("LOOP", "Loop criado: última cena = primeira cena")

    log("CLIPS", f"{len(clips)} cortes | Flow: {timeline_state.phase}")
    return clips


def render_chunk(clips, video_path, output_path, width, height, fps, codec, preset):
    parts = []
    labels = []
    for index, clip in enumerate(clips):
        scene = clip["scene"]
        start = scene["inicio"]
        available = max(0.18, scene["fim"] - scene["inicio"])
        duration = min(max(0.12, clip["dur"]), available)
        filter_chain = build_clip_filter(clip, preset, fps, width, height, clip.get("event_params"))
        parts.append(
            f"[0:v]trim=start={start:.3f}:duration={duration:.3f},"
            f"setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"{filter_chain},tpad=stop_mode=clone:stop_duration={clip['dur']:.3f},"
            f"trim=duration={clip['dur']:.3f},setpts=PTS-STARTPTS,setsar=1[v{index}]"
        )
        labels.append(f"[v{index}]")
    filter_complex = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=1:a=0[outv]"
    args = ["-i", video_path, "-filter_complex", filter_complex, "-map", "[outv]", "-an",
            "-r", str(fps), *codec_args(codec), "-pix_fmt", "yuv420p", output_path]
    run_ffmpeg(args, f"Render chunk {os.path.basename(output_path)}")


def merge_final(chunks, audio_path, output_path, duration, fps, codec, subtitle_path=None, workdir=None):
    list_path = os.path.abspath(os.path.join(workdir or ".", "list.txt"))
    with open(list_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(f"file '{os.path.abspath(chunk).replace(chr(92), '/')}'\n")
    args = ["-f", "concat", "-safe", "0", "-i", list_path, "-i", audio_path,
            "-t", str(duration), "-map", "0:v:0", "-map", "1:a:0"]
    if subtitle_path:
        args.extend(["-vf", f"ass='{ffmpeg_filter_path(subtitle_path)}'"])
    args.extend(["-r", str(fps), *codec_args(codec),
                 "-af", "apad", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", output_path])
    try:
        run_ffmpeg(args, "Merge final")
    except RuntimeError:
        if not subtitle_path:
            raise
        log("FFMPEG", "Tentando subtitles fallback")
        if "-vf" in args:
            idx = args.index("-vf")
            args[idx+1] = f"subtitles='{ffmpeg_filter_path(subtitle_path)}'"
        run_ffmpeg(args, "Merge final com subtitles")
    finally:
        cleanup([list_path])


def cleanup(paths):
    for target in paths:
        try:
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.exists(target):
                os.remove(target)
        except OSError:
            pass


def run_pipeline(video, audio, resolution, duration_arg, fps_arg, output_path, mode_arg=None):
    started = time.time()
    ensure_runtime_dirs()
    preset = get_mode_config(mode_arg)
    mode = preset["mode"]
    duration, fps = clamp_user_settings(duration_arg, fps_arg, preset)
    width, height = parse_resolution(resolution)
    codec = "h264_nvenc" if has_nvidia_encoder() else "libx264"
    temp_files = []
    temp_dir = tempfile.mkdtemp(prefix=f"job-{uuid.uuid4().hex[:8]}-", dir=TEMP_ROOT)
    temp_files.append(temp_dir)
    progress(5, "initializing", f"Criator | modo {mode}")

    try:
        stems = {"ok": False, "vocals": None, "no_vocals": None}
        if ENABLE_STEMS:
            progress(9, "extracting_stems", "Separando voz e instrumental...")
            stems = separate_stems(audio, output_dir=os.path.join(temp_dir, "stems"), required=False)
            if not stems.get("ok"):
                log("DEMUCS", "Falhou, usando audio completo")
        else:
            progress(9, "initializing", "Modo local leve: stems desativados")

        progress(12, "analyzing_audio", "Analisando audio...")
        music_engine = MusicEngine(
            audio,
            target_duration=duration,
            vocal_path=stems.get("vocals"),
            instrumental_path=stems.get("no_vocals"),
        )

        words = []
        viral_engine = None
        segment_start, segment_end = music_engine.get_best_segment()

        if preset["subtitles"]:
            progress(20, "transcribing", "Transcrevendo fala...")
            audio_for_transcription = stems.get("vocals") or audio
            words = transcribe_audio(audio_for_transcription, workdir=temp_dir, language="pt")
            if not words:
                raise RuntimeError("Whisper nao retornou palavras para o modo legendado.")

            narrative_for_scoring = NarrativeEngine(mode, max(duration, 0.1), music_engine)
            viral_engine = ViralMomentEngine(music_engine, narrative_for_scoring)
            words = viral_engine.analyze_words(words)
            segment_start, segment_end = viral_engine.get_best_speech_segment(duration)
        else:
            progress(20, "rhythm_segment", "Selecionando melhor trecho musical...")

        available = max(0.1, segment_end - segment_start)
        duration = min(duration, available)
        trimmed_audio = os.path.join(temp_dir, "audio_trimmed.mp3")
        trim_audio_segment(audio, segment_start, duration, trimmed_audio)
        audio = trimmed_audio

        if words:
            words = shift_words(words, segment_start, duration)
            if not words:
                raise RuntimeError("Trecho escolhido nao contem palavras para legendar.")

        progress(24, "reanalyzing_segment", "Mapeando ritmo do trecho final...")
        music_engine = MusicEngine(audio, target_duration=duration)
        narrative_engine = NarrativeEngine(mode, duration, music_engine)

        timeline = TimelineState()
        flow_engine = DynamicFlowEngine(timeline, duration)
        editing_engine = ProfessionalEditingEngine()
        attention_engine = AttentionEngine(timeline)

        progress(30, "detecting_scenes", "Detectando cenas...")
        scenes = find_scenes(video)
        if not scenes:
            scenes = [(0.0, video_duration(video) or duration)]
        scene_limit = adaptive_scene_pool(duration)
        if len(scenes) > scene_limit:
            step = len(scenes) / scene_limit
            scenes = [scenes[int(i * step)] for i in range(scene_limit)]

        progress(35, "analyzing_scenes", "Analisando cenas...")
        visual_intel = VisualIntelligence()
        continuity_engine = ContinuityEngine()
        scene_pool = analyze_scenes(video, scenes, fps, continuity_engine)[:scene_limit]

        if ENABLE_DEEP_VISION:
            progress(40, "subject_analysis", "Analisando personagens e composicao...")
            for scene in scene_pool[:min(int(preset["yolo_top"]), len(scene_pool))]:
                yolo_data = visual_intel.analyze_scene_yolo(video, scene["inicio"], scene["fim"])
                scene["visual_data"] = yolo_data
                if yolo_data.get('visual_emotion') != 'neutral':
                    scene["tipo"] = yolo_data['visual_emotion']
            for scene in scene_pool[:min(int(preset["deep_visual_top"]), len(scene_pool))]:
                deep_data = visual_intel.analyze_scene_deep(video, scene["inicio"], scene["fim"])
                scene["visual_data"].update(deep_data)
        else:
            progress(45, "creative_plan", "Criando plano narrativo e ritmo visual...")

        progress(55, "building_clips", "Construindo cortes...")
        temporal_mem = TemporalMemory()
        if preset["subtitles"]:
            beat_events = [
                {"time": w["start"], "type": "vocal_peak", "strength": w.get("impact_score", w.get("intensity", 0.6))}
                for w in words
            ]
        else:
            beat_events = music_engine.get_beat_events(0.0, duration)

        clips = build_clips_director(
            scene_pool, beat_events, duration, preset,
            music_engine, narrative_engine, CinematicEngine,
            temporal_mem, continuity_engine, viral_engine,
            timeline, flow_engine, attention_engine,
            editing_engine, visual_intel
        )

        if not clips:
            raise RuntimeError("Nao foi possivel montar os clipes")

        subtitle_path = None
        if preset["subtitles"]:
            progress(64, "generating_captions", "Gerando legendas...")
            caption_engine = CaptionEngine(music_engine, narrative_engine, viral_engine, timeline, flow_engine)
            subtitle_path, _ = caption_engine.generate_ass(
                words, os.path.join(temp_dir, "subtitles.ass"), width, height
            )

        progress(70, "rendering_chunks", "Renderizando...")
        chunk_size = adaptive_chunk_size(len(clips))
        chunks = []
        total_chunks = max(1, int(np.ceil(len(clips) / chunk_size)))
        for chunk_index in range(total_chunks):
            part = clips[chunk_index * chunk_size : (chunk_index + 1) * chunk_size]
            chunk_path = os.path.join(temp_dir, f"chunk_{chunk_index:03d}.mp4")
            render_chunk(part, video, chunk_path, width, height, fps, codec, preset)
            chunks.append(chunk_path)

        progress(90, "merging_final", "Unindo audio e video...")
        merge_final(chunks, audio, output_path, duration, fps, codec, subtitle_path=subtitle_path, workdir=temp_dir)

        elapsed = time.time() - started
        progress(100, "completed", f"Finalizado em {elapsed:.1f}s")
        log("PIPELINE", f"DONE | modo={mode}")
    finally:
        cleanup(temp_files)


def main():
    if len(sys.argv) < 7:
        raise RuntimeError("Uso: pipeline.py video audio resolucao duracao fps output [modo]")
    os.makedirs(os.path.dirname(os.path.abspath(sys.argv[6])) or ".", exist_ok=True)
    run_pipeline(*sys.argv[1:8])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        fail("PIPELINE", str(exc))
        raise
