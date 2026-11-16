# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_CLIP_V1 (D01): save only a part of a video ("from 1:20 to 3:45").

The GUI sends two plain time texts (m:ss, mm:ss or h:mm:ss); everything is checked here and turned into yt-dlp's
own download_ranges option, never into caller-supplied flags. Exact cuts need FFmpeg on the worker
(force_keyframes_at_cuts re-encodes around the cut points); without it the cut falls on the nearest keyframes and
the job's note says so.
"""
import re

MAX_END = 6 * 3600          # a clip may end at most 6 hours into the video
DURATION_SLACK = 1.0        # site durations are rounded; allow one second past the reported length

_MS = re.compile(r'(\d{1,3}):([0-5]\d)\Z')
_HMS = re.compile(r'(\d):([0-5]\d):([0-5]\d)\Z')


def parse_time(text, what='The time'):
    """'1:20' -> 80, '01:20' -> 80, '1:02:03' -> 3723. Raises ValueError for anything else."""
    if not isinstance(text, str) or len(text) > 9:
        raise ValueError(what + ' must look like 1:20 or 1:02:03.')
    value = text.strip(' ')
    m = _HMS.match(value)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = _MS.match(value)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    raise ValueError(what + ' must look like 1:20 or 1:02:03.')


def check_clip(start, end):
    """(start text, end text) from the form -> (start s, end s), or None when both are empty.
    An empty start means the very beginning; the end is required once a start is given."""
    empty = lambda v: v is None or (isinstance(v, str) and not v.strip())
    if empty(start) and empty(end):
        return None
    if empty(end):
        raise ValueError('Give the clip an end time (for example 3:45).')
    s = 0 if empty(start) else parse_time(start, 'The clip start')
    e = parse_time(end, 'The clip end')
    if e > MAX_END:
        raise ValueError('A clip must end within the first 6 hours.')
    if s >= e:
        raise ValueError('The clip must start before it ends.')
    return s, e


def stamp(seconds):
    """80 -> '1m20s', 3723 -> '1h02m03s' (file-name safe)."""
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return '%dh%02dm%02ds' % (h, m, s) if h else '%dm%02ds' % (m, s)


def suffix(clip):
    """' (clip 1m20s-3m45s)' for the file name; '' for a whole download."""
    return ' (clip %s-%s)' % (stamp(clip[0]), stamp(clip[1])) if clip else ''


def check_against_info(info, clip):
    """After yt-dlp read the link: no clips from live streams, and the clip must lie inside the video."""
    if not clip or not isinstance(info, dict):
        return
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming', 'post_live'):
        raise ValueError('Clips cannot be cut from a live stream. Save it after the stream has ended.')
    duration = info.get('duration')
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
        if clip[0] >= duration:
            raise ValueError('The clip starts after the video ends (it is %s long).' % stamp(duration))
        if clip[1] > duration + DURATION_SLACK:
            raise ValueError('The clip ends after the video ends (it is %s long).' % stamp(duration))


def ytdlp_options(clip, ffmpeg_available, range_func=None):
    """yt-dlp options for one clip; {} for a whole download."""
    if not clip:
        return {}
    if range_func is None:
        from yt_dlp.utils import download_range_func as range_func
    return dict(download_ranges=range_func(None, [(clip[0], clip[1])]), force_keyframes_at_cuts=bool(ffmpeg_available))


NO_FFMPEG = 'no FFmpeg on this worker for exact cuts'
KEYFRAME_CONTAINER = 'MKV and WebM files start at a keyframe'


def note(clip, ffmpeg_available, reason=NO_FFMPEG):
    """The sentence the finished job shows about its cut."""
    if not clip:
        return ''
    where = '%s to %s' % (stamp(clip[0]), stamp(clip[1]))
    if ffmpeg_available:
        return ' Clip %s, cut exactly.' % where
    return (' Clip %s, cut at the nearest keyframes (%s),'
            ' so it may start or end a few seconds off.' % (where, reason))


# OMNI_DL_FFMPEG_V1: the console worker has no ffmpeg program (it cannot start other programs), but its
# python-worker.elf links FFmpeg's libraries (minimal LGPL build, stream copy only). _omni_native.remux
# cuts, remuxes and tags local files in-process. An older worker without it keeps refusing clips.
def native_remux():
    """_omni_native.remux, or None when this worker has no in-process FFmpeg."""
    try:
        import _omni_native
    except ImportError:
        return None
    remux = getattr(_omni_native, 'remux', None)
    return remux if callable(remux) else None


_META_FIELDS = (('title', 'title'), ('artist', 'uploader'), ('artist', 'channel'), ('comment', 'webpage_url'))
_CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')


def media_metadata(info):
    """Container tags written into a file the worker remuxes (as yt-dlp's FFmpegMetadata would):
    title, artist, date (YYYYMMDD -> YYYY-MM-DD) and the page link as comment. Text only, bounded."""
    tags = {}
    if not isinstance(info, dict):
        return tags
    for tag, field in _META_FIELDS:
        value = info.get(field)
        if tag not in tags and isinstance(value, str) and value.strip():
            tags[tag] = _CONTROL.sub('', value).strip()[:500]
    date = info.get('upload_date')
    if isinstance(date, str) and re.fullmatch(r'\d{8}', date):
        tags['date'] = '%s-%s-%s' % (date[:4], date[4:6], date[6:])
    return tags


def cut_targets(source, container=None, audio=False):
    """File types to try for a remuxed/cut copy of source, best first. MP4/M4A keep an exact clip start
    (an edit list hides the lead-in from the keyframe); MKV takes every codec. A type the user chose wins."""
    ext = str(source).rsplit('.', 1)[-1].lower() if '.' in str(source) else ''
    if audio or ext in ('m4a', 'aac', 'mp3', 'opus', 'ogg'):
        return ['m4a', 'mka'] if ext in ('m4a', 'aac') else ['mka']
    if container == 'mkv':
        return ['mkv']
    return ['mp4', 'mkv']
