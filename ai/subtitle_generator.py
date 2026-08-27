# -*- coding: utf-8 -*-
import os, platform, re
from typing import Dict, List, Tuple
from config import ASS_FONT_CANDIDATES, ASS_STYLE
from impact_scorer import ImpactScorer
from logger import log

PALETTE = {
    'base':       '&H00FFFFFF',
    'impact':     '&H00FF0000',
    'urgency':    '&H0000FFFF',
    'emotional':  '&H0000FF66',
    'surreal':    '&H00FF00FF',
    'reflection': '&H00FF6600',
    'silence':    '&H00888888',
}

def _font_exists_windows(font_name):
    windir = os.environ.get('WINDIR', r'C:\Windows')
    font_dir = os.path.join(windir, 'Fonts')
    if not os.path.isdir(font_dir):
        return False
    key = re.sub(r'[^a-z0-9]', '', font_name.lower())
    try:
        for f in os.listdir(font_dir):
            if key and key in re.sub(r'[^a-z0-9]', '', f.lower()):
                return True
    except OSError:
        return False
    return False

def resolve_font():
    for font in ASS_FONT_CANDIDATES:
        if font and platform.system().lower() == 'windows' and _font_exists_windows(font):
            return font
    return ASS_FONT_CANDIDATES[-1] if ASS_FONT_CANDIDATES else 'Arial'

def ass_time(sec):
    sec = max(0.0, float(sec or 0))
    h, m = int(sec//3600), int((sec%3600)//60)
    return f'{h}:{m:02d}:{sec%60:05.2f}'

def clean_text(t):
    t = str(t or '').strip()
    t = re.sub(r'\s+', ' ', t).replace('{','').replace('}','').replace('\\','')
    return t.upper()

class SubtitleGenerator:
    def __init__(self, style=None, timeline_state=None, flow_engine=None):
        self.style = dict(ASS_STYLE)
        if style:
            self.style.update(style)
        self.font_name = resolve_font()
        self.timeline = timeline_state
        self.flow = flow_engine

    def generate(self, words, output_path, width, height):
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        font_size = max(42, int(height * float(self.style['font_size_ratio'])))
        y_pos = int(height * float(self.style['y_position_ratio']))
        count = 0
        with open(output_path, 'w', encoding='utf-8') as f:
            self._write_header(f, width, height, font_size)
            f.write('[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
            for w in words:
                txt = clean_text(w.get('word',''))
                if not txt:
                    continue
                line = self._dialogue(w, txt, width, y_pos)
                if line:
                    f.write(line+'\n')
                    count += 1
        log('CAPTION', f'ASS gerado: {count} eventos | fonte {self.font_name}')
        return os.path.abspath(output_path), count

    def _write_header(self, f, w, h, fs):
        f.write('[Script Info]\nTitle: Criator Captions\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n')
        f.write(f'PlayResX: {w}\nPlayResY: {h}\n\n[V4+ Styles]\n')
        f.write('Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n')
        f.write(f'Style: Default,{self.font_name},{fs},{self.style["primary_color"]},{self.style["secondary_color"]},{self.style["outline_color"]},{self.style["shadow_color"]},1,0,0,0,100,100,0,0,1,{self.style["outline"]},{self.style["shadow"]},{self.style["alignment"]},0,0,0,1\n\n')

    def _dialogue(self, w, txt, width, y_pos):
        start = float(w.get('start',0) or 0)
        end = float(w.get('end', start+0.35) or start+0.35)
        if end <= start:
            end = start+0.35
        score = float(w.get('impact_score', w.get('viral_score',0.4)) or 0.4)
        rank = w.get('caption_rank') or ImpactScorer.rank_for_score(score)
        moment = w.get('moment_type','normal')
        color = self._color(rank, moment, float(start))
        tags = self._tags(rank, score, color, width, y_pos, float(start))
        return f'Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{tags}{txt}'

    def _color(self, rank, moment, time_sec):
        if moment == 'silence_reveal':
            return PALETTE['silence']
        if moment == 'music_peak':
            if self.timeline and self.timeline.phase == 'climax':
                return PALETTE['impact']
            return PALETTE['urgency']
        if rank == 'dominant':
            return PALETTE['urgency']
        if rank == 'secondary':
            return PALETTE['emotional']
        if self.timeline and self.timeline.phase == 'release':
            return PALETTE['silence']
        return PALETTE['base']

    def _tags(self, rank, score, color, width, y_pos, time_sec):
        x = width//2
        if rank == 'dominant':
            si = int(118+score*22)
            glow = r'\blur3\be2'
            anim = rf'\t(0,70,\fscx{si}\fscy{si})\t(70,160,\fscx104\fscy104)\t(160,260,\fscx100\fscy100)'
        elif rank == 'secondary':
            glow = r'\blur2'
            anim = r'\t(0,90,\fscx112\fscy112)\t(90,210,\fscx100\fscy100)'
        else:
            glow = ''
            anim = r'\t(0,120,\fscx104\fscy104)\t(120,240,\fscx100\fscy100)'
        return rf'{{\an5\pos({x},{y_pos})\c{color}{glow}{anim}}}'
