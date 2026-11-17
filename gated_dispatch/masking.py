"""PII masking at the dispatch seam (proposal — Q-056 adoption, pilot-verified).

Every frontier-bound prompt passes through the masker before dispatch:
personal information is replaced with typed tokens, the frontier answers
against tokens, and the response is re-identified through the per-ticket
vault before it reaches the consumer. The vault never leaves this host and
never enters the ledger; the ledger records counts by class, never values.

Engine order (pilot, 2026-11-14, pinned set v1 — see MASKING.md):
  1. Rampart (primary): local ONNX classifier + deterministic layer, driven
     through the detector seam below (a Node sidecar in production).
  2. Presidio (fallback / breadth): second pass for classes outside
     Rampart's label set and for non-Latin content.
The deterministic layer in this module (checksummed cards, structural SSN,
email/URL/IP, phone forms) always runs — it owns the classes that carry a
checksum, at near-100% recall, whichever neural engine is bound.

Register: the class register (names -> role tokens, orgs -> class tokens,
always-tokenize strings, never-mask keep-set) is OPERATOR data. It is loaded
from a local file that is never committed; register.example.json carries the
shape with synthetic values only.

Fail-closed: any masker error raises MaskingError and dispatch blocks.
There is no bypass flag.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


class MaskingError(Exception):
    """Raised on any masker failure. Dispatch must not proceed."""


# ---------------------------------------------------------------- register

@dataclass
class Register:
    """His class register: the differentiation layer (evaluation section 3).

    names:      surface form -> role token stem, e.g. {"Asha Rao": "SPOUSE"}
    name_parts: given/surname parts for the gazetteer (joined across
                spaces, dots, underscores and hyphens: asha.rao, A. Rao)
    orgs:       surface form -> class token stem, e.g. {"Acme Corp": "EMPLOYER"}
    always:     strings masked reversibly without waiting for detection
    never:      keep-set — domain vocabulary that must survive masking
    """

    names: dict = field(default_factory=dict)
    name_parts: dict = field(default_factory=dict)
    orgs: dict = field(default_factory=dict)
    always: list = field(default_factory=list)
    never: set = field(default_factory=set)

    @classmethod
    def load(cls, path):
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:  # fail-closed: no register, no dispatch
            raise MaskingError(f"register load failed: {exc}") from exc
        return cls(
            names=dict(raw.get("names", {})),
            name_parts=dict(raw.get("name_parts", {})),
            orgs=dict(raw.get("orgs", {})),
            always=list(raw.get("always", [])),
            never={w.lower() for w in raw.get("never", [])},
        )


# ------------------------------------------------------------------- vault

@dataclass
class Vault:
    """Per-ticket token map. Keyed by ticket id; TTL = ticket life.

    The map is the secret: it stays on the gate host, is dropped when the
    ticket closes, and is never written to the ledger or any log.
    """

    ticket_id: str
    created: float = field(default_factory=time.time)
    _map: dict = field(default_factory=dict)      # token -> original
    _counters: dict = field(default_factory=dict)  # stem -> n
    counts: dict = field(default_factory=dict)     # class -> n (ledger-safe)

    def token_for(self, original: str, stem: str, cls: str) -> str:
        for tok, val in self._map.items():
            if val == original:
                return tok
        n = self._counters.get(stem, 0) + 1
        self._counters[stem] = n
        token = f"[{stem}_{n}]"
        self._map[token] = original
        self.counts[cls] = self.counts.get(cls, 0) + 1
        return token

    def originals(self):
        return set(self._map.values())

    def restore(self, text: str) -> str:
        for token in sorted(self._map, key=len, reverse=True):
            text = text.replace(token, self._map[token])
        return text

    def drop(self):
        self._map.clear()


# ------------------------------------------------------- deterministic layer

_LUHN = re.compile(r"(?<!\d)(?:\d[ -]?){15}\d(?!\d)")
_SSN = re.compile(r"(?<!\d)(\d{3})-(\d{2})-(\d{4})(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"https?://[^\s<>()]+")
_IP = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
# Phone forms incl. the parenthesized shape the pilot caught engines missing.
_PHONE = re.compile(
    r"(?:\(\d{3}\)\s?|\b\d{3}[-.])\d{3}[-.]\d{4}\b|\b\d{3}-\d{4}\b")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _ssn_ok(area: str, group: str, serial: str) -> bool:
    a = int(area)
    return a not in (0, 666) and a < 900 and group != "00" and serial != "0000"


# ------------------------------------------------------------------ masker

# A detector is any callable: text -> list of (start, end, label).
# Production binds Rampart (primary) and Presidio (fallback) behind it.
Detector = object


class Masker:
    def __init__(self, register: Register, detectors=()):
        self.register = register
        self.detectors = list(detectors)

    # -- outbound ------------------------------------------------------
    def mask(self, text: str, vault: Vault) -> str:
        try:
            return self._mask(text, vault)
        except MaskingError:
            raise
        except Exception as exc:  # fail-closed on ANY masker failure
            raise MaskingError(f"mask failed: {exc}") from exc

    def _mask(self, text: str, vault: Vault) -> str:
        reg = self.register
        spans = []  # (start, end, stem, cls)

        def add(start, end, stem, cls):
            if text[start:end].lower() in reg.never:
                return
            spans.append((start, end, stem, cls))

        # 1. deterministic layer (checksum/structural classes)
        for m in _LUHN.finditer(text):
            if _luhn_ok(re.sub(r"\D", "", m.group())):
                add(m.start(), m.end(), "CARD", "identifier")
        for m in _SSN.finditer(text):
            if _ssn_ok(*m.groups()):
                add(m.start(), m.end(), "SSN", "identifier")
        for m in _EMAIL.finditer(text):
            add(m.start(), m.end(), "EMAIL", "identifier")
        for m in _URL.finditer(text):
            add(m.start(), m.end(), "URL", "identifier")
        for m in _IP.finditer(text):
            add(m.start(), m.end(), "IP", "identifier")
        for m in _PHONE.finditer(text):
            add(m.start(), m.end(), "PHONE", "identifier")

        # 2. register: always-tokenize + orgs + full names (longest first)
        literal = [(s, "VALUE", "register") for s in reg.always]
        literal += [(s, stem, "org") for s, stem in reg.orgs.items()]
        literal += [(s, stem, "name") for s, stem in reg.names.items()]
        for surface, stem, cls in sorted(literal, key=lambda x: -len(x[0])):
            for m in re.finditer(re.escape(surface), text):
                add(m.start(), m.end(), stem, cls)

        # 3. gazetteer: known name-parts joined across separators
        #    (asha.rao / A. Rao / asha-rao catch deterministically)
        for part, stem in reg.name_parts.items():
            pat = re.compile(r"(?<![A-Za-z])" + re.escape(part) +
                             r"(?![A-Za-z])", re.IGNORECASE)
            for m in pat.finditer(text):
                add(m.start(), m.end(), stem, "name")

        # 4. neural detectors behind the seam (Rampart, then Presidio)
        #    A detected span can swallow keep-set terms inside a longer
        #    span ("jandhyam after snanam" read as one GIVEN_NAME —
        #    retention verification 2026-11-17: exact-span keep checks
        #    held 14/16, the merged span cost the other 2). Split
        #    detected spans around whole-word keep terms and mask only
        #    the remaining fragments.
        def add_detected(start, end, label):
            frag = text[start:end]
            cuts = []
            for term in reg.never:
                for m in re.finditer(r"(?<![A-Za-z])" + re.escape(term) +
                                     r"(?![A-Za-z])", frag,
                                     re.IGNORECASE):
                    cuts.append((m.start(), m.end()))
            if not cuts:
                add(start, end, label, "detected")
                return
            cuts.sort()
            pos = 0
            for cs, ce in cuts:
                if cs > pos and frag[pos:cs].strip():
                    add(start + pos, start + cs, label, "detected")
                pos = max(pos, ce)
            if pos < len(frag) and frag[pos:].strip():
                add(start + pos, end, label, "detected")

        for detect in self.detectors:
            for start, end, label in detect(text):
                add_detected(start, end, label)

        # resolve overlaps: earliest start wins, longest span wins ties
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        chosen, covered_until = [], -1
        for s in spans:
            if s[0] >= covered_until:
                chosen.append(s)
                covered_until = s[1]

        out, last = [], 0
        for start, end, stem, cls in chosen:
            out.append(text[last:start])
            out.append(vault.token_for(text[start:end], stem, cls))
            last = end
        out.append(text[last:])
        masked = "".join(out)

        # 5. known-value sweep: anything already in the vault that appears
        #    again unmasked (a later block, an inconsistent detection) is
        #    re-masked from the vault itself
        for token, original in list(vault._map.items()):
            if original in masked:
                masked = masked.replace(original, token)
        return masked

    # -- inbound -------------------------------------------------------
    def reidentify(self, text: str, vault: Vault) -> str:
        return vault.restore(text)

    def leak_scan(self, text: str, vault: Vault) -> list:
        """Return register/vault originals present in a response WITHOUT
        token provenance. A non-empty result quarantines the response:
        the consumer sees the defect, not the text."""
        leaks = []
        for original in vault.originals():
            if original in text:
                leaks.append(original)
        for surface in list(self.register.names) + list(self.register.orgs):
            if surface in text:
                leaks.append(surface)
        return sorted(set(leaks))
