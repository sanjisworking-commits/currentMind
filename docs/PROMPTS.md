# PROMPTS.md

# CurrentMind Prompt Documentation

This document describes how prompts are structured, versioned, and stored. The
prompt **files themselves remain authoritative** — this document never copies
their text, and it never documents raw provider output. For the decision
behind the prompt architecture, see ADR-022.

---

## 1. Active version

The active prompt version is **`v1`**. Both provider adapters define it and
derive the same authoritative prompt filenames from it:

```python
PROMPT_VERSION = "v1"   # app/infrastructure/openai_generator.py
PROMPT_VERSION = "v1"   # app/infrastructure/anthropic_generator.py
```

Both prompt filenames are derived from this constant, so bumping the version
without adding the corresponding files fails immediately (a clear
`FileNotFoundError`) rather than silently reusing stale prompts. The two
adapters share the same source-neutral prompt files and must keep the same
`PROMPT_VERSION` value: the constant (and the small prompt-rendering helpers)
are **intentionally duplicated** between the adapters rather than centralized
(ADR-026), so the two definitions must remain aligned. This correction does not
extract or centralize them; if a third provider is added, ADR-026 flags
extracting the shared pieces then.

## 2. Authoritative prompt files

```text
prompts/learning_note_v1_system.txt
prompts/learning_note_v1_user.txt
```

The system prompt frames the model as a UPSC analyst and defines the untrusted
source-data boundary. The user prompt carries the article material inside
labelled, delimited blocks. These files are the single authority for wording;
this document only describes their contract.

## 3. Placeholder contract

Prompts are plain UTF-8 rendered with the standard library's
`string.Template` (`$identifier` syntax, `.substitute()` — never
`.safe_substitute()`, so a missing or unknown placeholder fails loudly). The
loader (`app/infrastructure/prompt_loader.py`) validates the exact placeholder
set at load time.

The user prompt contains exactly three placeholders:

| Placeholder          | Filled with                                             |
| -------------------- | ------------------------------------------------------- |
| `article_metadata`   | Title, source, URL, author, publication date, categories |
| `article_text`       | The accepted extracted article body                     |
| `repair_instruction` | Empty on the first attempt; sanitized schema-error hints on a repair attempt |

The system prompt contains no placeholders.

## 4. Relationship to `LearningNoteContent`

The model is asked, via each provider's native structured-output parsing, to
return output matching `LearningNoteContent` exactly — the 15 AI-authored
fields, every one required, with explicit empty lists where a category does not
apply. Both adapters bind the schema the same way:

* OpenAI: `responses.parse(..., text_format=LearningNoteContent)`
* Anthropic: `messages.parse(..., output_format=LearningNoteContent)`

In both adapters **Pydantic is the sole validator** of model output (via each
SDK's own `LearningNoteContent` validation); there is no manual JSON parsing,
Markdown-fence stripping, or regex extraction in either. Trusted metadata is
**not** part of `LearningNoteContent` and is supplied locally by
`assemble_learning_note()` (shared application code), so the model cannot
influence it regardless of provider.

## 5. Untrusted-input delimiters

All supplied article material — every metadata field **and** the article body
— is treated as untrusted source data. The user prompt places metadata and
body in separately labelled `BEGIN/END … (UNTRUSTED SOURCE DATA)` blocks, and
the system prompt instructs the model to ignore any instructions, role
changes, schema changes, or delimiter-looking text inside that data. This is
prompt-injection **resistance** through explicit boundaries — not a
mathematical guarantee (ADR-022).

## 6. Repair-attempt behavior

Structured-output generation makes at most **three** application-level
attempts in **both** adapters: one original request plus up to two repair
retries. A repair retry occurs only for a Pydantic `ValidationError` during
parsing, or a completed response with no parsed content. The
`repair_instruction` placeholder is filled with **sanitized** error hints
(field location and error type/message only — never the rejected value, never a
raw exception rendering). Provider outcomes — refusals, incomplete/truncated
responses, unexpected stop reasons or statuses, and any transport/SDK error —
are **not** application-retried by either adapter; each becomes an immediate
`LearningNoteProviderError`. Transport-level retry belongs to the **selected**
provider SDK (`max_retries`, default 2 for both) and operates separately
underneath the application policy; it is configured at client construction, not
by application code. See ADR-023 for the full attempt budget and ADR-026 for the
second provider.

## 7. Model-name and prompt-version storage

Every persisted `LearningNote` records both the `model_name` and the
`prompt_version` used to generate it. This makes each note self-describing:
notes generated under different models or prompt versions remain
distinguishable after the fact.

## 8. Introducing a future `v2`

1. Add `prompts/learning_note_v2_system.txt` and
   `prompts/learning_note_v2_user.txt` (keeping the same placeholder contract
   unless a deliberate schema change is also made).
2. Bump `PROMPT_VERSION = "v2"`.
3. If the structured-output schema changes, update `LearningNoteContent` and
   its tests together.
4. Add or update tests covering the new prompt boundaries.
5. Record the change (and any schema impact) in `docs/DECISIONS.md`.

## 9. Backward compatibility

Existing notes keep the `prompt_version` they were generated under; nothing
rewrites historical notes when a new version is introduced. The dashboard
renders notes regardless of their stored version, since it reads the
structured fields, not the prompt.

## 10. Privacy constraints

Prompts, rendered prompt text, and raw provider responses are never logged or
displayed during normal operation. Repair instructions sent back to the model
exclude rejected input values. See ADR-022 and `docs/ARCHITECTURE.md` §10.

## 11. Fact-verification limitation

The system prompt instructs the model to stay grounded in the supplied
article, avoid inventing constitutional provisions/cases/reports/schemes/
statistics, and distinguish article facts from analytical inference. There is
**no** independent fact-checking, web verification, or retrieval step:
generated Learning Notes may still contain model error and must be reviewed
before being relied upon for study.
