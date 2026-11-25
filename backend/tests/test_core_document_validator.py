"""The document agent validator: what each operation needs before it can run, with the exact messages."""

from __future__ import annotations

import pytest

from app.core.document_agent import schema as ds
from app.core.document_agent.validator import DocumentOperationValidator as V

SECTION = "Observaciónes Generales"
MATCH = "Matched section 'Observaciónes Generales' (ID: s1)"


def state(**overrides) -> ds.CanonicalDocumentState:
  base = dict(document_id="d", sections=[ds.DocumentSection(id="s1", title=SECTION)], tags_present=["{{FECHA}}"])
  return ds.CanonicalDocumentState(**{**base, **overrides})


def at(**fields) -> ds.TargetLocator:
  return ds.TargetLocator(**fields)


GOOD = at(section_title="Observaciones")
BAD = at(section_title="Missing")
MISSING = "Target not found in document: section: Missing"


# -- finding the target -----------------------------------------------------------------------------

@pytest.mark.parametrize("title", ["observaciones", "OBSERVACIÓNES GENERALES", "Observaciónes Generales de la obra"])
def test_a_section_matches_by_accent_and_case_insensitive_partial_title(title):
  assert V.resolve_target(at(section_title=title), state()) == (True, MATCH)


@pytest.mark.parametrize("tag", ["{{fecha}}", "FECHA", "{fecha", "{{FECHA DE ENTREGA}}", "ec"])
def test_a_tag_matches_with_or_without_braces_and_case(tag):
  assert V.resolve_target(at(tag=tag), state()) == (True, "Matched document placeholder tag '{{{{FECHA}}}}'")


def test_the_section_is_tried_before_the_tag():
  assert V.resolve_target(at(section_title="observaciones", tag="FECHA"), state())[1] == MATCH


def test_a_tag_is_tried_when_the_section_does_not_match():
  ok, message = V.resolve_target(at(section_title="Missing", tag="FECHA"), state())
  assert ok and "placeholder tag" in message


def test_a_cell_range_only_counts_in_a_spreadsheet():
  target = at(cell_range="A1:B2")
  assert V.resolve_target(target, state(kind="spreadsheet")) == (True, "Targeted spreadsheet cell range 'A1:B2'")
  assert V.resolve_target(target, state()) == (False, "Target not found in document: Unknown target locator")


def test_a_blank_document_accepts_any_target():
  blank = ds.CanonicalDocumentState(document_id="b")
  assert V.resolve_target(at(section_title="x"), blank) == (True, "Document is currently blank; appending to root.")


@pytest.mark.parametrize("extra", [
  {"sections": [ds.DocumentSection(id="s1", title="Otra")]},
  {"tags_present": ["{{FECHA}}"]},
  {"tables_summary": [ds.TableSummary(id="t1")]},
])
def test_a_document_with_anything_in_it_is_not_blank(extra):
  content = {"sections": [], "tags_present": [], "tables_summary": [], **extra}
  assert V.resolve_target(at(section_title="x"), ds.CanonicalDocumentState(document_id="d", **content))[0] is False


def test_a_missing_target_lists_everything_that_was_asked_for():
  assert V.resolve_target(at(section_title="Nope", tag="X", anchor_text="abc"), state()) == (
    False, "Target not found in document: section: Nope, tag: X, anchor: 'abc'")
  assert V.resolve_target(at(anchor_text="abc"), state())[1] == "Target not found in document: anchor: 'abc'"
  assert V.resolve_target(at(tag="X"), state())[1] == "Target not found in document: tag: X"


# -- operations -------------------------------------------------------------------------------------

def image(target=GOOD, asset_id="a1", url=None) -> ds.InsertImageOperation:
  return ds.InsertImageOperation(target=target, asset=ds.AssetLocator(asset_id=asset_id, url=url))


def test_an_image_needs_a_found_target():
  assert V.validate(image(BAD), state()) == (False, f"Invalid target for image insertion: {MISSING}")
  assert V.validate(image(), state(), ["a1"]) == (True, f"InsertImage validated successfully. {MATCH}")


def test_an_image_needs_an_asset_id_or_a_url():
  assert V.validate(image(asset_id=""), state()) == (False, "Image operation missing both asset_id and url.")
  assert V.validate(image(asset_id="", url="https://x/y.png"), state(), ["a1"])[0]


def test_an_image_asset_must_be_available_unless_it_comes_from_the_web_or_a_data_uri():
  unknown = "Asset ID 'a1' is not in available assets list."
  assert V.validate(image(), state(), ["other"]) == (False, unknown)
  assert V.validate(image(url="/local/file.png"), state(), ["other"]) == (False, unknown)
  assert V.validate(image(url="http://x/y.png"), state(), ["other"])[0]
  assert V.validate(image(url="https://x/y.png"), state(), ["other"])[0]
  assert V.validate(image(url="data:image/png;base64,AA"), state(), ["other"])[0]


def test_without_a_list_of_available_assets_any_asset_is_accepted():
  assert V.validate(image(), state())[0]
  assert V.validate(image(), state(), [])[0] is False


def test_text_cannot_be_empty():
  empty = "Cannot insert empty text content."
  for content in ("", "  \n "):
    assert V.validate(ds.InsertTextOperation(target=GOOD, content=content), state()) == (False, empty)


def test_text_needs_a_found_target():
  assert V.validate(ds.InsertTextOperation(target=BAD, content="x"), state()) == (
    False, f"Invalid target for text insertion: {MISSING}")
  assert V.validate(ds.InsertTextOperation(target=GOOD, content="x"), state()) == (
    True, f"InsertText validated successfully. {MATCH}")


def test_a_replacement_needs_a_found_target():
  assert V.validate(ds.ReplaceContentOperation(target=BAD, new_content="n"), state()) == (
    False, f"Invalid target for content replacement: {MISSING}")
  assert V.validate(ds.ReplaceContentOperation(target=GOOD, new_content="n"), state()) == (
    True, f"ReplaceContent validated successfully. {MATCH}")


def test_updating_a_table_in_a_spreadsheet_is_always_valid():
  assert V.validate(ds.UpdateTableOperation(target=at()), state(kind="spreadsheet")) == (
    True, "Spreadsheet table update validated.")


def test_updating_a_table_needs_a_table_or_a_section():
  tables = [ds.TableSummary(id="t1")]
  refused = (False, "Document contains no tables to update and no section specified.")
  assert V.validate(ds.UpdateTableOperation(target=at()), state()) == refused
  accepted = (True, "UpdateTable validated successfully.")
  assert V.validate(ds.UpdateTableOperation(target=GOOD), state()) == accepted
  assert V.validate(ds.UpdateTableOperation(target=at()), state(tables_summary=tables)) == accepted
  assert V.validate(ds.UpdateTableOperation(target=GOOD), state(tables_summary=tables)) == accepted


def test_a_new_table_needs_headers_and_a_found_target():
  assert V.validate(ds.CreateTableOperation(target=GOOD, headers=[]), state()) == (
    False, "Cannot create table without headers.")
  assert V.validate(ds.CreateTableOperation(target=BAD, headers=["h"]), state()) == (
    False, f"Invalid target for table creation: {MISSING}")
  assert V.validate(ds.CreateTableOperation(target=GOOD, headers=["h"]), state()) == (
    True, f"CreateTable validated successfully. {MATCH}")


def test_a_deletion_needs_a_found_target():
  assert V.validate(ds.DeleteContentOperation(target=BAD), state()) == (False, f"Invalid target for deletion: {MISSING}")
  assert V.validate(ds.DeleteContentOperation(target=GOOD), state()) == (
    True, f"DeleteContent validated successfully. {MATCH}")


def test_a_move_needs_both_targets():
  def move(source, destination):
    return V.validate(ds.MoveContentOperation(source_target=source, destination_target=destination), state())

  assert move(BAD, GOOD) == (False, f"MoveContent: source target not found — {MISSING}")
  assert move(GOOD, BAD) == (False, f"MoveContent: destination target not found — {MISSING}")
  assert move(GOOD, GOOD) == (True, f"MoveContent validated. Source: {MATCH}. Destination: {MATCH}")


@pytest.mark.parametrize("op", [
  ds.InspectDocumentOperation(), ds.FindSectionOperation(section_title="x"), ds.FindTextOperation(query="q"),
])
def test_read_operations_are_always_valid(op):
  assert V.validate(op, state()) == (True, f"Operation '{op.operation}' validated.")
