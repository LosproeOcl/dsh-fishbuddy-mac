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


def test_hotkey_names():
    assert main.key_name(49, 1 << 19) == "⌥Space"
    assert main.key_name(49, (1 << 20) | (1 << 17)) == "⇧⌘Space"


def test_hotkey_conflicts():
    assert main.hotkey_conflict(49, 1 << 20) == "和系统快捷键「Spotlight 搜索」撞了"
    assert main.hotkey_conflict(49, 1 << 19) is None
    assert "⌘ / ⌥ / ⌃" in main.hotkey_conflict(49, 0)


def test_settings_has_new_keys():
    for k in ("挂件", "形象", "热键表"):
        assert k in main.DEFAULT_SETTINGS
    tbl = main.DEFAULT_SETTINGS["热键表"]
    assert set(tbl) == {"说话", "陪看", "看一眼", "设置"}
    for combo in tbl.values():
        assert len(combo) == 2


def test_hotkey_table_conflict():
    table = {"说话": [49, 1 << 19]}
    assert main.hotkey_conflict(49, 1 << 19, table, skip="陪看") == "和「说话」用了同一个组合"
    assert main.hotkey_conflict(49, 1 << 19, table, skip="说话") is None
