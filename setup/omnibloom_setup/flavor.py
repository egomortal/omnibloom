"""A little fun while Setup works: a morph call now and then during installs, repairs and waits.

Short catchphrases only, as a nod for fans: no names, logos or art, and nothing that suggests Omnibloom is connected
to any show. Turn them off with --plain on the command line or OMNIBLOOM_PLAIN=1.
"""
import os
import random

CALLS = (
    "It's Morphin' Time!",
    "Shift into Turbo!",
    "Let's Rocket!",
    "Go Galactic!",
    "Lightspeed, Rescue!",
    "Time for Time Force!",
    "Wild Access!",
    "Ninja Storm, Ranger Form!",
    "Dino Thunder, Power Up!",
    "S.P.D., Emergency!",
    "Magical Source, Mystic Force!",
    "Overdrive, Accelerate!",
    "Jungle Beast, Spirit Unleashed!",
    "RPM, Get in Gear!",
    "Go Go Samurai!",
    "Go Go Megaforce!",
    "Super Mega Mode!",
    "Energize! Unleash the Power!",
    "Ready! Ninja Spin!",
    "Beast Morphers, Activate!",
    "Dino Fury, Unleash the Power!",
)

_plain = os.environ.get("OMNIBLOOM_PLAIN", "").strip().lower() in ("1", "yes", "true", "on")
_last = None


def set_plain(value):
    global _plain
    _plain = bool(value)


def enabled():
    return not _plain


def call():
    """A morph call (never the same one twice in a row), or "" with plain messages on."""
    global _last
    if _plain:
        return ""
    choices = [c for c in CALLS if c != _last]
    _last = random.choice(choices)
    return _last


def say(log):
    """Log one morph call through `log` (no-op with plain messages)."""
    line = call()
    if line:
        log(">> " + line)   # plain ASCII: Windows consoles (cp1252) cannot print emoji
