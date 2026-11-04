"""Closed yt-dlp preset options; no caller-supplied flags. GPL-3.0-or-later."""
import re
PRESETS={'best':'bestvideo+bestaudio/best','1080p':'bestvideo[height<=1080]+bestaudio/best[height<=1080]','audio-m4a':'bestaudio[ext=m4a]','audio-opus':'bestaudio[acodec^=opus]','subtitles':'bestvideo+bestaudio/best'}
def preset_options(preset,subtitle_lang=None):
    if preset is None:return {}
    if not isinstance(preset,str) or preset not in PRESETS:raise ValueError('Choose a supported download preset.')
    if subtitle_lang is not None and (not isinstance(subtitle_lang,str) or not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?',subtitle_lang)):raise ValueError('Invalid subtitle language.')
    if preset!='subtitles' and subtitle_lang is not None:raise ValueError('Subtitle language requires the subtitle preset.')
    out={'format':PRESETS[preset]}
    if preset=='subtitles':out.update(writesubtitles=True,writeautomaticsub=False,subtitleslangs=[subtitle_lang or 'en'],subtitlesformat='vtt/srt/best')
    return out
