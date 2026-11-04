"""Picking ports for apps (Setup writes the result into each app's ID card).

A port is free for an app when it is:
- not one of the suite's / console's known ports (config.RESERVED_PORTS), unless the app owns it;
- not in another app's ID card;
- not answering on the console's network address (a best-effort probe from this computer).

Limit: apps that listen on 127.0.0.1 only can't be seen from this computer, so the probe can miss
them. The known-ports list and the cards cover our own apps; see REPORT.md "Standard feedback".
"""
import json

from . import config
from .ps5 import port_open


def read_cards(console):
    cards = {}
    for name, entry in console.listing(config.CARDS_DIR).items():
        if entry["dir"] or not name.endswith(".json"):
            continue
        try:
            card = json.loads(console.read(config.CARDS_DIR + name))
        except ValueError:
            continue
        if isinstance(card, dict) and card.get("id"):
            cards[card["id"]] = card
    return cards


class PortPicker:
    def __init__(self, console, probe=True):
        self.console = console
        self.probe = probe
        self.claimed = {}   # port -> app id, from cards and from picks made in this run
        for app_id, card in read_cards(console).items():
            if type(card.get("port")) is int:
                self.claimed[card["port"]] = app_id

    def owner(self, port, app_id):
        """Who else uses this port, or None if `app_id` may have it."""
        if self.claimed.get(port) not in (None, app_id):
            return self.claimed[port]
        reserved = config.RESERVED_PORTS.get(port)
        if reserved and not _owns_reserved(app_id, port):
            return reserved
        return None

    def answering(self, port, app_id, current):
        # Something is listening. Fine if it's this app's own current port (the app is running).
        return self.probe and port != current and port_open(self.console.host, port, 0.4)

    def pick(self, app_id, rule, current=None):
        """rule = {"preferred": int, "movable": bool}. Returns (port, note)."""
        if rule is None:
            return None, None
        tries = []
        if current:
            tries.append(current)          # keep a working port across updates
        tries.append(rule["preferred"])
        for p in tries:
            who = self.owner(p, app_id)
            if who is None and not self.answering(p, app_id, current):
                self.claimed[p] = app_id
                return p, None
        if not rule["movable"]:
            p = rule["preferred"]
            who = self.owner(p, app_id) or "another program on the PS5"
            raise PortClash("%s needs port %d, but %s is using it. Close it or uninstall it, then try again."
                            % (app_id, p, who))
        for lo, hi in config.PORT_RANGES:
            for p in range(lo, hi + 1):
                if self.owner(p, app_id) is None and not self.answering(p, app_id, current):
                    self.claimed[p] = app_id
                    return p, "Port %d was taken, so %s uses port %d." % (rule["preferred"], app_id, p)
        raise PortClash("No free port found for %s." % app_id)


class PortClash(Exception):
    pass


# Apps that own one of the suite's fixed ports.
_RESERVED_OWNERS = {config.HUB_PORT: config.HUB_ID, 8765: "downloads", 8767: "files-broker", 7090: "exbox"}


def _owns_reserved(app_id, port):
    return _RESERVED_OWNERS.get(port) == app_id
