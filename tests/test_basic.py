import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def test_version():
    assert main.VERSION.count(".") == 2


def test_settings_defaults():
    d = dict(main.DEFAULT_SETTINGS)
    assert "朗读" in d and "热键" in d and "陪看间隔" in d


def test_settings_merge_ignores_unknown(tmp_path, monkeypatch):
    p = tmp_path / "s.json"
    p.write_text('{"朗读": false, "不认识的": 1}', encoding="utf-8")
    monkeypatch.setattr(main, "SETTINGS_PATH", str(p))
    got = main.load_settings()
    assert got["朗读"] is False
    assert "不认识的" not in got
    assert got["陪看间隔"] == main.DEFAULT_SETTINGS["陪看间隔"]


def test_payload_shapes():
    # 插件要的两个键名，写死在这里防止手滑改掉
    assert main.SEND_URL.endswith("/hands/say")
    assert main.REPLY_PORT == 8778
