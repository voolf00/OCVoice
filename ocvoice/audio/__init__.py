"""Audio capture, VAD, and wake word detection.

@contract: Provides the audio input pipeline components
@desc: Real-time audio capture via sounddevice, voice activity detection
       (WebRTC VAD + Silero fallback), and wake word detection (openwakeword
       + energy-based fallback).
@tags: audio, capture, vad, wake
"""
