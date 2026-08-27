# -*- coding: utf-8 -*-
from config import EFFECT_FATIGUE
_usage_count = {}
def _fatigue_penalty(effect_name):
    count = _usage_count.get(effect_name, 0)
    cooldown = EFFECT_FATIGUE.get(effect_name, 2.0)
    return min(0.95, count * cooldown * 0.15)
def _record_use(effect_name):
    _usage_count[effect_name] = _usage_count.get(effect_name, 0) + 1
def flash_filter(intensity, beat_type, duration, fps):
    if beat_type == "kick" and intensity > 0.85:
        if _fatigue_penalty("flash") > 0.7: return None
        _record_use("flash")
        frames = min(int(duration * fps * 0.3), 4)
        return f"eq=brightness=1.5:contrast=1.3:enable='between(n,0,{frames})'"
    return None
def shake_filter(intensity, beat_type, duration, width, height):
    if beat_type == "kick" and intensity > 0.8:
        if _fatigue_penalty("shake") > 0.6: return None
        _record_use("shake")
        amp = int(6 + intensity * 10)
        return f"crop={width-amp*2}:{height-amp*2}:{amp}*sin(n*0.5)+{amp}:{amp}*cos(n*0.7)+{amp}"
    return None
def speed_filter(beat_type, intensity):
    if _fatigue_penalty("speed_ramp") > 0.65: return None
    _record_use("speed_ramp")
    if beat_type == "kick" and intensity > 0.85: return "setpts='if(lt(T,0.08),0.3*PTS,if(lt(T,0.2),0.7*PTS,1.2*PTS))'"
    elif beat_type == "bass" and intensity > 0.7: return "setpts='1.4*PTS'"
    elif beat_type == "snare": return "setpts='0.75*PTS'"
    return None
def zoom_filter(intensity, beat_type, width, height):
    if beat_type == "kick" and intensity > 0.75:
        if _fatigue_penalty("zoom") > 0.6: return None
        _record_use("zoom")
        z = min(1.0 + intensity * 0.2, 1.3)
        return f"scale=iw*{z:.2f}:ih*{z:.2f},crop={width}:{height}"
    return None
