"""Tests for PCM to WAV helper."""

from intersection_agent.services.qwen_tts_realtime_service import pcm_to_wav


def test_pcm_to_wav_header():
    pcm = b"\x00\x00" * 100
    wav = pcm_to_wav(pcm, sample_rate=24000)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert len(wav) == 44 + len(pcm)
