"""OMNI_DOWNLOADS_PROBE_V5: check a grabbed media link before it is downloaded.

Reads only as much of a link as it takes to say what it really is: an HLS or
DASH manifest (every quality, codec, audio language and subtitle), or a direct
file (container, size, duration, resolution, codecs). It never downloads media
and never tries to get around DRM: protected streams are reported as such.

Safety: only public http(s) hosts. Every hostname is resolved first and the
connection is pinned to the checked address (no DNS rebinding); loopback,
private, link-local, shared, multicast and reserved addresses are refused,
on every redirect hop too. Reads are capped and time-limited. The deep (site
extractor) check runs yt-dlp through egress_guard, which applies the same
policy to every connection yt-dlp makes (audit DW-01).
"""
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import struct
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ElementTree

from egress_guard import resolve_within, shared_guard  # OMNI_EGRESS_GUARD_V1 (audit DW-01/DW-02)

USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
              '(KHTML, like Gecko) Version/17.0 Safari/605.1.15')
DEADLINE = 8.0            # seconds per probe (whole probe, all requests)
SOCKET_TIMEOUT = 6.0
MAX_REDIRECTS = 5
HEAD_BYTES = 256 * 1024   # first read of any link
MANIFEST_BYTES = 2 * 1024 * 1024
MOOV_BYTES = 8 * 1024 * 1024
CACHE_SECONDS = 300
CACHE_SIZE = 256
PARALLEL = 3
SITE_TIMEOUT = 20.0
DRM_KEYFORMATS = ('com.apple.streamingkeydelivery', 'com.widevine', 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed',
                  'com.microsoft.playready', 'urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95')
SHARED = ipaddress.ip_network('100.64.0.0/10')


class Refused(Exception):
    """The link points somewhere the probe must not go."""


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def public_address(host, port):
    """Resolve host; refuse unless every address is a public unicast address."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError) as error:
        raise Problem('dead', "The site's address could not be found.") from error
    chosen = None
    for family, _, _, _, sockaddr in infos:
        address = ipaddress.ip_address(sockaddr[0].split('%', 1)[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast
                or address.is_reserved or address.is_unspecified or address in SHARED
                or (isinstance(address, ipaddress.IPv6Address) and (address.is_site_local or address.teredo or address.sixtofour))):
            raise Refused('Local or private address')
        if chosen is None:
            chosen = (family, sockaddr[0], sockaddr[1])
    if chosen is None:
        raise Problem('dead', "The site's address could not be found.")
    return chosen


def check_url(url):
    if not isinstance(url, str) or not url or len(url) > 4096:
        raise Refused('Not a link')
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise Refused('Only http and https links are checked')
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url) or '\\' in url:
        raise Refused('Not a link')
    try:
        port = parts.port or (443 if parts.scheme == 'https' else 80)
    except ValueError as error:
        raise Refused('Bad port') from error
    return parts, port


class _Pinned(http.client.HTTPConnection):
    def __init__(self, host, address, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self):
        self.sock = socket.create_connection((self._address[1], self.port), self.timeout)


class _PinnedTLS(http.client.HTTPSConnection):
    def __init__(self, host, address, port, timeout, context):
        super().__init__(host, port, timeout=timeout, context=context)
        self._address = address
        self._tls = context

    def connect(self):
        raw = socket.create_connection((self._address[1], self.port), self.timeout)
        self.sock = self._tls.wrap_socket(raw, server_hostname=self.host)


_context = None


def tls_context():
    global _context
    if _context is None:
        _context = ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE') or None)
    return _context


class Fetcher:
    """Bounded GETs with manual, re-checked redirects and a whole-probe deadline."""

    def __init__(self, referer=None, deadline=DEADLINE, resolver=public_address):
        self.referer = referer
        self.until = time.monotonic() + deadline
        self.resolver = resolver
        self.requests = 0

    def left(self):
        remaining = self.until - time.monotonic()
        if remaining <= 0:
            raise Problem('slow', 'The site took too long to answer.')
        return remaining

    def get(self, url, limit, start=None, end=None):
        """Return (final_url, status, headers, body, total_size)."""
        for _ in range(MAX_REDIRECTS + 1):
            parts, port = check_url(url)
            try:  # DW-02: the lookup counts against the probe deadline
                address = resolve_within(self.resolver, parts.hostname, port, min(SOCKET_TIMEOUT, self.left()))
            except TimeoutError as error:
                raise Problem('slow', 'The site took too long to answer.') from error
            timeout = min(SOCKET_TIMEOUT, self.left())
            if parts.scheme == 'https':
                connection = _PinnedTLS(parts.hostname, address, port, timeout, tls_context())
            else:
                connection = _Pinned(parts.hostname, address, port, timeout)
            path = urllib.parse.urlunsplit(('', '', parts.path or '/', parts.query, ''))
            headers = {'User-Agent': USER_AGENT, 'Accept': '*/*', 'Accept-Encoding': 'identity', 'Connection': 'close'}
            if self.referer:
                headers['Referer'] = self.referer
            if start is not None:
                headers['Range'] = f'bytes={start}-{"" if end is None else end}'
            self.requests += 1
            try:
                connection.request('GET', path, headers=headers)
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location:
                        raise Problem('error', 'The site redirected without saying where.')
                    url = urllib.parse.urljoin(url, location.strip())
                    continue
                body = bytearray()
                while len(body) < limit:
                    self.left()
                    chunk = response.read(min(64 * 1024, limit - len(body)))
                    if not chunk:
                        break
                    body.extend(chunk)
                total = None
                content_range = response.getheader('Content-Range') or ''
                match = re.match(r'bytes\s+\d+-\d+/(\d+)', content_range)
                if match:
                    total = int(match.group(1))
                elif response.status == 200 and (response.getheader('Content-Length') or '').isdigit():
                    total = int(response.getheader('Content-Length'))
                return url, response.status, response.headers, bytes(body), total
            except (ssl.SSLError, ssl.CertificateError) as error:
                raise Problem('error', "The site's secure connection could not be verified.") from error
            except (socket.timeout, TimeoutError) as error:
                raise Problem('slow', 'The site took too long to answer.') from error
            except (ConnectionError, OSError, http.client.HTTPException) as error:
                raise Problem('error', 'The site could not be reached.') from error
            finally:
                connection.close()
        raise Problem('error', 'Too many redirects.')


# ---- readable names ------------------------------------------------------------------------
def codec_name(code):
    c = (code or '').strip().lower()
    if not c:
        return ''
    table = (('avc1', 'H.264'), ('avc3', 'H.264'), ('h264', 'H.264'), ('v_mpeg4/iso/avc', 'H.264'),
             ('hvc1', 'HEVC'), ('hev1', 'HEVC'), ('h265', 'HEVC'), ('hevc', 'HEVC'), ('v_mpegh/iso/hevc', 'HEVC'),
             ('dvh1', 'Dolby Vision'), ('dvhe', 'Dolby Vision'), ('vp09', 'VP9'), ('vp9', 'VP9'), ('v_vp9', 'VP9'),
             ('vp8', 'VP8'), ('v_vp8', 'VP8'), ('av01', 'AV1'), ('av1', 'AV1'), ('v_av1', 'AV1'),
             ('mp4a.40.5', 'HE-AAC'), ('mp4a.40.29', 'HE-AAC'), ('mp4a.40.34', 'MP3'), ('mp4a.6b', 'MP3'),
             ('mp4a', 'AAC'), ('aac', 'AAC'), ('a_aac', 'AAC'), ('ec-3', 'Dolby Digital Plus'), ('eac3', 'Dolby Digital Plus'),
             ('ac-3', 'Dolby Digital'), ('ac3', 'Dolby Digital'), ('opus', 'Opus'), ('a_opus', 'Opus'),
             ('vorbis', 'Vorbis'), ('a_vorbis', 'Vorbis'), ('flac', 'FLAC'), ('mp3', 'MP3'), ('a_mpeg/l3', 'MP3'),
             ('wvtt', 'WebVTT'), ('stpp', 'TTML'))
    for prefix, name in table:
        if c.startswith(prefix):
            return name
    return code.split('.', 1)[0][:16]


VIDEO_CODECS = {'H.264', 'HEVC', 'Dolby Vision', 'VP9', 'VP8', 'AV1'}
AUDIO_CODECS = {'AAC', 'HE-AAC', 'MP3', 'Dolby Digital Plus', 'Dolby Digital', 'Opus', 'Vorbis', 'FLAC'}


def split_codecs(value):
    video, audio = '', ''
    for part in (value or '').split(','):
        name = codec_name(part)
        if name in VIDEO_CODECS and not video:
            video = name
        elif name in AUDIO_CODECS and not audio:
            audio = name
    return video, audio


def result(status, message='', **values):
    value = dict(status=status, ok=status == 'ok', message=message, kind=None, container=None, duration=None,
                 size=None, size_estimated=False, video=None, audio=None, variants=[], audio_tracks=[],
                 subtitles=[], encrypted='none', source='parse', title=None)
    value.update(values)
    return value


# ---- HLS ---------------------------------------------------------------------------------
_ATTR = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def attributes(line):
    return {key: value.strip('"') for key, value in _ATTR.findall(line.split(':', 1)[1] if ':' in line else '')}


def key_state(lines):
    state = 'none'
    for line in lines:
        if line.startswith('#EXT-X-KEY') or line.startswith('#EXT-X-SESSION-KEY'):
            values = attributes(line)
            method = values.get('METHOD', 'NONE').upper()
            keyformat = values.get('KEYFORMAT', 'identity').lower()
            if method == 'NONE':
                continue
            if method.startswith('SAMPLE-AES') or keyformat != 'identity' or any(keyformat.startswith(k) for k in DRM_KEYFORMATS):
                return 'drm'
            state = 'aes-128'
    return state


def media_playlist(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    duration = 0.0
    segments = 0
    for line in lines:
        if line.startswith('#EXTINF:'):
            try:
                duration += float(line[8:].split(',', 1)[0])
            except ValueError:
                pass
            segments += 1
    return dict(duration=round(duration, 3), segments=segments, live='#EXT-X-ENDLIST' not in lines,
                encrypted=key_state(lines), vod='#EXT-X-PLAYLIST-TYPE:VOD' in lines)


def parse_hls(text, url, fetch_media):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].startswith('#EXTM3U'):
        raise Problem('error', 'Not a valid HLS playlist.')
    variants, audio_tracks, subtitles = [], [], []
    for index, line in enumerate(lines):
        if line.startswith('#EXT-X-STREAM-INF'):
            values = attributes(line)
            uri = next((item for item in lines[index + 1:] if not item.startswith('#')), None)
            width = height = None
            if 'RESOLUTION' in values and 'x' in values['RESOLUTION']:
                try:
                    width, height = (int(v) for v in values['RESOLUTION'].lower().split('x', 1))
                except ValueError:
                    pass
            try:
                fps = round(float(values['FRAME-RATE'])) if 'FRAME-RATE' in values else None
            except ValueError:
                fps = None
            video, audio = split_codecs(values.get('CODECS'))
            bandwidth = values.get('AVERAGE-BANDWIDTH') or values.get('BANDWIDTH')
            variants.append(dict(width=width, height=height, fps=fps, vcodec=video, acodec=audio,
                                 bandwidth=int(bandwidth) if (bandwidth or '').isdigit() else None,
                                 audio_group=values.get('AUDIO'), uri=urllib.parse.urljoin(url, uri) if uri else None))
        elif line.startswith('#EXT-X-MEDIA'):
            values = attributes(line)
            kind = values.get('TYPE', '').upper()
            entry = dict(lang=values.get('LANGUAGE') or '', name=values.get('NAME') or '',
                         default=values.get('DEFAULT', 'NO').upper() == 'YES', group=values.get('GROUP-ID'))
            if kind == 'AUDIO':
                audio_tracks.append(entry)
            elif kind == 'SUBTITLES':
                subtitles.append(dict(lang=entry['lang'], name=entry['name']))
    encrypted = key_state(lines)
    if variants:
        media_url = max(variants, key=lambda v: v['bandwidth'] or 0)['uri']
        info = fetch_media(media_url) if media_url else None
    else:
        info = media_playlist(text)
    if info:
        if info['encrypted'] == 'drm' or encrypted == 'drm':
            encrypted = 'drm'
        elif info['encrypted'] == 'aes-128':
            encrypted = 'aes-128'
    duration = info['duration'] if info else None
    if encrypted == 'drm':
        return result('protected', "Protected stream (DRM). It can't be downloaded.", kind='hls', container='HLS', encrypted='drm')
    if info and info['live'] and not info['vod']:
        return result('live', "Live stream. Omni can't save live streams yet.", kind='hls', container='HLS',
                      variants=_variant_list(variants, None), audio_tracks=_audio_list(audio_tracks), subtitles=subtitles)
    out = _variant_list(variants, duration)
    best = out[0] if out else None
    group_codecs = {v['audio_group']: v['acodec'] for v in variants if v.get('audio_group') and v.get('acodec')}
    value = result('ok', '', kind='hls', container='HLS', duration=duration, encrypted=encrypted,
                   variants=out, audio_tracks=_audio_list(audio_tracks, group_codecs), subtitles=subtitles,
                   size=best['size'] if best else None, size_estimated=bool(best and best['size']))
    if best:
        value['video'] = {k: best[k] for k in ('width', 'height', 'fps', 'vcodec')} if best.get('height') or best.get('vcodec') else None
        value['audio'] = {'codec': best['acodec']} if best.get('acodec') else None
    return value


def _variant_list(variants, duration):
    seen = {}
    for v in variants:
        key = (v['height'], v['fps']) if v['height'] else ('bw', v['bandwidth'])
        if key not in seen or (v['bandwidth'] or 0) > (seen[key]['bandwidth'] or 0):
            seen[key] = v
    out = []
    for v in seen.values():
        size = int(v['bandwidth'] * duration / 8) if v['bandwidth'] and duration else None
        out.append(dict(width=v['width'], height=v['height'], fps=v['fps'], vcodec=v['vcodec'], acodec=v['acodec'],
                        bandwidth=v['bandwidth'], size=size, audio_group=v.get('audio_group')))
    out.sort(key=lambda v: ((v['height'] or 0), (v['fps'] or 0), (v['bandwidth'] or 0)), reverse=True)
    return out[:16]


def _audio_list(tracks, group_codecs=None):
    out, seen = [], set()
    for t in tracks:
        key = (t['lang'].lower(), t['name'])
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(lang=t['lang'], name=t['name'], default=t['default'],
                        codec=(group_codecs or {}).get(t.get('group'), '')))
    return out[:12]


# ---- DASH --------------------------------------------------------------------------------
def iso_duration(value):
    match = re.fullmatch(r'P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?', (value or '').strip())
    if not match or not any(match.groups()):
        return None
    days, hours, minutes, seconds = (float(x) if x else 0.0 for x in match.groups())
    return round(days * 86400 + hours * 3600 + minutes * 60 + seconds, 3)


def parse_dash(data):
    if b'<!DOCTYPE' in data[:2048].upper() or b'<!ENTITY' in data.upper():
        raise Problem('error', 'The DASH manifest uses features Omni does not read.')
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise Problem('error', 'Not a valid DASH manifest.') from error
    except ImportError as error:  # no XML parser in this runtime: say so instead of failing the worker
        raise Problem('error', 'DASH details are not readable on this console.') from error

    def local(tag):
        return tag.rsplit('}', 1)[-1]
    if local(root.tag) != 'MPD':
        raise Problem('error', 'Not a valid DASH manifest.')
    if any(local(e.tag) == 'ContentProtection' for e in root.iter()):
        return result('protected', "Protected stream (DRM). It can't be downloaded.", kind='dash', container='DASH', encrypted='drm')
    if (root.get('type') or 'static') == 'dynamic':
        return result('live', "Live stream. Omni can't save live streams yet.", kind='dash', container='DASH')
    duration = iso_duration(root.get('mediaPresentationDuration'))
    videos, audios, subtitles = [], [], []
    for adaptation in (e for e in root.iter() if local(e.tag) == 'AdaptationSet'):
        base = dict(adaptation.attrib)
        for rep in (e for e in adaptation if local(e.tag) == 'Representation'):
            a = {**base, **rep.attrib}
            mime = (a.get('mimeType') or '') + ' ' + (a.get('contentType') or '')
            codec = codec_name(a.get('codecs'))
            bw = int(a['bandwidth']) if (a.get('bandwidth') or '').isdigit() else None
            if 'video' in mime or codec in VIDEO_CODECS:
                fps = a.get('frameRate')
                try:
                    fps = round(eval_rate(fps)) if fps else None
                except (ValueError, ZeroDivisionError):
                    fps = None
                videos.append(dict(width=_int(a.get('width')), height=_int(a.get('height')), fps=fps, vcodec=codec, bandwidth=bw))
            elif 'audio' in mime or codec in AUDIO_CODECS:
                audios.append(dict(lang=a.get('lang') or '', name=a.get('label') or '', codec=codec, bandwidth=bw, default=False))
            elif 'text' in mime or codec in ('WebVTT', 'TTML'):
                subtitles.append(dict(lang=a.get('lang') or '', name=a.get('label') or ''))
    best_audio = max(audios, key=lambda a: a['bandwidth'] or 0) if audios else None
    variants = []
    for v in videos:
        total_bw = (v['bandwidth'] or 0) + (best_audio['bandwidth'] or 0 if best_audio else 0)
        variants.append(dict(width=v['width'], height=v['height'], fps=v['fps'], vcodec=v['vcodec'],
                             acodec=best_audio['codec'] if best_audio else '', bandwidth=total_bw or None, audio_group=None,
                             size=int(total_bw * duration / 8) if total_bw and duration else None))
    dedup = {}
    for v in variants:
        key = (v['height'], v['fps'], v['vcodec'])
        if key not in dedup or (v['bandwidth'] or 0) > (dedup[key]['bandwidth'] or 0):
            dedup[key] = v
    variants = sorted(dedup.values(), key=lambda v: ((v['height'] or 0), (v['fps'] or 0), (v['bandwidth'] or 0)), reverse=True)[:16]
    tracks, seen = [], set()
    for a in sorted(audios, key=lambda a: a['bandwidth'] or 0, reverse=True):
        key = (a['lang'].lower(), a['name'])
        if key not in seen:
            seen.add(key)
            tracks.append(dict(lang=a['lang'], name=a['name'], codec=a['codec'], default=False))
    best = variants[0] if variants else None
    value = result('ok', '', kind='dash', container='DASH', duration=duration, variants=variants, audio_tracks=tracks[:12],
                   subtitles=subtitles[:12], size=best['size'] if best else (int(best_audio['bandwidth'] * duration / 8) if best_audio and best_audio['bandwidth'] and duration else None))
    value['size_estimated'] = value['size'] is not None
    if best:
        value['video'] = {k: best[k] for k in ('width', 'height', 'fps', 'vcodec')}
    if best_audio:
        value['audio'] = {'codec': best_audio['codec']}
    return value


def eval_rate(value):
    if '/' in value:
        top, bottom = value.split('/', 1)
        return float(top) / float(bottom)
    return float(value)


def _int(value):
    return int(value) if (value or '').isdigit() else None


# ---- MP4 ---------------------------------------------------------------------------------
def boxes(data, start=0, end=None):
    end = len(data) if end is None else end
    offset = start
    while offset + 8 <= end:
        size, kind = struct.unpack('>I4s', data[offset:offset + 8])
        header = 8
        if size == 1:
            if offset + 16 > end:
                return
            size = struct.unpack('>Q', data[offset + 8:offset + 16])[0]
            header = 16
        elif size == 0:
            size = end - offset
        if size < header:
            return
        yield kind.decode('latin-1'), offset, offset + header, offset + size
        offset += size


def top_level(data, base=0):
    """Yield top-level boxes even when the data is cut off (sizes beyond the buffer are kept)."""
    offset = 0
    while offset + 8 <= len(data):
        size, kind = struct.unpack('>I4s', data[offset:offset + 8])
        header = 8
        if size == 1:
            if offset + 16 > len(data):
                return
            size = struct.unpack('>Q', data[offset + 8:offset + 16])[0]
            header = 16
        if size and size < header:
            return
        yield kind.decode('latin-1'), base + offset, header, size
        if not size:
            return
        offset += size


def parse_moov(moov):
    info = dict(duration=None, video=None, audio=None, encrypted='none')
    for kind, _, body, end in boxes(moov):
        if kind == 'mvhd':
            version = moov[body]
            if version == 1 and end - body >= 32:
                timescale, duration = struct.unpack('>IQ', moov[body + 20:body + 32])
            elif end - body >= 20:
                timescale, duration = struct.unpack('>II', moov[body + 12:body + 20])
            else:
                continue
            if timescale and duration and duration != 0xFFFFFFFF:
                info['duration'] = round(duration / timescale, 3)
        elif kind == 'pssh':
            info['encrypted'] = 'drm'
        elif kind == 'trak':
            track = parse_trak(moov, body, end)
            if track.get('encrypted'):
                info['encrypted'] = 'drm'
            if track.get('handler') == 'vide' and not info['video']:
                info['video'] = dict(width=track.get('width'), height=track.get('height'), fps=None, vcodec=track.get('codec', ''))
            elif track.get('handler') == 'soun' and not info['audio']:
                info['audio'] = dict(codec=track.get('codec', ''))
    return info


def parse_trak(data, start, end):
    out = {}
    for kind, _, body, stop in boxes(data, start, end):
        if kind == 'tkhd':
            version = data[body]
            offset = body + (88 if version == 1 else 76)
            if offset + 8 <= stop:
                width, height = struct.unpack('>II', data[offset:offset + 8])
                out['width'], out['height'] = width >> 16 or None, height >> 16 or None
        elif kind == 'mdia':
            for k2, _, b2, e2 in boxes(data, body, stop):
                if k2 == 'hdlr' and b2 + 12 <= e2:
                    out['handler'] = data[b2 + 8:b2 + 12].decode('latin-1')
                elif k2 == 'minf':
                    for k3, _, b3, e3 in boxes(data, b2, e2):
                        if k3 == 'stbl':
                            for k4, _, b4, e4 in boxes(data, b3, e3):
                                if k4 == 'stsd' and b4 + 16 <= e4:
                                    fourcc = data[b4 + 12:b4 + 16].decode('latin-1')
                                    if fourcc in ('encv', 'enca'):
                                        out['encrypted'] = True
                                    out['codec'] = codec_name(fourcc) if fourcc not in ('encv', 'enca') else ''
    return out


def mp4_info(fetcher, url, head, total):
    """Find moov at the start, or after mdat, with at most two extra ranged reads."""
    for kind, offset, header, size in top_level(head):
        if kind == 'moov':
            if offset + size <= len(head):
                return parse_moov(head[offset + header:offset + size])
            if size <= MOOV_BYTES:
                _, status, _, body, _ = fetcher.get(url, size, offset, offset + size - 1)
                if status == 206 and len(body) >= size:
                    return parse_moov(body[header:size])
            return None
        if kind == 'mdat':
            after = offset + size if size else None
            if after is None or (total and after >= total):
                return None
            _, status, _, peek, _ = fetcher.get(url, 16, after, after + 15)
            if status != 206 or len(peek) < 8:
                return None
            moov_size, moov_kind = struct.unpack('>I4s', peek[:8])
            if moov_kind != b'moov':
                return None
            header = 8
            if moov_size == 1 and len(peek) >= 16:
                moov_size, header = struct.unpack('>Q', peek[8:16])[0], 16
            if not header <= moov_size <= MOOV_BYTES:
                return None
            _, status, _, body, _ = fetcher.get(url, moov_size, after, after + moov_size - 1)
            if status == 206 and len(body) >= moov_size:
                return parse_moov(body[header:moov_size])
            return None
    return None


# ---- WebM / Matroska ---------------------------------------------------------------------
def _vint(data, offset, keep_marker=False):
    if offset >= len(data):
        raise IndexError
    first = data[offset]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8 or offset + length > len(data):
        raise IndexError
    value = first if keep_marker else first & (mask - 1)
    unknown = (first & (mask - 1)) == mask - 1
    for b in data[offset + 1:offset + length]:
        value = (value << 8) | b
        unknown = unknown and b == 0xFF
    return value, length, unknown


def webm_info(data):
    info = dict(duration=None, video=None, audio=None, encrypted='none', doctype=None)

    def walk(start, end, depth):
        offset = start
        scale = 1_000_000
        duration = None
        while offset < end:
            try:
                element, idlen, _ = _vint(data, offset, keep_marker=True)
                size, sizelen, unknown = _vint(data, offset + idlen)
            except IndexError:
                return scale, duration
            body = offset + idlen + sizelen
            stop = end if unknown else min(end, body + size)
            if element == 0x4282:
                info['doctype'] = data[body:stop].decode('latin-1', 'replace').strip('\x00')
            elif element in (0x1A45DFA3, 0x18538067, 0x1654AE6B, 0xAE, 0x5035):
                if element == 0x5035:
                    info['encrypted'] = 'drm'
                if element == 0xAE:
                    track(body, stop)
                else:
                    walk(body, stop, depth + 1)
            elif element == 0x1549A966:
                s, d = walk(body, stop, depth + 1)
                scale = s
                if d is not None:
                    info['duration'] = round(d * s / 1e9, 3)
            elif element == 0x2AD7B1:
                scale = int.from_bytes(data[body:stop], 'big') or scale
            elif element == 0x4489:
                if stop - body == 4:
                    duration = struct.unpack('>f', data[body:stop])[0]
                elif stop - body == 8:
                    duration = struct.unpack('>d', data[body:stop])[0]
            elif element == 0x1F43B675:
                return scale, duration
            if unknown:
                return scale, duration
            offset = stop
        return scale, duration

    def track(start, end):
        offset, kind, codec, width, height = start, None, '', None, None
        while offset < end:
            try:
                element, idlen, _ = _vint(data, offset, keep_marker=True)
                size, sizelen, _ = _vint(data, offset + idlen)
            except IndexError:
                break
            body = offset + idlen + sizelen
            stop = min(end, body + size)
            if element == 0x83:
                kind = int.from_bytes(data[body:stop], 'big')
            elif element == 0x86:
                codec = codec_name(data[body:stop].decode('latin-1', 'replace'))
            elif element == 0xE0:
                inner = body
                while inner < stop:
                    try:
                        e2, l2, _ = _vint(data, inner, keep_marker=True)
                        s2, sl2, _ = _vint(data, inner + l2)
                    except IndexError:
                        break
                    b2 = inner + l2 + sl2
                    if e2 == 0xB0:
                        width = int.from_bytes(data[b2:b2 + s2], 'big')
                    elif e2 == 0xBA:
                        height = int.from_bytes(data[b2:b2 + s2], 'big')
                    inner = b2 + s2
            elif element == 0x6D80 and b'\x50\x35' in data[body:stop]:
                info['encrypted'] = 'drm'  # ContentEncryption inside ContentEncodings
            offset = stop
        if kind == 1 and not info['video']:
            info['video'] = dict(width=width, height=height, fps=None, vcodec=codec)
        elif kind == 2 and not info['audio']:
            info['audio'] = dict(codec=codec)

    walk(0, len(data), 0)
    return info


# ---- the probe ---------------------------------------------------------------------------
CONTAINERS = (('video/mp4', 'MP4'), ('audio/mp4', 'M4A'), ('video/webm', 'WebM'), ('audio/webm', 'WebM'),
              ('video/x-matroska', 'MKV'), ('video/mp2t', 'MPEG-TS'), ('audio/mpeg', 'MP3'), ('audio/aac', 'AAC'),
              ('video/quicktime', 'MOV'), ('audio/ogg', 'Ogg'), ('audio/flac', 'FLAC'), ('audio/wav', 'WAV'),
              ('video/x-flv', 'FLV'))


def probe_url(url, referer=None, resolver=public_address):
    try:
        fetcher = Fetcher(referer, resolver=resolver)
        final, status, headers, head, total = fetcher.get(url, HEAD_BYTES, 0, HEAD_BYTES - 1)
        if status in (401, 403):
            return result('blocked', "The site refused the request. It may need the page's sign-in or cookies.")
        if status in (404, 410):
            return result('dead', 'Dead link: the file is gone.')
        if status == 416:
            final, status, headers, head, total = fetcher.get(url, HEAD_BYTES)
        if status >= 400:
            return result('error', f'The site answered with an error (HTTP {status}).')
        content_type = (headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
        start = head.lstrip(b'\xef\xbb\xbf \t\r\n')[:16]
        if start.startswith(b'#EXTM3U') or 'mpegurl' in content_type:
            if status == 206 and total and total > len(head):
                final, status, headers, head, total = fetcher.get(final, MANIFEST_BYTES)
            text = head.decode('utf-8', 'replace')

            def fetch_media(media_url):
                _, s, _, body, _ = fetcher.get(media_url, MANIFEST_BYTES)
                if s >= 400:
                    return None
                return media_playlist(body.decode('utf-8', 'replace'))
            return parse_hls(text, final, fetch_media)
        if 'dash+xml' in content_type or b'<MPD' in head[:4096]:
            if status == 206 and total and total > len(head):
                final, status, headers, head, total = fetcher.get(final, MANIFEST_BYTES)
            return parse_dash(head)
        if content_type in ('text/html', 'application/xhtml+xml') or head.lstrip()[:15].lower().startswith((b'<!doctype html', b'<html')):
            return result('page', 'A web page, not a media file.', kind='page')
        container = next((name for prefix, name in CONTAINERS if content_type.startswith(prefix)), None)
        if head[4:8] == b'ftyp' or head[4:8] in (b'moov', b'mdat', b'free', b'wide'):
            brand = head[8:12]
            container = 'M4A' if brand in (b'M4A ', b'M4B ') else 'MOV' if brand == b'qt  ' else 'MP4'
            info = mp4_info(fetcher, final, head, total) or {}
            if info.get('encrypted') == 'drm':
                return result('protected', "Protected file (DRM). It can't be downloaded.", kind='file', container=container, encrypted='drm')
            return result('ok', '', kind='file', container=container, size=total, duration=info.get('duration'),
                          video=info.get('video'), audio=info.get('audio'))
        if head[:4] == b'\x1a\x45\xdf\xa3':
            info = webm_info(head)
            container = 'WebM' if (info.get('doctype') or '').lower() == 'webm' else 'MKV'
            if info.get('encrypted') == 'drm':
                return result('protected', "Protected file (DRM). It can't be downloaded.", kind='file', container=container, encrypted='drm')
            return result('ok', '', kind='file', container=container, size=total, duration=info.get('duration'),
                          video=info.get('video'), audio=info.get('audio'))
        if head[:1] == b'\x47' and len(head) > 376 and head[188:189] == b'\x47' and head[376:377] == b'\x47':
            return result('ok', '', kind='file', container='MPEG-TS', size=total)
        if head[:3] == b'ID3' or head[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'):
            return result('ok', '', kind='file', container='MP3', size=total, audio={'codec': 'MP3'})
        if container:
            return result('ok', '', kind='file', container=container, size=total)
        if content_type.startswith(('video/', 'audio/')) or content_type == 'application/octet-stream':
            return result('ok', '', kind='file', container=(content_type.split('/', 1)[-1].upper()[:12] or 'File'), size=total)
        return result('unsupported', 'Not a media file Omni recognises.', kind='file')
    except Refused:
        return result('refused', 'Local or private address. Not checked.')
    except Problem as problem:
        return result(problem.status, problem.message)
    except Exception:
        return result('error', 'This link could not be checked.')


def site_probe(url, adapter_options=None):
    """yt-dlp's own format list for a page link (the site's extractor)."""
    import yt_dlp
    options = dict(quiet=True, no_warnings=True, noplaylist=True, skip_download=True, socket_timeout=8,
                   cachedir=False, js_runtimes={}, extract_flat=False)
    options.update(adapter_options or {})
    # DW-01: every connection yt-dlp opens (redirects, extractor subrequests,
    # manifests) goes through the loopback egress guard, which applies the same
    # public-address-only policy and pins each socket to the checked address.
    # Set last, so caller options can never remove it.
    options['proxy'] = shared_guard(public_address).url
    # yt-dlp lets a per-request proxy override the global one (geo verification
    # proxy / Ytdl-Request-Proxy header); neither may route around the guard.
    options['geo_verification_proxy'] = None
    options['http_headers'] = {k: v for k, v in (options.get('http_headers') or {}).items()
                               if k.lower() != 'ytdl-request-proxy'}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        return result('unsupported', 'The site check found no video on this page.', kind='page')
    if info.get('_type') in ('playlist', 'multi_video'):
        return result('unsupported', 'This page is a playlist. Open one video and grab it again.', kind='page')
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming'):
        return result('live', "Live stream. Omni can't save live streams yet.", kind='page', source='yt-dlp')
    formats = info.get('formats') or []
    if formats and all(f.get('has_drm') for f in formats):
        return result('protected', "Protected video (DRM). It can't be downloaded.", kind='page', source='yt-dlp', encrypted='drm')
    duration = info.get('duration')
    audio_only = [f for f in formats if f.get('vcodec') in (None, 'none') and f.get('acodec') not in (None, 'none') and not f.get('has_drm')]
    best_audio = max(audio_only, key=lambda f: f.get('abr') or f.get('tbr') or 0) if audio_only else None
    seen = {}
    for f in formats:
        if f.get('has_drm') or f.get('vcodec') in (None, 'none') or not f.get('height'):
            continue
        key = (f.get('height'), round(f.get('fps') or 0) or None)
        size = f.get('filesize') or f.get('filesize_approx')
        if size and f.get('acodec') in (None, 'none') and best_audio:
            size += best_audio.get('filesize') or best_audio.get('filesize_approx') or 0
        tbr = f.get('tbr') or 0
        candidate = dict(width=f.get('width'), height=f.get('height'), fps=key[1], vcodec=codec_name(f.get('vcodec')),
                         acodec=codec_name(f.get('acodec')) if f.get('acodec') not in (None, 'none') else (codec_name(best_audio.get('acodec')) if best_audio else ''),
                         bandwidth=int(tbr * 1000) if tbr else None, size=int(size) if size else (int(tbr * 1000 * duration / 8) if tbr and duration else None),
                         audio_group=None)
        if key not in seen or (candidate['bandwidth'] or 0) > (seen[key]['bandwidth'] or 0):
            seen[key] = candidate
    variants = sorted(seen.values(), key=lambda v: ((v['height'] or 0), (v['fps'] or 0), (v['bandwidth'] or 0)), reverse=True)[:16]
    tracks, langs = [], set()
    for f in sorted(audio_only, key=lambda f: f.get('abr') or 0, reverse=True):
        lang = f.get('language') or ''
        if lang.lower() in langs:
            continue
        langs.add(lang.lower())
        tracks.append(dict(lang=lang, name=f.get('format_note') or '', codec=codec_name(f.get('acodec')), default=False))
    subs = [dict(lang=k, name='') for k in sorted((info.get('subtitles') or {}).keys())][:12]
    best = variants[0] if variants else None
    value = result('ok', '', kind='page', container=(info.get('extractor_key') or 'Site')[:24], source='yt-dlp',
                   duration=duration, variants=variants, audio_tracks=tracks[:12], subtitles=subs,
                   size=best['size'] if best else None, size_estimated=True, title=str(info.get('title') or '')[:200] or None)
    if best:
        value['video'] = {k: best[k] for k in ('width', 'height', 'fps', 'vcodec')}
        value['audio'] = {'codec': best['acodec']} if best['acodec'] else None
    elif best_audio:
        value['audio'] = {'codec': codec_name(best_audio.get('acodec'))}
    if not variants and not best_audio:
        return result('unsupported', 'The site check found no downloadable formats.', kind='page', source='yt-dlp')
    return value


class Prober:
    """Cache + bounded concurrency for /api/probe."""

    def __init__(self, resolver=public_address, site=site_probe, clock=time.monotonic):
        self.resolver = resolver
        self.site = site
        self.clock = clock
        self.cache = {}
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(PARALLEL)
        self.site_slot = threading.BoundedSemaphore(1)
        self.site_running = {}

    def _cached(self, key):
        with self.lock:
            hit = self.cache.get(key)
            if hit and self.clock() - hit[0] < CACHE_SECONDS:
                return hit[1]
            return None

    def _store(self, key, value):
        with self.lock:
            if value.get('status') in ('slow', 'busy'):
                return
            self.cache[key] = (self.clock(), value)
            while len(self.cache) > CACHE_SIZE:
                self.cache.pop(next(iter(self.cache)))

    def probe(self, url, referer=None, deep=False):
        key = (url, referer, bool(deep))
        hit = self._cached(key)
        if hit is not None:
            return dict(hit, cached=True)
        if deep:
            return self._site(key, url)
        if not self.slots.acquire(timeout=DEADLINE):
            return result('busy', 'Still checking other links.')
        try:
            value = probe_url(url, referer, self.resolver)
        finally:
            self.slots.release()
        self._store(key, value)
        return value

    def _site(self, key, url):
        try:
            parts, port = check_url(url)
            resolve_within(self.resolver, parts.hostname, port, SOCKET_TIMEOUT)
        except TimeoutError:
            return result('slow', 'The site took too long to answer.', kind='page')
        except Refused:
            return result('refused', 'Local or private address. Not checked.', kind='page')
        except Problem as problem:
            return result(problem.status, problem.message, kind='page')
        with self.lock:
            running = self.site_running.get(key)
            if running is None:
                if not self.site_slot.acquire(blocking=False):
                    return result('busy', 'The site check is busy with another page. Try again shortly.', kind='page')
                running = dict(done=threading.Event(), value=None)
                self.site_running[key] = running

                def work():
                    try:
                        running['value'] = self.site(url)
                    except Exception as error:
                        message = str(error)
                        if 'drm' in message.lower():
                            running['value'] = result('protected', "Protected video (DRM). It can't be downloaded.", kind='page', source='yt-dlp')
                        elif 'unsupported url' in message.lower():
                            running['value'] = result('unsupported', 'No downloadable video found on this page.', kind='page', source='yt-dlp')
                        else:
                            running['value'] = result('error', 'The site check failed.', kind='page', source='yt-dlp')
                    finally:
                        self.site_slot.release()
                        self._store(key, running['value'])
                        with self.lock:
                            self.site_running.pop(key, None)
                        running['done'].set()
                threading.Thread(target=work, name='omni-site-probe', daemon=True).start()
        if running['done'].wait(min(SITE_TIMEOUT, 6.0)):
            return running['value']
        return result('slow', 'Still checking the site. This can take a moment.', kind='page', source='yt-dlp')


def quality_format(quality):
    """Build a yt-dlp format selector from a validated quality choice (never raw text from the GUI)."""
    if quality is None:
        return None
    if not isinstance(quality, dict) or set(quality) - {'height', 'fps', 'audio_lang', 'audio_only'}:
        raise ValueError('Invalid quality choice.')
    height, fps, lang, audio_only = quality.get('height'), quality.get('fps'), quality.get('audio_lang'), quality.get('audio_only', False)
    if type(audio_only) is not bool:
        raise ValueError('Invalid quality choice.')
    if height is not None and (type(height) is not int or not 1 <= height <= 4320):
        raise ValueError('Invalid quality height.')
    if fps is not None and (type(fps) is not int or not 1 <= fps <= 240):
        raise ValueError('Invalid quality frame rate.')
    if lang is not None and (not isinstance(lang, str) or not re.fullmatch(r'[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8}){0,2}', lang)):
        raise ValueError('Invalid audio language.')
    audio = f'bestaudio[language^={lang}]' if lang else 'bestaudio'
    if audio_only:
        return f'{audio}/bestaudio' if lang else 'bestaudio'
    if height is None:
        return f'bestvideo+{audio}/bestvideo+bestaudio/best' if lang else None
    video = f'bestvideo[height<={height}]' + (f'[fps<={fps + 1}]' if fps else '')
    return (f'{video}+{audio}/' if lang else '') + f'{video}+bestaudio/best[height<={height}]'


if __name__ == '__main__':
    import sys
    print(json.dumps(probe_url(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None), indent=2))
