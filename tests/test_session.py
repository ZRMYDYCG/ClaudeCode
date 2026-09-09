"""core.session：会话 jsonl 持久化。"""

from pathlib import Path

from pydantic_ai.messages import ModelRequest, UserPromptPart

from core import session


def test_sanitize_path() -> None:
    assert session.sanitize_path("/Users/me/proj") == "-Users-me-proj"


def test_list_sessions_and_first_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session, "STORAGE_ROOT", tmp_path)
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)

    sid = session.new_session_id()
    path = session.session_file(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"parts":[{"part_kind":"user-prompt","content":"hello"}],'
        '"kind":"request","instructions":null}\n',
        encoding="utf-8",
    )

    assert session.first_prompt(path) == "hello"
    listed = session.list_sessions()
    assert len(listed) == 1
    assert listed[0][0] == sid
    assert listed[0][2] == "hello"


def test_append_messages_writes_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session, "STORAGE_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)

    sid = "abc"
    msg = ModelRequest(parts=[UserPromptPart(content="hi")])
    session.append_messages(sid, [msg])
    text = session.session_file(sid).read_text(encoding="utf-8")
    assert "user-prompt" in text
    assert text.endswith("\n")


def test_append_messages_skips_empty_session_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session, "STORAGE_ROOT", tmp_path)
    session.append_messages("", [object()])
    assert list(tmp_path.rglob("*.jsonl")) == []
