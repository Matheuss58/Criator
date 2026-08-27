# -*- coding: utf-8 -*-
from typing import Dict, List, Tuple
from impact_scorer import ImpactScorer
from logger import log
from subtitle_generator import SubtitleGenerator

class CaptionEngine:
    def __init__(self, music_engine=None, narrative_engine=None, viral_engine=None,
                 timeline_state=None, flow_engine=None):
        self.music_engine = music_engine
        self.narrative_engine = narrative_engine
        self.viral_engine = viral_engine
        self.timeline = timeline_state
        self.flow = flow_engine
        self.scorer = ImpactScorer(music_engine, narrative_engine, timeline_state)
        self.generator = SubtitleGenerator(timeline_state=timeline_state, flow_engine=flow_engine)

    def score_words(self, words):
        scored = self.scorer.analyze_words(words or [])
        if self.viral_engine is not None: self.viral_engine.set_scored_words(scored)
        return scored

    def generate_ass(self, words, output_path, width=1080, height=1920):
        if not words: raise RuntimeError('Nao ha palavras para gerar legenda.')
        scored = self.score_words(words)
        path, count = self.generator.generate(scored, output_path, width, height)
        log('CAPTION', f'Legenda ASS pronta: {count} palavras')
        return path, count
