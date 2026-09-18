"""Classify split Godot stderr warnings without hiding later runtime errors."""
import re

_LOCATION = re.compile(r"[ \t]+at: [^\r\n]+ \([^()\r\n]+:[0-9]+\)[ \t]*")


class ConsoleDiagnostics:
    def __init__(self):
        self.warnings = []
        self._warning_location_pending = False

    def is_error(self, kind, message):
        pending = self._warning_location_pending
        self._warning_location_pending = False
        if kind == 'error' and message.lstrip().startswith('WARNING:'):
            # Godot Web sends the warning header and its native location separately.
            self._warning_location_pending = '\n' not in message
            self.warnings.append(message[:1000])
            del self.warnings[:-20]
            return False
        if kind == 'error' and pending and _LOCATION.fullmatch(message):
            if self.warnings:
                self.warnings[-1] = (self.warnings[-1] + '\n' + message)[:2000]
            return False
        return kind == 'error'
