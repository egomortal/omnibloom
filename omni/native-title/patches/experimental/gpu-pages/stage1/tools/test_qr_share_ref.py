#!/usr/bin/env python3
"""OMNI_QR_SHARE_V1: reference QR matrices for tools/test_qr_share.cpp (byte mode, level M, versions 1-20), and an
OpenCV decode of the codes the C++ encoder made.

  python3 -m venv /tmp/qrvenv && /tmp/qrvenv/bin/pip install qrcode segno opencv-python-headless numpy
  /tmp/qrvenv/bin/python -I test_qr_share_ref.py refs refs.txt
  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_qr_share.cpp -o t && ./t refs.txt mine.txt
  /tmp/qrvenv/bin/python -I test_qr_share_ref.py decode mine.txt

refs.txt, one line per case:  <lib> <data hex> <forced mask, -1 = library's choice> <version> <size> <rows: 0/1>
  qrcode: python-qrcode, every mask 0-7 forced (the exact-match reference) and its own mask choice.
  segno:  segno's own choice (information only: segno 1.6.6 writes an extra 0x00 codeword after the terminator when
          the data ends on a byte boundary, so its matrices differ from ISO 18004 padding unless the data fills the
          version exactly; its codes still scan).
mine.txt (written by the C++ test):  <data hex> <size> <rows>; "decode" scans each with cv2.QRCodeDetector (8 px
modules, 4-module quiet zone) and compares the text with the data.
"""
import sys

# Example hosts only (example.com / .org / .net, RFC 2606); no real addresses.
INPUTS = [
    b'HELLO WORLD',
    b'https://example.com/',
    b'https://www.example.org/path/to/page?id=42&lang=en#section-2',
    'https://example.net/café/日本'.encode('utf-8'),
    b'a',
]
# the longest input that fits each version 1-20 (level M, byte mode) and one byte more (the next version)
CAP = [0, 14, 26, 42, 62, 84, 106, 122, 152, 180, 213, 251, 287, 331, 362, 412, 450, 504, 560, 624, 666]
for v in range(1, 21):
    for n in (CAP[v], CAP[v] + 1):
        if n <= 666:
            base = ('https://example.com/v%d/' % v).encode()
            INPUTS.append((base + bytes(b'abcdefghijklmnopqrstuvwxyz0123456789-_'[i % 38] for i in range(n)))[:n])


def bits(mat):
    return ''.join('1' if c else '0' for row in mat for c in row)


def refs(path):
    import segno
    import qrcode
    from qrcode.util import QRData, MODE_8BIT_BYTE

    def qr(data, version, mask):
        q = qrcode.QRCode(version=version, error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, mask_pattern=mask)
        q.add_data(QRData(data, mode=MODE_8BIT_BYTE), optimize=0)
        q.make(fit=version is None)
        return q

    out = []
    for data in INPUTS:
        auto = qr(data, None, None)
        mat = auto.get_matrix()
        out.append('qrcode %s -1 %d %d %s' % (data.hex(), auto.version, len(mat), bits(mat)))
        for m in range(8):
            mat = qr(data, auto.version, m).get_matrix()
            out.append('qrcode %s %d %d %d %s' % (data.hex(), m, auto.version, len(mat), bits(mat)))
        s = segno.make(data, error='m', mode='byte', boost_error=False, micro=False)
        out.append('segno %s -1 %d %d %s' % (data.hex(), s.version, len(s.matrix), bits(s.matrix)))
    with open(path, 'w') as f:
        f.write('\n'.join(out) + '\n')
    print('%d reference matrices for %d inputs (python-qrcode, segno %s)' % (len(out), len(INPUTS), segno.__version__))


def decode(path):
    import cv2
    import numpy as np
    detectors = [cv2.QRCodeDetector()] + ([cv2.QRCodeDetectorAruco()] if hasattr(cv2, 'QRCodeDetectorAruco') else [])
    ok = bad = 0
    for line in open(path):
        hexdata, size, rows = line.split()
        size = int(size)
        a = np.array([int(c) for c in rows], dtype=np.uint8).reshape(size, size)
        want = bytes.fromhex(hexdata).decode('utf-8')
        text = ''
        # OpenCV's detector misses some clean codes at one scale and finds them at another: try a few
        for px in (8, 6, 10, 5, 12, 4):
            img = np.kron(np.pad(1 - a, 4, constant_values=1) * 255, np.ones((px, px), dtype=np.uint8))
            for det in detectors:
                text, _, _ = det.detectAndDecode(img)
                if text == want:
                    break
            if text == want:
                break
        if text == want:
            ok += 1
        else:
            bad += 1
            print('NOT DECODED: %d bytes, size %d: got %r' % (len(want.encode()), size, text[:60]))
    print('decoded %d/%d codes (OpenCV %s)' % (ok, ok + bad, cv2.__version__))
    sys.exit(1 if bad or not ok else 0)


if __name__ == '__main__':
    {'refs': refs, 'decode': decode}[sys.argv[1]](sys.argv[2])
