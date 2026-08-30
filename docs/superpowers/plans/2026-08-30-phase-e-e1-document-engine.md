# Phase E E1 Document Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a database-independent CORE Document Engine for Canonical Document Schema v1, strict Restricted HTML, projections, Narou export, and a TipTap semantic round-trip feasibility gate without changing E2/backend/UI runtime behavior.

**Architecture:** `novel_core.document` owns immutable typed document values, strict schema parsing/normalization, a stdlib-only inline HTML AST, Authoring HTML interchange, pure WEB/Context projections, and a small exporter dispatcher. WEBUI receives only the explicitly required TipTap packages and a feasibility adapter/test; existing ManuscriptPage, API, MCP, migrations, and stable data remain untouched.

**Tech Stack:** Python 3.10+ dataclasses, `json`, `html`, and `html.parser.HTMLParser`; pytest, Ruff, Mypy, coverage; React/Vite/Vitest with official `@tiptap/*` packages and no UI/toolbar dependency.

**Spec:** `docs/superpowers/specs/2026-08-30-novelproduction-phase-e-structured-manuscript-design.md`

## Global Constraints

- Implement **E1 Document Engine only**; do not implement migration 005, draft persistence, save workflow, API/MCP contract changes, `episode_context`, ManuscriptPage integration, Final Cutover, or E2+ work.
- Keep `CORE/src/novel_core/services/draft_service.py`, `CORE/src/novel_core/repositories/draft_repository.py`, `API/`, and `MCP/` unchanged.
- Do not change migrations `001_initial.sql` through `004_drafts.sql`, `data/2126`, `story.db`, or the MCP tool count of 59.
- Do not add a Python HTML dependency; use stdlib parsing and deterministic escaping.
- Canonical block IDs match `^blk_[0-9a-f]{32}$`; generated IDs use UUID4 hex.
- Canonical JSON allows only standard JSON values and rejects NaN and ±Infinity.
- Every logical task follows failing test, observed failure, minimal implementation, target pass, adjacent pass, then the next task.
- Use one sequential agent; do not delegate, use subagents, create parallel work, or perform a live database/Broker/runtime operation.
- Preserve existing user files, especially the untracked `MCP/.tools/`; stage only intended E1 files.
- TipTap JSON is an internal adapter representation and is never a CORE/API/MCP/SQLite contract.

## File map

- `CORE/src/novel_core/errors.py`: add only `DocumentSchemaError` with stable code `DOCUMENT_SCHEMA_ERROR`.
- `CORE/src/novel_core/document/model.py`: typed Canonical Document values, block types, attributes, annotations, and formal-ID predicate.
- `CORE/src/novel_core/document/schema.py`: strict JSON boundary, v1 dispatch, structural validation, normalization, deterministic serialization, and generated IDs.
- `CORE/src/novel_core/document/inline_html.py`: private inline AST behind strict parse/serialize/visible-text functions.
- `CORE/src/novel_core/document/authoring_html.py`: typed Authoring HTML input, metadata/annotation codecs, projection selection, strict outer parser, and deterministic serializer.
- `CORE/src/novel_core/document/projections.py`: pure WEB Read rendering, Context rendering, tail selection, and typed result.
- `CORE/src/novel_core/document/exporters/__init__.py`: typed export result/warning and format dispatcher.
- `CORE/src/novel_core/document/exporters/narou.py`: direct Canonical-to-Narou rendering and ruby degradation warnings.
- `CORE/src/novel_core/document/__init__.py`: only stable public imports for the new package.
- `CORE/tests/test_document_schema.py`: schema/model/error contracts.
- `CORE/tests/test_document_inline_html.py`: strict inline grammar and visible text.
- `CORE/tests/test_document_authoring_html.py`: Authoring parser, codecs, projection, and round-trip.
- `CORE/tests/test_document_projections.py`: WEB and Context projections/truncation.
- `CORE/tests/test_document_narou.py`: exporter output and warnings.
- `CORE/tests/test_installed_wheel.py`: installed-wheel import smoke for `novel_core.document`.
- `WEBUI/frontend/package.json`, `WEBUI/frontend/package-lock.json`: official TipTap dependencies only.
- `WEBUI/frontend/src/features/manuscript/tiptap/phaseEExtensions.ts`: minimal block-attribute, ruby, and emphasis-dot extensions.
- `WEBUI/frontend/src/features/manuscript/tiptap/phaseEFeasibility.test.ts`: shared-fixture semantic round-trip test.
- `tests/fixtures/phase_e_tiptap_roundtrip.html`: one CORE-accepted fixture consumed by CORE and WEBUI tests.

---

### Task 1: Canonical model and Schema v1

**Files:**
- Create: `CORE/src/novel_core/document/__init__.py`
- Create: `CORE/src/novel_core/document/model.py`
- Create: `CORE/src/novel_core/document/schema.py`
- Modify: `CORE/src/novel_core/errors.py`
- Test: `CORE/tests/test_document_schema.py`

**Interfaces:**
- Consumes: no database or service layer; standard JSON text/bytes/mappings.
- Produces: `JsonValue`, `BlockType`, `BlockAttrs`, `NovelBlock`, `NovelDocument`, `is_formal_block_id`, `parse_document_json(raw) -> NovelDocument`, `normalize_document(document) -> NovelDocument`, `serialize_document_json(document) -> str`, and `new_block_id() -> str`.

- [ ] **Step 1: Write failing tests for the public schema behavior.**

  Cover empty documents, all eight block types, ordered blocks, formal ID acceptance, UUID4-shaped generated IDs, positive integer attrs, required heading levels, empty non-heading HTML, separator structure, arbitrary annotations, `emotions` as `string[]`, and `DocumentSchemaError.code == "DOCUMENT_SCHEMA_ERROR"`. Add rejection cases for wrong envelope/type/version, unsupported version, extra envelope/block/attr fields, malformed IDs, duplicate IDs, unknown types, non-finite numbers, invalid attr values, heading mismatch, non-empty separator HTML, and empty heading visible text. Assert that null optional attrs disappear after normalization and that Japanese JSON is emitted as UTF-8 text with compact deterministic separators, stable object-key order, preserved block order, and `\n` values.

  ```python
  def test_document_json_round_trips_deterministically() -> None:
      document = NovelDocument(
          blocks=(
              NovelBlock(
                  id="blk_0123456789abcdef0123456789abcdef",
                  type="heading",
                  html="東京\n",
                  attrs=BlockAttrs(heading_level=2),
                  annotations={"emotions": ["静か"], "snack-count": 3},
              ),
          )
      )
      raw = serialize_document_json(document)
      assert raw == serialize_document_json(parse_document_json(raw))
      assert "東京" in raw and "\\u6771" not in raw
      assert "\n" not in raw
  ```

- [ ] **Step 2: Run the schema target to observe the intended RED state.**

  Run `uv run pytest -q tests/test_document_schema.py`. Expected result: collection fails because `novel_core.document` and `DocumentSchemaError` do not yet exist. If collection reports a test typo instead, correct the test until the failure is caused by the missing implementation.

- [ ] **Step 3: Implement the smallest typed model and v1 boundary.**

  Use frozen/slotted dataclasses and `Literal` block types. Represent `JsonValue` recursively as null/bool/finite int or float/string/list/object, reject bool-as-int for structural IDs/levels, and normalize mappings to deterministic plain dictionaries/tuples. Make `DocumentSchemaError(ValueError, NovelMcpError)` expose class/instance `code = "DOCUMENT_SCHEMA_ERROR"`. Parse JSON with `parse_constant` that raises, reject non-object top-level values, dispatch on `schema_version`, then validate the exact v1 envelope and exact block fields. Normalize inline fragments through the inline public normalizer once that module is available; until Task 2, keep the schema test fixture plain-text-only and make the schema boundary call a local seam that Task 2 replaces without widening the public contract. Serialize using fixed envelope/block key order, sorted attribute/annotation keys, `ensure_ascii=False`, `allow_nan=False`, compact separators, and no trailing newline.

- [ ] **Step 4: Run the target and adjacent CORE tests.**

  Run `uv run pytest -q tests/test_document_schema.py` and then `uv run pytest -q tests/test_document_schema.py tests/test_installed_wheel.py`. Expected result: schema tests pass and the existing wheel smoke remains green.

- [ ] **Step 5: Commit the first logical boundary.**

  Stage only the plan, `errors.py`, the new document package files, and `test_document_schema.py`; commit with `feat: add Phase E document schema engine`.

### Task 2: Restricted Inline HTML

**Files:**
- Create: `CORE/src/novel_core/document/inline_html.py`
- Modify: `CORE/src/novel_core/document/schema.py`
- Test: `CORE/tests/test_document_inline_html.py`
- Modify: `CORE/tests/test_document_schema.py`

**Interfaces:**
- Consumes: Canonical block `html` fragments from Task 1.
- Produces: `parse_inline_html(fragment)`, `serialize_inline_html(parsed)`, `normalize_inline_html(fragment)`, and `base_visible_text(fragment)`; the AST remains an implementation detail.

- [ ] **Step 1: Write failing strict-parser tests.**

  Test plain text containing `<`, `>`, `&`, quotes, Japanese, nested `strong`/`em`, ordinary `em`, `em data-emphasis="dot"`, `<br>` and `<br/>`, valid ruby, entity decoding followed by canonical escaping, and visible text where ruby reading is excluded and `<br>` is `\n`. Reject span/a/script, unknown attributes, arbitrary emphasis attributes, comments/declarations/processing instructions, malformed tags, mismatched/unclosed tags, close tags for `br`, `rt` outside ruby, nested markup inside ruby base/reading, missing/duplicate/non-final/empty `rt`, empty ruby base, and non-empty invalid `rt` structures. Assert that normalized fragments are deterministic and schema parsing uses the same validator.

  ```python
  def test_ruby_reading_is_not_part_of_base_visible_text() -> None:
      fragment = "<strong>東京</strong><ruby>駅<rt>えき</rt></ruby><br>次"
      assert base_visible_text(fragment) == "東京駅\n次"
      assert normalize_inline_html(fragment) == (
          "<strong>東京</strong><ruby>駅<rt>えき</rt></ruby><br>次"
      )
  ```

- [ ] **Step 2: Run the inline target to observe RED.**

  Run `uv run pytest -q tests/test_document_inline_html.py`. Expected result: collection/import failure for the missing inline module, followed by ordinary assertion failures only after the test imports are corrected.

- [ ] **Step 3: Implement a strict stdlib parser and canonical AST serializer.**

  Subclass `html.parser.HTMLParser(convert_charrefs=False)`, maintain an explicit stack, reject every non-whitelisted tag/attribute and every construct callback outside text/start/end tags, and reject any unclosed/mismatched nesting. Decode text/entity callbacks into internal text nodes; use plain text only inside ruby and enforce exactly one final non-empty `rt`. Accept only the empty-attribute `em[data-emphasis="dot"]` form. Treat `br` as a void node. Serialize all text with deterministic escaping, lower-case allowed tags, the exact emphasis-dot attribute, and no browser repair. Make `normalize_inline_html` parse then serialize and make `base_visible_text` walk the AST while excluding ruby `rt` and converting `br` to newline. Wire schema normalization/validation to this function so Canonical HTML is always restricted and deterministic.

- [ ] **Step 4: Run inline, schema, and adjacent CORE tests.**

  Run `uv run pytest -q tests/test_document_inline_html.py tests/test_document_schema.py`. Expected result: all new inline and schema tests pass with no change to legacy tests.

- [ ] **Step 5: Commit the inline boundary.**

  Stage only the inline module and the two intended test files plus the schema integration; commit with `feat: add restricted inline html`.

### Task 3: Restricted Authoring HTML and annotation projection

**Files:**
- Create: `CORE/src/novel_core/document/authoring_html.py`
- Modify: `CORE/src/novel_core/document/__init__.py`
- Test: `CORE/tests/test_document_authoring_html.py`
- Create: `tests/fixtures/phase_e_tiptap_roundtrip.html`

**Interfaces:**
- Consumes: `NovelDocument`, normalized inline fragments, `BlockType`, `JsonValue`, and formal IDs from Tasks 1–2.
- Produces: `AuthoringBlockInput`, `AnnotationProjection`, `parse_authoring_html(raw) -> tuple[AuthoringBlockInput, ...]`, and `serialize_authoring_html(document, annotation_projection=...) -> str`.

- [ ] **Step 1: Write failing parser/serializer tests.**

  Cover p with and without `data-np-type`, forced blockquote/heading/hr mapping, formal and correlation IDs, duplicate/empty IDs, omitted-vs-clear structural attrs, all annotation codecs, explicit removal, unknown attribute rejection, top-level whitespace, nested block rejection, inline fragment parsing, deterministic attribute ordering/escaping, all projection modes, note/quote/separator serialization, and Canonical → Authoring → parse semantic equality. Assert that an untyped p has `type_hint is None`; the E2 new/existing distinction is not guessed. Assert that complex annotations remain in the Canonical document even when omitted from HTML.

  ```python
  def test_omitted_paragraph_type_stays_unresolved() -> None:
      parsed = parse_authoring_html('<p id="correlation-1">本文</p>')
      assert parsed[0].type_hint is None
      assert parsed[0].supplied_id == "correlation-1"

  def test_emotions_and_string_annotations_round_trip() -> None:
      html = '<p id="x" data-np-type="dialogue" data-ann-emotions="[&quot;焦り&quot;]" data-ann-snack-count="3">急いで</p>'
      block = parse_authoring_html(html)[0]
      assert block.annotations == {"emotions": ["焦り"], "snack-count": "3"}
  ```

- [ ] **Step 2: Run the Authoring target to observe RED.**

  Run `uv run pytest -q tests/test_document_authoring_html.py`. Expected result: collection/import failure for the missing Authoring module or named types.

- [ ] **Step 3: Implement strict outer parsing, typed input, and projection.**

  Parse only top-level `p`, `blockquote`, `h1`–`h3`, and `hr`; ignore only inter-block whitespace text; reject non-whitespace top-level text, nested outer tags, unknown attributes, unknown `data-np-*`, empty `data-np-type`, forced-tag type ambiguity, invalid positive decimal IDs, and duplicate non-empty IDs. Store omitted scene/speaker keys absent from the explicit-attrs mapping and empty values as explicit `None`. Preserve any non-formal supplied ID as a request-local correlation value. Parse `data-ann-<lowercase-ascii-kebab-case>` as strings, parse only `data-ann-emotions` as a JSON string array, reject invalid removal arrays/duplicates, and preserve set/remove separately.

  Use `AnnotationProjection(mode: Literal["none", "selected", "all"], keys=tuple[str, ...])`. Project only `emotions` lists of strings and unknown Canonical strings whose keys match the HTML namespace; do not stringify complex/non-string values. Serialize Canonical blocks with formal IDs, deterministic structural attrs, forced outer tags, normalized inline HTML, notes, and the requested projection. For p blocks emit the explicit type so semantic type survives a round trip; never emit `data-np-type` on forced tags.

- [ ] **Step 4: Run the Authoring, inline, and schema tests.**

  Run `uv run pytest -q tests/test_document_authoring_html.py tests/test_document_inline_html.py tests/test_document_schema.py`. Expected result: all three new CORE boundaries pass.

- [ ] **Step 5: Commit the Authoring boundary and shared fixture.**

  Stage only `authoring_html.py`, `document/__init__.py`, the Authoring tests, and `tests/fixtures/phase_e_tiptap_roundtrip.html`; commit with `feat: add restricted authoring html`.

### Task 4: WEB Read and Context projections

**Files:**
- Create: `CORE/src/novel_core/document/projections.py`
- Modify: `CORE/src/novel_core/document/__init__.py`
- Test: `CORE/tests/test_document_projections.py`

**Interfaces:**
- Consumes: normalized `NovelDocument`, inline visible-text helpers, and Authoring outer-tag rules.
- Produces: `render_web_html(document, include_notes=False) -> str`, `ContextProjectionResult`, and `render_context_html(document, max_visible_chars=4000) -> ContextProjectionResult`.

- [ ] **Step 1: Write failing projection tests.**

  Assert WEB output keeps block IDs, rich inline/ruby semantics, heading/quote/separator structure, hides structural editing metadata and annotations, excludes notes by default, and includes notes only with `include_notes=True`. Assert Context output has no IDs/annotations, keeps type/scene/speaker, keeps inline/ruby markup, excludes notes, and returns HTML, selected block count, visible base-text character count, and `truncated`.

  ```python
  def test_context_selects_whole_tail_blocks_by_visible_text() -> None:
      document = make_document("A" * 3, "＊", "B" * 3)
      result = render_context_html(document, max_visible_chars=3)
      assert result.html == '<p data-np-type="narration">＊</p><p data-np-type="narration">BBB</p>'
      assert result.selected_block_count == 2
      assert result.visible_text_char_count == 3
      assert result.truncated is True
  ```

  Add a case where the final block alone exceeds the budget and is included whole, a case with adjacent zero-visible separator blocks, original-order output after reverse tail selection, and exclusion of notes without counting them as budget truncation.

- [ ] **Step 2: Run the projection target to observe RED.**

  Run `uv run pytest -q tests/test_document_projections.py`. Expected result: collection/import failure for `projections.py`.

- [ ] **Step 3: Implement pure rendering and whole-block tail selection.**

  Build outer tags directly from Canonical blocks. WEB uses IDs and only the minimum p `data-np-type`; it omits scene/speaker/heading editing attrs and annotations. Context omits IDs/annotations/notes while retaining type and scene/speaker. Select eligible non-note blocks from the end: include the first tail block even when its visible count exceeds the budget; thereafter include a block only when its addition stays within budget, always retain zero-visible neighboring blocks encountered before the first over-budget positive block, stop without cutting a block, reverse selected indexes back to original order, and compute the result fields from selected blocks.

- [ ] **Step 4: Run projection and adjacent CORE tests.**

  Run `uv run pytest -q tests/test_document_projections.py tests/test_document_authoring_html.py tests/test_document_schema.py`. Expected result: all projection and preceding engine tests pass.

- [ ] **Step 5: Commit the projection boundary.**

  Stage only `projections.py`, its public imports, and `test_document_projections.py`; commit with `feat: add manuscript projections`.

### Task 5: Narou exporter

**Files:**
- Create: `CORE/src/novel_core/document/exporters/__init__.py`
- Create: `CORE/src/novel_core/document/exporters/narou.py`
- Modify: `CORE/src/novel_core/document/__init__.py`
- Test: `CORE/tests/test_document_narou.py`

**Interfaces:**
- Consumes: normalized Canonical Documents and the inline AST parser; it does not call Authoring HTML serialization.
- Produces: `ExportWarning`, `ExportResult`, `export_document(document, format) -> ExportResult`, and `render_narou(document) -> ExportResult`.

- [ ] **Step 1: Write failing exporter tests.**

  Cover prose paragraph separation, strong/italic/emphasis-dot text retention with decoration dropped, `<br>` to newline, valid ruby conversion, 1–10 character ruby limits, base/reading degradation with `NAROU_RUBY_DEGRADED`, heading/quote text, fixed separator `＊　＊　＊`, note/metadata/ID exclusion, warning preservation, result media type `text/plain`, and explicit unknown-format failure.

  ```python
  def test_long_ruby_keeps_base_and_emits_warning() -> None:
      document = make_document('<ruby>ABCDEFGHIJK<rt>よみ</rt></ruby>')
      result = export_document(document, "narou")
      assert result.content == "ABCDEFGHIJK"
      assert [warning.code for warning in result.warnings] == ["NAROU_RUBY_DEGRADED"]
      assert result.warnings[0].block_id == document.blocks[0].id
  ```

- [ ] **Step 2: Run the exporter target to observe RED.**

  Run `uv run pytest -q tests/test_document_narou.py`. Expected result: collection/import failure for the exporter package.

- [ ] **Step 3: Implement the small dispatcher and direct renderer.**

  Dispatch only the exact `narou` format and raise `ValueError("unsupported export format: <format>")` for all other values. Render Canonical inline nodes directly: preserve text, drop strong/emphasis decoration, translate br to newline, convert valid ruby to `｜base《reading》`, retain ruby base for out-of-range base or reading and append a stable warning. Exclude note blocks and all metadata/IDs. Render heading/quote/prose as text paragraphs and separator as the fixed separator; join emitted blocks with exactly one blank line. Return `ExportResult(format="narou", media_type="text/plain", content=..., warnings=..., suggested_filename=None)`.

- [ ] **Step 4: Run exporter and all CORE document tests.**

  Run `uv run pytest -q tests/test_document_narou.py tests/test_document_projections.py tests/test_document_authoring_html.py tests/test_document_inline_html.py tests/test_document_schema.py`. Expected result: all five document test modules pass.

- [ ] **Step 5: Commit the exporter boundary.**

  Stage only the exporter package, public imports, and Narou tests; commit with `feat: add Narou document exporter`.

### Task 6: TipTap feasibility boundary

**Files:**
- Modify: `WEBUI/frontend/package.json`
- Modify: `WEBUI/frontend/package-lock.json`
- Create: `WEBUI/frontend/src/features/manuscript/tiptap/phaseEExtensions.ts`
- Create: `WEBUI/frontend/src/features/manuscript/tiptap/phaseEFeasibility.test.ts`
- Modify: `CORE/tests/test_document_authoring_html.py`
- Modify: `CORE/tests/test_installed_wheel.py`
- Create/consume: `tests/fixtures/phase_e_tiptap_roundtrip.html`

**Interfaces:**
- Consumes: the exact shared fixture and CORE Authoring parser contract.
- Produces: minimal TipTap extensions preserving block `id`, `data-np-type`, `data-np-scene-id`, `data-np-speaker-id`, `data-ann-emotions`, restricted ruby, and a dedicated emphasis-dot mark, plus the feasibility test only; no ManuscriptPage/runtime switch.

- [ ] **Step 1: Write failing shared-fixture tests before package/code implementation.**

  Add the fixture with dialogue, formal ID, scene, speaker, emotions, ruby, emphasis dot, note, heading, separator, quote, br, bold, and italic. CORE must parse the exact fixture and assert expected block metadata. WEBUI must load the same bytes into a TipTap `Editor`, serialize HTML, and compare semantic DOM values for tags, text, attributes, block order, ruby base/reading, dot-emphasis, and retained emotions; attribute order and harmless escaping differences are normalized by the DOM comparison.

  ```ts
  test("shared Phase E fixture survives TipTap semantic serialization", () => {
    const editor = new Editor({ extensions: phaseEExtensions });
    editor.commands.setContent(fixtureHtml);
    const serialized = editor.getHTML();
    expect(semanticHtml(serialized)).toEqual(semanticHtml(fixtureHtml));
    editor.destroy();
  });
  ```

- [ ] **Step 2: Run the WEBUI target to observe RED.**

  Run `npm test -- --run src/features/manuscript/tiptap/phaseEFeasibility.test.ts` from `WEBUI/frontend`. Expected result: package/module resolution failure because TipTap and the extension file do not yet exist. Run the CORE fixture test separately with `uv run pytest -q tests/test_document_authoring_html.py` and keep it green before changing the WEBUI side.

- [ ] **Step 3: Install the current official minimal TipTap package set and implement extensions.**

  Confirm package names with npm, then add only `@tiptap/core`, `@tiptap/pm`, `@tiptap/extension-document`, `@tiptap/extension-text`, `@tiptap/extension-paragraph`, `@tiptap/extension-blockquote`, `@tiptap/extension-heading`, `@tiptap/extension-horizontal-rule`, `@tiptap/extension-hard-break`, `@tiptap/extension-bold`, and `@tiptap/extension-italic` using the repository's existing package style. Extend paragraph/blockquote/heading/horizontal-rule nodes with only the required block attrs. Add an inline ruby node that parses/serializes `<ruby>base<rt>reading</rt></ruby>` semantically, and a dedicated `em[data-emphasis="dot"]` mark separate from italic. Restrict italic parsing to ordinary `<em>` so it does not consume dot emphasis. Keep unknown annotations out of the projection and do not import or modify ManuscriptPage.

- [ ] **Step 4: Run shared CORE and WEBUI feasibility tests.**

  Run `uv run pytest -q tests/test_document_authoring_html.py tests/test_installed_wheel.py` from `CORE`, then `npm test -- --run src/features/manuscript/tiptap/phaseEFeasibility.test.ts` from `WEBUI/frontend`. Expected result: both pass using the identical fixture. If TipTap serialization changes harmless attr ordering/escaping, compare DOM semantics rather than weakening the CORE parser.

- [ ] **Step 5: Commit the feasibility boundary.**

  Stage only package manifests/lockfile, the two TipTap files, the shared fixture test additions, and installed-wheel assertion; commit with `test: validate TipTap document boundary`.

### Task 7: Public exports, wheel verification, and full regression

**Files:**
- Modify: `CORE/src/novel_core/document/__init__.py`
- Modify: `CORE/tests/test_installed_wheel.py`
- No changes: `API/`, `MCP/`, `CORE/migrations/`, stable data, ManuscriptPage, manuscriptApi, current body editor.

**Interfaces:**
- Consumes: all E1 package modules from Tasks 1–6.
- Produces: a wheel-importable `novel_core.document` public surface with no private-parser imports required by callers.

- [ ] **Step 1: Write the public-import and wheel assertions.**

  Assert the package-level imports for model/schema/inline/Authoring/projection/export result types work, and extend the installed wheel smoke subprocess to import `novel_core.document`, call `new_block_id`, and assert `is_formal_block_id` without adding a migration or changing the existing migration inventory assertion.

- [ ] **Step 2: Run the focused public-surface test to observe RED if exports are incomplete.**

  Run `uv run pytest -q tests/test_installed_wheel.py tests/test_document_schema.py tests/test_document_authoring_html.py tests/test_document_projections.py tests/test_document_narou.py`. Expected result is either pass if the prior implementation already exported everything or a focused import failure identifying the missing public export.

- [ ] **Step 3: Complete only the explicit public imports and wheel package data behavior.**

  Export stable model types, parsers/serializers, projection functions/result, Authoring types/functions, and exporter types/functions from `novel_core.document`. Keep private AST/parser helpers unexported. Do not alter setuptools dependencies or migration package data; the new Python modules must be included by package discovery.

- [ ] **Step 4: Run all required verification gates.**

  From `CORE`, run:

  ```powershell
  uv sync --all-groups
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy src
  uv run pytest -W error
  uv run pytest -W error --cov=src/novel_core --cov-report=term-missing
  uv run pytest -W error tests/test_installed_wheel.py -q
  ```

  From `WEBUI/frontend`, run:

  ```powershell
  npm ci
  npm run lint
  npm run typecheck
  npm test -- --run
  npm run build
  ```

  At repository root run `git diff --check`; inspect `git diff --name-only origin/main...HEAD`; assert migrations list exactly 001–004, no 005 exists, MCP tool count remains 59, `data/2126` is unchanged, and no API/MCP/unrelated files are in the E1 diff.

- [ ] **Step 5: Commit any final public-surface-only correction and stop at review handoff.**

  If Step 4 finds a real public-export defect, make a failing test first, fix only that defect, rerun the affected gate, and commit with `fix: finalize document engine exports`. Otherwise leave the existing logical commits intact. Push `codex/phase-e-e1-document-engine` normally; do not force-push, rebase public history, merge, create a PR, or begin E2.

## Completion report checklist

Before reporting completion, record the branch, `origin/main` base SHA, final HEAD, all commits, changed files, this plan path, public Document Engine interfaces, added tests, TipTap packages, fixture feasibility result, CORE/WEBUI verification output, migration 005 absence, migrations 001–004 identity, MCP tool count 59, stable `data/2126` untouched, preserved user files, any unrun checks with the exact reason, pushed branch, and that ChatGPT review is pending.
