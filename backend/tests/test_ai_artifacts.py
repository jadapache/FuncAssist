"""Artifact parsing, truncation detection and streaming splitter."""

from app.ai.artifacts import (
  ArtifactStreamSplitter,
  artifacts_to_dict,
  build_fallback_artifact,
  extract_artifacts,
  has_unclosed_artifact,
  is_artifact_truncated,
)


def test_extract_title_first_and_chat_blocks():
  raw = '<chat>Hola</chat>\n<artifact title="Plan A" extension="DOCX">\n# X\n</artifact>\n<chat>Nota</chat>'
  arts, clean = extract_artifacts(raw)
  assert [(a.title, a.extension, a.content, a.index) for a in arts] == [("Plan A", "docx", "# X", 0)]
  assert clean == "Hola\n\nNota"
  assert artifacts_to_dict(arts) == [{"index": 0, "title": "Plan A", "extension": "docx", "content": "# X"}]


def test_extract_alt_order_and_no_chat():
  arts, clean = extract_artifacts("intro <artifact extension='md' title='T'>body</artifact>\n\n\n\nfin")
  assert (arts[0].title, arts[0].extension, arts[0].content) == ("T", "md", "body")
  # Without <chat> blocks only the tags are stripped; the artifact body stays in the text.
  assert clean == "intro body\n\nfin"


def test_extract_recovers_truncated_blocks():
  raw = '<artifact title="A" extension="md">uno</artifact><artifact extension="xlsx" title="B">dos</art'
  arts, clean = extract_artifacts(raw)
  assert [(a.title, a.extension, a.content) for a in arts] == [("A", "md", "uno"), ("B", "xlsx", "dos")]
  assert "artifact" not in clean
  assert extract_artifacts("plain") == ([], "plain")


def test_unclosed_and_truncated():
  assert not has_unclosed_artifact("")
  assert not has_unclosed_artifact("no tags")
  assert has_unclosed_artifact('<artifact title="a" extension="md">x')
  assert not has_unclosed_artifact('<artifact title="a" extension="md">x</artifact>')
  assert not is_artifact_truncated("   ")
  assert is_artifact_truncated('<artifact title="a" extension="md">x')
  body = "texto normal. " * 50
  assert not is_artifact_truncated(body + "\nfin.")
  assert not is_artifact_truncated("## Corto")  # short texts never flagged
  assert is_artifact_truncated(body + "\n## BENEFICIO ESPERADO")
  assert is_artifact_truncated(body + "\n-")
  assert is_artifact_truncated(body + "\n```python\ncode here.")
  assert is_artifact_truncated(body + "\n| col1 | col2")
  assert not is_artifact_truncated(body + "\n| col1 | col2 |")


def test_fallback_artifact():
  a = build_fallback_artifact("  # Mi Título\ntexto  ", default_extension="MD")
  assert (a.title, a.extension, a.content) == ("Mi Título", "md", "# Mi Título\ntexto")
  assert build_fallback_artifact("sin heading").title == "Documento"


def _run(chunks):
  sp = ArtifactStreamSplitter()
  events = []
  for c in chunks:
    events += sp.feed(c)
  events += sp.close()
  return events


def _collapse(events):
  """Merge consecutive deltas of the same kind for stable assertions."""
  out = []
  for kind, data in events:
    if out and kind == out[-1][0] and kind in ("delta", "artifact_delta"):
      out[-1] = (kind, {**out[-1][1], "text": out[-1][1]["text"] + data["text"]})
    else:
      out.append((kind, data))
  return out


def test_splitter_char_by_char():
  raw = '<chat>Hola</chat> <artifact title="Doc" extension="MD">cuerpo</artifact> fin'
  events = _collapse(_run(list(raw)))
  assert events == [
    ("delta", {"text": "Hola "}),
    ("artifact_start", {"index": 0, "title": "Doc", "extension": "md"}),
    ("artifact_delta", {"index": 0, "text": "cuerpo"}),
    ("artifact_end", {"index": 0, "title": "Doc", "extension": "md", "truncated": False}),
    ("delta", {"text": " fin"}),
  ]


def test_splitter_truncated_and_malformed():
  events = _collapse(_run(['a <artifact foo="x"> b ', '<artifact extension="xlsx" title="T">dat', "a</art"]))
  kinds = [k for k, _ in events]
  assert events[0] == ("delta", {"text": 'a <artifact foo="x"> b '})
  assert ("artifact_start", {"index": 0, "title": "T", "extension": "xlsx"}) in events
  assert events[-2] == ("artifact_delta", {"index": 0, "text": "data</art"})
  assert events[-1][1]["truncated"] is True and kinds.count("artifact_end") == 1
  # Incomplete opening tag at close is flushed as chat text.
  assert _collapse(_run(["x <artifact titl"])) == [("delta", {"text": "x <artifact titl"})]
  # Truncated with nothing buffered.
  ev = _run(['<artifact title="a" extension="md">'])
  assert ev[-1][0] == "artifact_end" and ev[-1][1]["truncated"]
  assert ArtifactStreamSplitter().feed(None) == []
