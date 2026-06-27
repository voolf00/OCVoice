"""Speech-to-text, speaker verification, and text-to-speech.

@contract: Provides the speech processing pipeline components
@desc: Speech-to-text (faster-whisper local + OpenAI API + Vosk streaming),
       speaker verification (SpeechBrain ECAPA-TDNN + Resemblyzer),
       and text-to-speech (Edge TTS + Piper TTS).
@tags: speech, stt, tts, speaker, vosk, streaming
"""
