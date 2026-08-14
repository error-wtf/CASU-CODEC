from __future__ import annotations

import json
import shutil
import subprocess
import threading

import pytest

from casu.core import CasuCancelled
from casu.jobs import ConversionEngine, ConversionJob, ConversionProfile
from casu.transcode import (MediaTranscodeError, build_transcode_command,
                            transcode_media)
from casu.cli import main


pytestmark = [pytest.mark.media,
              pytest.mark.skipif(not shutil.which("ffmpeg") or
                                  not shutil.which("ffprobe"),
                                  reason="FFmpeg unavailable")]


def _probe(path):
    return json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-show_chapters",
        "-show_format", "-of", "json", str(path),
    ], check=True, capture_output=True, text=True).stdout)


def _av_source(tmp_path):
    subtitle = tmp_path / "caption.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,300\nFull converter\n",
                        encoding="utf-8")
    chapters = tmp_path / "chapters.ffmeta"
    chapters.write_text(
        ";FFMETADATA1\ntitle=Full Converter Source\n[CHAPTER]\nTIMEBASE=1/1000\n"
        "START=0\nEND=400\ntitle=Intro\n", encoding="utf-8")
    source = tmp_path / "source.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x48:rate=5:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=16000:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=880:sample_rate=16000:duration=0.4", "-i", str(subtitle),
        "-i", str(chapters), "-map", "0:v:0", "-map", "1:a:0", "-map",
        "2:a:0", "-map", "3:s:0", "-map_metadata", "4", "-map_chapters", "4",
        "-metadata:s:a:0", "language=de", "-metadata:s:a:1", "language=en",
        "-c:v", "ffv1", "-c:a", "pcm_s16le", "-c:s", "srt", "-y", str(source),
    ], check=True)
    return source


def test_media_transcode_preserves_all_tracks_subtitle_metadata_and_chapter(tmp_path):
    source = _av_source(tmp_path)
    target = tmp_path / "restored.mp4"
    progress = []
    transcode_media(source, target, progress=progress.append)
    probe = _probe(target)
    kinds = [item["codec_type"] for item in probe["streams"]]
    assert kinds.count("video") == 1
    assert kinds.count("audio") == 2
    assert kinds.count("subtitle") == 1
    assert probe["format"]["tags"]["title"] == "Full Converter Source"
    assert probe["chapters"][0]["tags"]["title"] == "Intro"
    assert progress[0] == 0 and progress[-1] == 1
    assert progress == sorted(progress)


@pytest.mark.parametrize("extension,expected", [
    (".aac", "aac"), (".aif", "pcm_s16be"), (".aiff", "pcm_s16be"),
    (".alac", "alac"), (".flac", "flac"), (".m4a", "aac"),
    (".mka", "flac"), (".mp2", "mp2"), (".mp3", "mp3"),
    (".oga", "vorbis"), (".ogg", "vorbis"), (".opus", "opus"),
    (".wav", "pcm_s16le"), (".wma", "wmav2"),
])
def test_media_transcode_audio_output_matrix(tmp_path, extension, expected):
    source = _av_source(tmp_path)
    target = tmp_path / f"audio{extension}"
    transcode_media(source, target, preset="high")
    streams = _probe(target)["streams"]
    audio = [(item["codec_type"], item["codec_name"]) for item in streams
             if item["codec_type"] == "audio"]
    expected_count = 2 if extension in {".m4a", ".mka"} else 1
    assert audio == [("audio", expected)] * expected_count


@pytest.mark.parametrize("extension,video,audio", [
    (".3g2", "h264", "aac"), (".3gp", "h264", "aac"),
    (".asf", "wmv2", "wmav2"), (".avi", "mpeg4", "mp3"),
    (".f4v", "h264", "aac"), (".flv", "flv1", "mp3"),
    (".m2ts", "h264", "aac"), (".m4v", "h264", "aac"),
    (".mkv", "h264", "aac"), (".mov", "h264", "aac"),
    (".mp4", "h264", "aac"), (".mpeg", "mpeg2video", "mp2"),
    (".mpg", "mpeg2video", "mp2"), (".mts", "h264", "aac"),
    (".ogv", "theora", "vorbis"), (".ts", "h264", "aac"),
    (".webm", "vp9", "opus"), (".wmv", "wmv2", "wmav2"),
])
def test_media_transcode_video_output_matrix(tmp_path, extension, video, audio):
    source = _av_source(tmp_path)
    target = tmp_path / f"video{extension}"
    transcode_media(source, target, preset="small")
    streams = _probe(target)["streams"]
    codecs = {(item["codec_type"], item["codec_name"]) for item in streams}
    assert ("video", video) in codecs
    assert ("audio", audio) in codecs


def test_media_transcode_remux_and_lossless_profiles(tmp_path):
    source = _av_source(tmp_path)
    remuxed = tmp_path / "remux.mkv"
    transcode_media(source, remuxed, preset="remux")
    assert {item["codec_name"] for item in _probe(remuxed)["streams"]} >= {
        "ffv1", "pcm_s16le", "subrip"}
    lossless = tmp_path / "lossless.mkv"
    transcode_media(source, lossless, preset="lossless", subtitle_mode="drop")
    assert {item["codec_name"] for item in _probe(lossless)["streams"]} >= {
        "ffv1", "flac"}


def test_media_transcode_cancellation_removes_partial_output(tmp_path):
    source = _av_source(tmp_path)
    target = tmp_path / "cancelled.mp4"
    cancel = threading.Event(); cancel.set()
    with pytest.raises(CasuCancelled):
        transcode_media(source, target, cancel=cancel)
    assert not target.exists()
    assert not list(tmp_path.glob(".cancelled.*.mp4"))


def test_conversion_engine_media_job_is_hash_journal_resumable(tmp_path):
    source = _av_source(tmp_path)
    target = tmp_path / "engine.webm"
    profile = ConversionProfile(container="media", media_preset="small",
                                subtitle_mode="auto")
    job = ConversionJob(source, target, profile)
    engine = ConversionEngine(journal=tmp_path / "media-journal.json")
    first = engine.run([job])
    second = engine.run([job], resume=True)
    assert first[0].status == "converted" and first[0].error is None
    assert first[0].container == "media" and first[0].output_sha256
    assert second[0].resumed is True


def test_media_transcode_rejects_unsafe_codec_and_target(tmp_path, monkeypatch):
    monkeypatch.setattr("casu.transcode._probe", lambda _source: {
        "streams": [{"index": 0, "codec_type": "audio"}], "format": {}})
    with pytest.raises(MediaTranscodeError, match="codec name"):
        build_transcode_command("source", tmp_path / "out.mp3",
                                audio_codec="aac;touch /tmp/no")
    with pytest.raises(MediaTranscodeError, match="output extension"):
        build_transcode_command("source", tmp_path / "out.exe")


def test_cli_full_converter_recursive_batch_and_report(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "inputs"
    nested = source_dir / "nested"; nested.mkdir(parents=True)
    first = _av_source(tmp_path)
    first.replace(source_dir / "one.mkv")
    second = _av_source(tmp_path)
    second.replace(nested / "two.mkv")
    output = tmp_path / "outputs"
    report = tmp_path / "media-report.json"
    monkeypatch.setattr("sys.argv", [
        "casu", "transcode", str(source_dir), "-o", str(output),
        "--format", "webm", "--preset", "small", "--report", str(report),
    ])
    assert main() == 0
    payload = json.loads(report.read_text())
    assert payload["mode"] == "media-transcode"
    assert [item["status"] for item in payload["files"]] == [
        "converted", "converted"]
    assert (output / "one.webm").is_file()
    assert (output / "nested" / "two.webm").is_file()
    assert '"container": "webm"' in capsys.readouterr().out
