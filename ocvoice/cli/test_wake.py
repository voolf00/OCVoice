"""Test wake word detection + speaker verification. No messages sent."""

import re
import time
import sys
import os
import numpy as np


def test_wake():
    """Test if the wake word + speaker verification detect the user's voice."""
    try:
        from ..speech.vosk_stt import VoskSTT
        from ..speech.speaker import SpeakerVerifier
        from ..config import Config
        from ..audio.capture import AudioCapture
    except ImportError:
        print("❌ Failed to load OCVoice modules")
        return

    cfg = Config()
    wake_words = cfg.wake_words
    daemon_pid = os.path.expanduser("~/.config/ocvoice/daemon.pid")

    print(f"\n{'='*50}")
    print("🧪  Test Wake Word + Speaker Verification")
    print(f"{'='*50}")
    print()
    print(f"Wake words: {', '.join(wake_words)}")
    print(f"Language: {cfg.language}")
    print(f"Speaker enabled: {cfg.speaker_enabled}")
    print(f"Speaker threshold: {cfg.speaker_threshold}")

    # Check if daemon is already running
    if os.path.exists(daemon_pid):
        try:
            with open(daemon_pid) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            print(f"\n⚠️  Daemon is RUNNING (PID {pid})")
            print("   This test may conflict with the daemon.")
            print("   Stop it first: ocv stop")
            print("   Or just say 'дарвин' to the running daemon.\n")
        except (ProcessLookupError, ValueError, OSError):
            pass

    # Check Vosk model
    vosk_cache = os.path.expanduser(f"~/.cache/ocvoice/vosk")
    lang_model = f"vosk-model-small-{cfg.language}"
    model_path = os.path.join(vosk_cache, lang_model)
    if os.path.exists(os.path.join(model_path, "am")):
        print(f"  ✓ Vosk model cached: {lang_model}")
    else:
        print(f"  ⚠️  Vosk model NOT cached — will download on first test")
    print(f"Speaker threshold: {cfg.speaker_threshold}")

    if not cfg.speaker_enabled:
        print("\n⚠️  Speaker verification is DISABLED")
        print("   Wake word will work without voice check.")
    else:
        verifier = SpeakerVerifier(cfg)
        if not verifier.is_enrolled():
            print("\n⚠️  No voice enrollment found!")
            print("   Run 'ocv enroll' or use the button in Settings.")
            print("   Without enrollment, verification allows everything.\n")

    # Find mic device
    device_id = cfg.audio_device
    if device_id < 1:
        device_id = AudioCapture.auto_detect_device()
        print(f"\n  Using auto-detected device: {device_id}")

    # Initialize Vosk
    try:
        vosk = VoskSTT(lang=cfg.language)
        print("  Vosk model loaded ✓")
    except Exception as e:
        print(f"❌ Vosk failed: {e}")
        return

    # Start audio capture
    capture = AudioCapture(
        sample_rate=16000,
        channels=1,
        device_id=device_id,
        chunk_size=1024,
    )
    capture.start()

    # Collect audio for verification
    verify_buffer = []

    print(f"\n  🎤 Listening for 15 seconds...")
    print(f"  Say the wake word ('{wake_words[0]}') clearly.\n")

    detected = False
    start = time.time()
    last_print = 0
    vosk_fuzzy = {"дарвин": "дарвин", "дарви": "дарвин", "darwin": "дарвин"}

    while time.time() - start < 15:
        chunk = capture.read(1024, timeout=0.5)
        if len(chunk) == 0:
            continue

        verify_buffer.append(chunk)
        max_verify = int(3.0 * 16000)
        verify_len = sum(len(c) for c in verify_buffer)
        while verify_len > max_verify * 3:
            verify_buffer.pop(0)
            verify_len = sum(len(c) for c in verify_buffer)

        vosk.process(chunk)
        partial = vosk.get_partial()
        if not partial:
            elapsed = int(time.time() - start)
            if elapsed > last_print:
                print(f"  ⏳ Listening... {elapsed}s", end="\r")
                last_print = elapsed
            continue

        clean = re.sub(r'[^\w\s]', '', partial.lower())

        for ww in wake_words:
            ww_c = re.sub(r'[^\w\s]', '', ww.lower())
            if ww_c in clean:
                detected = True
                elapsed = time.time() - start
                print(f"\n  ✅ Vosk detected: '{ww}' ({elapsed:.1f}s)")
                print(f"     Partial: \"{partial}\"")

                # Test speaker verification
                if cfg.speaker_enabled and len(verify_buffer) > 0:
                    try:
                        verify_audio = np.concatenate(verify_buffer)
                        if len(verify_audio) > max_verify:
                            verify_audio = verify_audio[-max_verify:]
                        v = verifier.verify(verify_audio)
                        score = v.get("score", 0)
                        match = v.get("match", False)
                        if match or score >= 0.25:
                            print(f"  ✅ Speaker: MATCH (score={score:.2f})")
                        else:
                            print(f"  ❌ Speaker: REJECTED (score={score:.2f} < threshold={cfg.speaker_threshold})")
                            print(f"     Lower threshold in Settings → Speaker Threshold")
                    except Exception as e:
                        print(f"  ⚠️  Speaker verify error: {e}")
                else:
                    print(f"  ⚠️  Speaker verification skipped (disabled or no enrollment)")
                break

        if not detected:
            for vosk_w, real_w in vosk_fuzzy.items():
                if vosk_w in clean:
                    for ww in wake_words:
                        ww_c = re.sub(r'[^\w\s]', '', ww.lower())
                        if real_w == ww_c:
                            detected = True
                            elapsed = time.time() - start
                            print(f"\n  ⚠️  Fuzzy Vosk: '{vosk_w}' matched '{ww}' ({elapsed:.1f}s)")
                            print(f"     Partial: \"{partial}\"")
                            break
                    break

        if detected:
            break

        elapsed = int(time.time() - start)
        if elapsed > last_print:
            print(f"  ⏳ Listening... {elapsed}s", end="\r")
            last_print = elapsed

    capture.stop()
    print()

    if detected:
        print(f"\n  ✅  Wake word '{wake_words[0]}' — Vosk DETECTED")
        print(f"  ✅  Test complete. Close this window and reopen Settings.")
    else:
        print(f"\n  ❌  Wake word NOT detected in 15 seconds")
        print(f"      Check microphone and try again.")

    print(f"\n{'='*50}")
    print()
    input("Press Enter to close...")
