"""Voice: local speech-to-text (whisper.cpp), local text-to-speech, push-to-talk
and a wake-word loop. Everything runs on-device; audio never leaves the machine.

External programs are discovered at call time. When one is missing the status
says exactly which, and the action fails with an install hint.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .core import ActionError, Ctx

if TYPE_CHECKING:
    from .core import Core

WHISPER_NAMES = ("whisper-cli", "whisper-cpp", "whisper.cpp", "main")
STOP_PHRASES = ("stop listening", "goodbye titan", "that's all")
_NOISE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*")


def clean_transcript(text: str) -> str:
    return re.sub(r"\s+", " ", _NOISE.sub(" ", text)).strip()


def parse_wake(transcript: str, wake: str = "hey titan") -> str | None:
    """Return the command following the wake phrase, '' if only the wake phrase
    was said, or None if the wake phrase is absent. Tolerates common
    mis-hearings of “TITAN”."""
    t = re.sub(r"[^\w\s']", " ", transcript.lower())
    t = re.sub(r"\s+", " ", t).strip()
    words = wake.lower().split()
    variants = {wake.lower()}
    if words[-1] == "titan":
        head = " ".join(words[:-1])
        for alt in ("titan", "tighten", "titans", "tyton", "titen", "tightan"):
            variants.add(f"{head} {alt}".strip())
            if head == "hey":
                variants.add(f"hi {alt}")
                variants.add(f"a {alt}")
    best = None
    for v in variants:
        m = re.search(rf"(?:^|\s){re.escape(v)}(?:\s|$)", t)
        if m and (best is None or m.start() < best.start()):
            best = m
    if best is None:
        return None
    return t[best.end():].strip()


class Voice:
    def __init__(self, core: "Core"):
        self.core = core
        self._wake_task: str | None = None

    # --- discovery ---------------------------------------------------------
    def _whisper(self) -> str | None:
        s = self.core.settings
        if s.whisper_bin:
            return s.whisper_bin if Path(s.whisper_bin).exists() or shutil.which(s.whisper_bin) else None
        local = s.data_dir / "whisper.cpp" / "build" / "bin" / "whisper-cli"
        if local.exists():
            return str(local)
        return next((p for p in map(shutil.which, WHISPER_NAMES[:3]) if p), None)

    def _model(self) -> Path | None:
        s = self.core.settings
        if s.whisper_model:
            return s.whisper_model if s.whisper_model.exists() else None
        mdir = s.data_dir / "models"
        return next(iter(sorted(mdir.glob("ggml-*.bin"))), None) if mdir.is_dir() else None

    def _tts(self) -> str | None:
        want = self.core.db.pref("voice.tts_engine")
        for name in ([want] if want else []) + ["piper", "espeak-ng", "espeak", "spd-say"]:
            if name and shutil.which(name):
                return name
        return None

    def _recorder(self) -> str | None:
        return next((n for n in ("arecord", "pw-record", "parecord") if shutil.which(n)), None)

    def status(self) -> dict:
        w, m, t, r = self._whisper(), self._model(), self._tts(), self._recorder()
        missing = []
        if not w:
            missing.append("whisper.cpp binary (build whisper.cpp; see deploy/setup-voice.sh)")
        if not m:
            missing.append(f"whisper model (ggml-*.bin in {self.core.settings.data_dir / 'models'})")
        if not r:
            missing.append("audio recorder (sudo apt install alsa-utils)")
        if not t:
            missing.append("text-to-speech engine (sudo apt install espeak-ng)")
        return {"stt": {"available": bool(w and m), "binary": w, "model": str(m) if m else None},
                "tts": {"available": bool(t), "engine": t},
                "microphone": {"available": bool(r), "recorder": r},
                "wake_word": self.core.db.pref("voice.wake_word", "hey titan"),
                "wake_listening": self._wake_active(), "missing": missing}

    # --- primitives --------------------------------------------------------
    def transcribe(self, wav: Path) -> str:
        w, m = self._whisper(), self._model()
        if not w or not m:
            raise ActionError("Speech-to-text is not set up: " + "; ".join(x for x in self.status()["missing"] if "whisper" in x))
        lang = self.core.db.pref("voice.language", "en")
        try:
            p = subprocess.run([w, "-m", str(m), "-f", str(wav), "-l", lang, "-nt", "-np"],
                               capture_output=True, text=True, errors="replace", timeout=120)
        except subprocess.TimeoutExpired:
            raise ActionError("whisper.cpp timed out")
        if p.returncode != 0:
            raise ActionError(f"whisper.cpp failed: {p.stderr.strip()[-300:]}")
        return clean_transcript(p.stdout)

    def record(self, seconds: float, out: Path) -> None:
        r = self._recorder()
        if not r:
            raise ActionError("No audio recorder found. Install with: sudo apt install alsa-utils")
        secs = max(1, min(int(round(seconds)), 60))
        if r == "arecord":
            cmd = ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", str(secs), str(out)]
        elif r == "pw-record":
            cmd = ["timeout", str(secs), "pw-record", "--rate", "16000", "--channels", "1", str(out)]
        else:
            cmd = ["timeout", str(secs), "parecord", "--rate=16000", "--channels=1", "--file-format=wav", str(out)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=secs + 10)
        except subprocess.TimeoutExpired:
            raise ActionError("recording timed out")
        if not out.exists() or out.stat().st_size < 1000:
            raise ActionError(f"recording failed (is a microphone connected and unmuted?): {p.stderr.strip()[-200:]}")

    def speak(self, text: str) -> dict:
        engine = self._tts()
        if not engine:
            raise ActionError("No text-to-speech engine found. Install with: sudo apt install espeak-ng")
        text = text.strip()[:2000]
        if not text:
            raise ActionError("nothing to say")
        db = self.core.db
        if engine in ("espeak-ng", "espeak"):
            cmd = [engine, "-s", str(int(db.pref("voice.rate", 165))), "-v", str(db.pref("voice.voice", "en")), "--", text]
            stdin = None
        elif engine == "spd-say":
            cmd, stdin = ["spd-say", "--wait", "--", text], None
        else:  # piper: needs a voice model path; pipes raw audio to aplay
            model = db.pref("voice.piper_model")
            if not model or not Path(model).exists() or not shutil.which("aplay"):
                raise ActionError("piper needs the `voice.piper_model` preference set to a .onnx voice file, and `aplay`")
            cmd = ["bash", "-c", 'piper --model "$0" --output-raw | aplay -q -r 22050 -f S16_LE -t raw -', model]
            stdin = text
        try:
            p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise ActionError("speech timed out")
        if p.returncode != 0:
            raise ActionError(f"{engine} failed: {p.stderr.strip()[-200:]}")
        return {"spoken": text, "engine": engine}

    def listen_once(self, seconds: float = 5) -> str:
        with tempfile.TemporaryDirectory(prefix="titan-voice-") as d:
            wav = Path(d) / "in.wav"
            self.record(seconds, wav)
            return self.transcribe(wav)

    # --- conversation ------------------------------------------------------
    def handle_command(self, command: str) -> dict:
        """Send a spoken command to the assistant and speak the reply."""
        self.core.bus.publish("voice.command", {"text": command})
        out = self.core.ai.chat(command, conversation_id=self.core.db.pref("voice.conversation_id"), actor="voice")
        self.core.db.set_preference("voice.conversation_id", out["conversation_id"])
        if self.core.db.pref("voice.spoken_replies", True) and out["reply"]:
            try:
                self.speak(out["reply"][:600])
            except ActionError as e:
                out["speech_error"] = str(e)
        return out

    def _wake_active(self) -> bool:
        if not self._wake_task:
            return False
        try:
            return self.core.tasks.get(self._wake_task)["status"] in ("queued", "running")
        except KeyError:
            return False

    def start_wake(self) -> dict:
        if self._wake_active():
            raise ActionError("Wake-word listening is already running")
        st = self.status()
        if not (st["stt"]["available"] and st["microphone"]["available"]):
            raise ActionError("Voice is not set up: " + "; ".join(st["missing"]))
        wake = st["wake_word"]

        def loop(ctl):
            engaged = False  # continuous-conversation mode: no wake word needed
            while not ctl.cancelled:
                ctl.progress(0.0, "in conversation" if engaged else f"listening for “{wake}”")
                try:
                    heard = self.listen_once(5 if engaged else 4)
                except ActionError as e:
                    raise RuntimeError(str(e))
                if ctl.cancelled:
                    break
                if not heard:
                    engaged = False
                    continue
                cmd = heard if engaged else parse_wake(heard, wake)
                if cmd is None:
                    continue
                if cmd == "":
                    cmd = self.listen_once(6)
                if not cmd or any(s in cmd.lower() for s in STOP_PHRASES):
                    engaged = False
                    continue
                try:
                    self.handle_command(cmd)
                except Exception as e:
                    self.core.notifier.notify("ai", "Voice command failed", str(e), "warning")
                engaged = bool(self.core.db.pref("voice.continuous", False))
            return {"stopped": True}

        task = self.core.tasks.submit("Voice wake-word listener", loop)
        self._wake_task = task["id"]
        return {"task_id": task["id"], "wake_word": wake}

    def stop_wake(self) -> dict:
        if not self._wake_active():
            raise ActionError("Wake-word listening is not running")
        self.core.tasks.cancel(self._wake_task)  # type: ignore[arg-type]
        return {"stopping": True}


def register(reg) -> None:
    v = Voice(reg.core)
    reg.core.voice = v
    S = {"type": "string"}
    reg.add("voice.status", "voice", "Voice system status: speech-to-text, text-to-speech, microphone", lambda c, a: v.status(), readonly=True, ai=False)
    reg.add("voice.speak", "voice", "Speak text aloud with the local text-to-speech engine", lambda c, a: v.speak(a["text"]), {"text": S}, ["text"])
    reg.add("voice.listen", "voice", "Push-to-talk: record for N seconds and transcribe locally",
            lambda c, a: {"transcript": v.listen_once(a.get("seconds", 5))}, {"seconds": {"type": "integer"}}, ai=False)
    reg.add("voice.command", "voice", "Push-to-talk command: record, transcribe, run through the assistant, speak the reply",
            lambda c, a: (lambda t: {"transcript": t, **(v.handle_command(t) if t else {"reply": "", "steps": []})})(v.listen_once(a.get("seconds", 6))),
            {"seconds": {"type": "integer"}}, ai=False)
    reg.add("voice.wake_start", "voice", "Start wake-word listening in the background", lambda c, a: v.start_wake(), ai=False)
    reg.add("voice.wake_stop", "voice", "Stop wake-word listening", lambda c, a: v.stop_wake(), ai=False)
