# mypy: disable-error-code="union-attr"
"""T17.1 legacy step 17.A: strict single-action model response parser tests.

Pins the closed-response parser contract of SPEC §4.2.2/§4.2.5: exactly one
complete model-response JSON object parses into the closed ``AgentAction``
union or one stable ``ParseErrorV1``; surrounding text, multiple objects,
defaults, omissions, unknown/extra keys, wrong types, and any model-supplied
Harness action identity are rejected with a stable parse error.  The exact
card RED test (``test_model_supplied_action_id_is_rejected``) is preserved
verbatim.  The per-file ``union-attr`` mypy directive is the minimal
accommodation for the card's exact RED assertion, which accesses
``error_code`` on the ``AgentAction | ParseErrorV1`` union return without a
narrowing check (mypy strict cannot see the attribute on the six action
members); the same directive also covers the matrix's union-attribute
accesses (``action_type``/``root.kind``/``error_code``), which all execute
at runtime against the expected concrete values, so no defect is masked.
"""

from __future__ import annotations

import hashlib

import pytest

from src.vespercode.llm.base import ModelResponse
from src.vespercode.loop.action_parser import ActionParser

_DIGEST = "1" * 64


def model_response(text: str) -> ModelResponse:
    """One closed ModelResponse whose digest and byte count bind *text*."""
    raw = text.encode("utf-8")
    return ModelResponse(
        schema_version=1,
        text=text,
        text_digest=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def response_with_action_id() -> ModelResponse:
    """A model response whose action object carries a forbidden action id."""
    return model_response(
        '{"schema_version":1,"action_type":"list_files","action_id":"model-1",'
        '"root":{"kind":"ROOT"},"recursive":false,"max_entries":10,'
        '"cursor":{"kind":"ABSENT"}}'
    )


def list_files_json() -> str:
    return (
        '{"schema_version":1,"action_type":"list_files",'
        '"root":{"kind":"ROOT"},"recursive":true,"max_entries":50,'
        '"cursor":{"kind":"ABSENT"}}'
    )


def read_file_json() -> str:
    return (
        '{"schema_version":1,"action_type":"read_file","path":"src/a.py",'
        '"start_line":1,"line_count":40,"max_bytes":8192}'
    )


def search_text_json() -> str:
    return (
        '{"schema_version":1,"action_type":"search_text","query":"def",'
        '"roots":[{"kind":"PATH","path":"src"}],"case_sensitive":false,'
        '"context_lines":1,"max_results":20,"cursor":{"kind":"ABSENT"}}'
    )


def apply_candidate_patch_json() -> str:
    patch = "--- a/src/a.py\\n+++ b/src/a.py\\n@@ -1 +1 @@\\n-x\\n+x\\n"
    return (
        '{"schema_version":1,"action_type":"apply_candidate_patch",'
        f'"base_candidate_digest":"{_DIGEST}",'
        f'"patch_format":"UNIFIED_DIFF_V1","patch_text":"{patch}"}}'
    )


def run_check_json() -> str:
    return (
        '{"schema_version":1,"action_type":"run_check","check_plan_id":"TARGET_TESTS"}'
    )


def propose_completion_json() -> str:
    return (
        '{"schema_version":1,"action_type":"propose_completion",'
        f'"candidate_digest":"{_DIGEST}","rationale_summary":"done"}}'
    )


@pytest.fixture
def parser() -> ActionParser:
    """One parser instance; parsing is side-effect free."""
    return ActionParser()


def test_model_supplied_action_id_is_rejected(parser: ActionParser) -> None:
    assert parser.parse(response_with_action_id()).error_code == "UNKNOWN_FIELD"


def test_action_parser_closed_grammar_matrix(parser: ActionParser) -> None:
    """Registry 17.A: each closed action variant parses only its fields;
    model action id, multiple actions, trailing bytes, unknown type,
    malformed JSON, or extra field is rejected."""

    # --- Every closed variant parses into its exact concrete action. ---
    parsed_list = parser.parse(model_response(list_files_json()))
    assert parsed_list.action_type == "list_files"
    assert parsed_list.max_entries == 50
    assert parsed_list.root.kind == "ROOT"
    assert parsed_list.cursor.kind == "ABSENT"

    parsed_read = parser.parse(model_response(read_file_json()))
    assert parsed_read.action_type == "read_file"
    assert parsed_read.path.value == "src/a.py"
    assert parsed_read.line_count == 40

    parsed_search = parser.parse(model_response(search_text_json()))
    assert parsed_search.action_type == "search_text"
    assert parsed_search.roots[0].kind == "PATH"
    assert parsed_search.max_results == 20

    parsed_patch = parser.parse(model_response(apply_candidate_patch_json()))
    assert parsed_patch.action_type == "apply_candidate_patch"
    assert parsed_patch.patch_format == "UNIFIED_DIFF_V1"

    parsed_check = parser.parse(model_response(run_check_json()))
    assert parsed_check.action_type == "run_check"
    assert parsed_check.check_plan_id == "TARGET_TESTS"

    parsed_completion = parser.parse(model_response(propose_completion_json()))
    assert parsed_completion.action_type == "propose_completion"
    assert parsed_completion.rationale_summary == "done"

    # JSON whitespace around the single object is not surrounding text.
    padded = "  \n\t" + run_check_json() + "\r\n "
    assert parser.parse(model_response(padded)).action_type == "run_check"

    # --- Every framing/field/type/omission/default/identity violation
    # returns the stable parse error. ---
    rejection_rows: list[tuple[str, str]] = [
        # model-supplied Harness identity
        (
            '{"schema_version":1,"action_type":"read_file","path":"src/a.py",'
            '"start_line":1,"line_count":1,"max_bytes":1024,'
            '"action_id":"model-id"}',
            "UNKNOWN_FIELD",
        ),
        # unknown/extra field on a closed variant
        (
            '{"schema_version":1,"action_type":"read_file","path":"src/a.py",'
            '"start_line":1,"line_count":1,"max_bytes":1024,"verbose":true}',
            "UNKNOWN_FIELD",
        ),
        # cross-variant fields are extra fields of the declared variant
        (
            '{"schema_version":1,"action_type":"list_files",'
            '"root":{"kind":"ROOT"},"recursive":false,"max_entries":10,'
            '"cursor":{"kind":"ABSENT"},"check_plan_id":"TARGET_TESTS"}',
            "UNKNOWN_FIELD",
        ),
        # omitted required field (no default may fill it)
        (
            '{"schema_version":1,"action_type":"read_file","path":"src/a.py",'
            '"start_line":1,"line_count":1}',
            "MISSING_FIELD",
        ),
        # omitted discriminator
        ('{"schema_version":1,"max_entries":10}', "MISSING_FIELD"),
        # wrong field type (no bool/float coercion into integers)
        (
            '{"schema_version":1,"action_type":"read_file","path":"src/a.py",'
            '"start_line":"1","line_count":1,"max_bytes":1024}',
            "FIELD_INVALID",
        ),
        # unknown action type
        (
            '{"schema_version":1,"action_type":"hack","any":1}',
            "UNKNOWN_ACTION_TYPE",
        ),
        # malformed JSON
        ('{"schema_version":1,"action_type":"list_files",', "NOT_JSON_OBJECT"),
        # multiple JSON objects in one response
        (
            '{"schema_version":1,"action_type":"run_check",'
            '"check_plan_id":"TARGET_TESTS"}'
            '{"schema_version":1,"action_type":"run_check",'
            '"check_plan_id":"RUFF"}',
            "NOT_JSON_OBJECT",
        ),
        # trailing bytes after the single object
        (
            '{"schema_version":1,"action_type":"run_check",'
            '"check_plan_id":"TARGET_TESTS"}\nand more text',
            "NOT_JSON_OBJECT",
        ),
        # a JSON array of actions is not a single action object
        (
            "[" + run_check_json() + "," + run_check_json() + "]",
            "NOT_JSON_OBJECT",
        ),
        # a bare JSON scalar is not an action object
        ('"just a string"', "NOT_JSON_OBJECT"),
        # whitespace only is not an object
        ("   \n  ", "NOT_JSON_OBJECT"),
    ]
    for text, expected_code in rejection_rows:
        outcome = parser.parse(model_response(text))
        assert outcome.error_code == expected_code, text
        assert outcome.bounded_message != ""


def test_parse_rejects_integer_schema_version_coercion(parser: ActionParser) -> None:
    """Schema version must be the decimal integer 1, never a string/bool."""
    outcome = parser.parse(
        model_response(
            '{"schema_version":"1","action_type":"run_check",'
            '"check_plan_id":"TARGET_TESTS"}'
        )
    )
    assert outcome.error_code == "FIELD_INVALID"


def test_parse_is_side_effect_free(parser: ActionParser) -> None:
    """Parsing never mutates the response and repeats deterministically."""
    response = model_response(read_file_json())
    first = parser.parse(response)
    second = parser.parse(response)
    assert first.action_type == "read_file"
    assert second.action_type == "read_file"
    assert response.text == read_file_json()
