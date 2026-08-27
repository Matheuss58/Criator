# -*- coding: utf-8 -*-
"""Motor local Phonk: percebe, planeja a timeline inteira e renderiza."""
from __future__ import annotations
import hashlib, json, math, os, random, shutil, subprocess, tempfile, time
from dataclasses import asdict, dataclass
import cv2, librosa, numpy as np
from config import FFMPEG_BIN, FFPROBE_BIN, TEMP_ROOT
from logger import log, progress
from scene_detect import find_scenes, video_duration

FPS = 60

@dataclass
class Scene:
    id: int; start: float; end: float; motion: float; sharpness: float
    brightness: float; color: float; face: float; quality: float; kind: str
    @property
    def duration(self): return self.end - self.start

@dataclass
class Shot:
    index: int; scene_id: int; source_start: float; source_duration: float
    timeline_start: float; duration: float; speed: float; phase: str
    effect: str; intensity: float

def run(args, label, timeout=1800):
    log("FFMPEG", label)
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        detail = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
        raise RuntimeError(f"{label} falhou:\n{detail[-3500:]}")
    return result

def probe_duration(path):
    result = run([FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], "Verificar duracao", 30)
    return float(result.stdout.strip())

def norm(values):
    values = np.asarray(values, dtype=np.float32)
    if not len(values): return values
    return (values - np.min(values)) / (np.max(values) - np.min(values) + 1e-8)

def analyze_audio(path, wanted, workdir):
    progress(12, "audio", "Entendendo ritmo, energia e estrutura musical")
    y, sr = librosa.load(path, sr=22050, mono=True)
    total = len(y) / sr
    if total < 0.2: raise RuntimeError("O audio esta vazio ou curto demais.")
    wanted = min(wanted, total); hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    energy, impact = norm(rms), norm(onset[:len(rms)])
    novelty = np.maximum(0, np.gradient(np.convolve(energy, np.ones(9) / 9, mode="same")))
    best_start, best_score = 0.0, -1.0
    for start in np.arange(0, max(.01, total - wanted) + .01, .25):
        mask = (times >= start) & (times < start + wanted)
        if not np.any(mask): continue
        e, i, n = energy[mask], impact[mask], novelty[mask]
        thirds = np.array_split(e, 3)
        arc = float(np.mean(thirds[-1]) - np.mean(thirds[0]))
        score = float(np.mean(e))*.25 + float(np.percentile(i, 90))*.28 + float(np.std(e))*.18 + max(0, arc)*.12 + float(np.mean(n))*.17
        if score > best_score: best_start, best_score = float(start), score
    beats = [float(t-best_start) for t in beat_times if best_start <= t <= best_start+wanted]
    tempo_value = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else 120.0
    if len(beats) < 4: beats = list(np.arange(0, wanted+.01, 60/max(60, tempo_value)))
    trimmed = os.path.join(workdir, "music.m4a")
    run([FFMPEG_BIN, "-y", "-ss", f"{best_start:.3f}", "-i", path, "-t", f"{wanted:.3f}", "-af", "apad", "-c:a", "aac", "-b:a", "256k", trimmed], "Preparar melhor trecho da musica")
    return {"path": trimmed, "source_start": best_start, "duration": wanted, "beats": beats, "tempo": tempo_value}

def analyze_scenes(path):
    progress(25, "scenes", "Encontrando e avaliando as melhores cenas")
    bounds = find_scenes(path, threshold=25.0) or [(0.0, video_duration(path))]
    expanded = []
    for start, end in bounds:
        pieces = max(1, int(math.ceil((end-start)/3.0)))
        points = np.linspace(start, end, pieces+1)
        expanded += [(float(points[i]), float(points[i+1])) for i in range(pieces)]
    cap = cv2.VideoCapture(path)
    if not cap.isOpened(): raise RuntimeError("Nao foi possivel abrir o video.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    scenes = []
    try:
        for idx, (start, end) in enumerate(expanded[:160]):
            if end-start < .18: continue
            previous=None; motions=[]; sharps=[]; brights=[]; colors=[]; faces=[]
            for sample in np.linspace(start+.03, max(start+.03,end-.03), min(6,max(2,int(end-start)+1))):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(sample*fps)); ok, frame=cap.read()
                if not ok: continue
                small=cv2.resize(frame,(256,144)); gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
                sharps.append(float(cv2.Laplacian(gray,cv2.CV_64F).var())); brights.append(float(np.mean(gray)))
                colors.append(float(np.mean(cv2.cvtColor(small,cv2.COLOR_BGR2HSV)[:,:,1])))
                faces.append(1.0 if len(detector.detectMultiScale(gray,1.12,4,minSize=(18,18))) else 0.0)
                if previous is not None: motions.append(float(np.mean(cv2.absdiff(previous,gray))))
                previous=gray
            if not sharps: continue
            m=float(np.mean(motions)) if motions else 0.; s=float(np.mean(sharps)); b=float(np.mean(brights)); c=float(np.mean(colors)); f=float(np.mean(faces))
            exposure=1-min(1,abs(b-118)/118); quality=min(1,s/320)*.35+min(1,m/22)*.28+exposure*.19+f*.18
            kind="action" if m>15 else "tension" if m>8 else "portrait" if f>.2 else "calm"
            scenes.append(Scene(idx,start,end,m,s,b,c,f,quality,kind))
    finally: cap.release()
    if not scenes: raise RuntimeError("Nenhuma cena utilizavel foi encontrada.")
    return scenes

def phase(t,d):
    x=t/max(d,.01)
    return "hook" if x<.10 else "setup" if x<.32 else "build" if x<.60 else "drop" if x<.88 else "release"

def cut_points(beats,duration):
    points=[0.]; cursor=0.
    desired={"hook":.42,"setup":.82,"build":.58,"drop":.34,"release":.65}
    while cursor<duration-.16:
        target=desired[phase(cursor,duration)]
        candidates=[b for b in beats if cursor+target*.62<=b<=cursor+target*1.55]
        nxt=min(candidates,key=lambda b:abs(b-(cursor+target))) if candidates else cursor+target
        nxt=min(duration,max(cursor+.22,nxt))
        if duration-nxt<.16: nxt=duration
        points.append(round(nxt,4)); cursor=nxt
    points[-1]=duration
    return points

def plan(scenes,audio,duration,seed):
    progress(45,"direction","Criando historia, ritmo e plano de montagem")
    rng=random.Random(seed); points=cut_points(audio["beats"],duration); recent=[]; last=None; shots=[]
    base={"hook":.88,"setup":.48,"build":.65,"drop":1.,"release":.72}
    for idx,(start,end) in enumerate(zip(points,points[1:])):
        p=phase(start,duration); intensity=base[p]; ranked=[]
        for scene in scenes:
            repeat=.16 if scene.id in recent[-5:] else 1.; role=1.
            if p in ("hook","drop") and scene.kind=="action": role=1.45
            elif p=="setup" and scene.kind in ("portrait","calm"): role=1.35
            elif p=="build" and scene.kind=="tension": role=1.35
            continuity=1. if not last else 1-min(.55,abs(scene.brightness-last.brightness)/220+abs(scene.color-last.color)/300)
            ranked.append((scene.quality*role*repeat*continuity*(.92+rng.random()*.16),scene))
        ranked.sort(key=lambda x:x[0],reverse=True); pool=ranked[:max(2,min(7,len(ranked)))]
        scene=rng.choices([s for _,s in pool],weights=[max(.01,x) for x,_ in pool],k=1)[0]
        speed=rng.choice(([1.,1.12,1.22,.82] if p=="drop" else [1.,1.08,.9] if p=="build" else [1.]))
        dur=end-start; srcdur=min(scene.duration,dur*speed); room=max(0,scene.duration-srcdur); src=scene.start+(rng.random()*room if room else 0)
        effect=(rng.choice(["punch","flash","clean"]) if p=="hook" else "push" if p=="build" and idx%3==0 else rng.choice(["punch","flash","contrast","clean"]) if p=="drop" else "vignette" if p=="release" else "clean")
        shots.append(Shot(idx,scene.id,src,srcdur,start,dur,speed,p,effect,intensity)); recent.append(scene.id); last=scene
    if len(shots)>4:
        first=next(s for s in scenes if s.id==shots[0].scene_id); shots[-1].scene_id=first.id; shots[-1].source_start=min(first.end-shots[-1].source_duration,first.start+.08)
    return shots

def codec():
    check=subprocess.run([FFMPEG_BIN,"-hide_banner","-encoders"],capture_output=True,text=True)
    if check.returncode==0 and "h264_nvenc" in check.stdout: return ["-c:v","h264_nvenc","-preset","p5","-tune","hq","-rc","vbr","-cq","18","-b:v","0"]
    return ["-c:v","libx264","-preset","fast","-crf","18"]

def visual_filter(shot,w,h):
    zoom={"punch":1.10,"push":1.055}.get(shot.effect,1.025); sw=int(math.ceil(w*zoom/2)*2); sh=int(math.ceil(h*zoom/2)*2)
    chain=[f"scale={sw}:{sh}:force_original_aspect_ratio=increase",f"crop={w}:{h}","setsar=1",f"eq=contrast={1.09+shot.intensity*.08:.3f}:saturation={1.10+shot.intensity*.12:.3f}:brightness=0.006","unsharp=5:5:0.45:3:3:0.0"]
    if shot.effect=="flash": chain.append("fade=t=in:st=0:d=0.055:color=white")
    if shot.effect=="vignette": chain.append("vignette=PI/5")
    return ",".join(chain)

def render(video,music,shots,output,w,h,duration,workdir):
    progress(62,"render","Renderizando cortes e efeitos em 60 FPS"); chunks=[]; groups=math.ceil(len(shots)/10)
    for ci,offset in enumerate(range(0,len(shots),10)):
        group=shots[offset:offset+10]; filters=[]; labels=[]
        for i,shot in enumerate(group):
            filters.append(f"[0:v]trim=start={shot.source_start:.4f}:duration={shot.source_duration:.4f},setpts=(PTS-STARTPTS)/{shot.speed:.5f},{visual_filter(shot,w,h)},tpad=stop_mode=clone:stop_duration={shot.duration:.4f},trim=duration={shot.duration:.4f},setpts=PTS-STARTPTS,fps={FPS}[v{i}]"); labels.append(f"[v{i}]")
        graph=";".join(filters)+";"+"".join(labels)+f"concat=n={len(group)}:v=1:a=0[outv]"; chunk=os.path.join(workdir,f"chunk-{ci:03d}.mp4")
        run([FFMPEG_BIN,"-y","-i",video,"-filter_complex",graph,"-map","[outv]","-an",*codec(),"-pix_fmt","yuv420p",chunk],f"Renderizar bloco {ci+1}"); chunks.append(chunk)
        progress(62+int(24*(ci+1)/groups),"render",f"Bloco {ci+1} concluido")
    listing=os.path.join(workdir,"chunks.txt")
    with open(listing,"w",encoding="utf-8") as f:
        for chunk in chunks: f.write("file '"+chunk.replace("\\","/")+"'\n")
    progress(88,"finishing","Aplicando musica e acabamento final")
    run([FFMPEG_BIN,"-y","-f","concat","-safe","0","-i",listing,"-i",music,"-t",f"{duration:.4f}","-map","0:v:0","-map","1:a:0","-c:v","copy","-af","apad,alimiter=limit=0.95","-c:a","aac","-b:a","256k","-movflags","+faststart","-shortest",output],"Finalizar MP4")

def create_edit(video,audio,resolution,requested_duration,output):
    started=time.time(); requested_duration=max(3.,min(float(requested_duration),180.))
    try: w,h=(int(v) for v in resolution.lower().split("x"))
    except Exception: w,h=1080,1920
    os.makedirs(TEMP_ROOT,exist_ok=True); workdir=tempfile.mkdtemp(prefix="criator-",dir=TEMP_ROOT)
    seed=int(hashlib.sha256(f"{os.path.getsize(video)}:{os.path.getsize(audio)}:{requested_duration}:{time.time_ns()}".encode()).hexdigest()[:8],16)
    progress(4,"startup","Iniciando diretor local Phonk")
    try:
        if video_duration(video)<.25: raise RuntimeError("O video esta vazio ou corrompido.")
        duration=min(requested_duration,max(3.,probe_duration(audio))); amap=analyze_audio(audio,duration,workdir); scenes=analyze_scenes(video); shots=plan(scenes,amap,duration,seed)
        plan_path=os.path.splitext(output)[0]+".timeline.json"
        with open(plan_path,"w",encoding="utf-8") as f: json.dump({"version":1,"mode":"phonk","fps":FPS,"resolution":[w,h],"duration":duration,"audio_source_start":amap["source_start"],"tempo":amap["tempo"],"scenes":[asdict(s) for s in scenes],"shots":[asdict(s) for s in shots]},f,ensure_ascii=False,indent=2)
        render(video,amap["path"],shots,output,w,h,duration,workdir); measured=probe_duration(output)
        if abs(measured-duration)>max(.08,2/FPS): raise RuntimeError(f"Controle de qualidade rejeitou a duracao: esperado {duration:.3f}s, obtido {measured:.3f}s")
        progress(100,"completed",f"Edit pronto em {time.time()-started:.1f}s"); log("QUALITY",f"{len(shots)} cortes | {measured:.3f}s | {w}x{h} | 60 FPS")
    finally: shutil.rmtree(workdir,ignore_errors=True)
