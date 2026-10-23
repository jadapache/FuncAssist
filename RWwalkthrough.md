# Walkthrough: Dynamic and Multimodal LLM Chat Implementation

This document summarizes the changes introduced to enable dynamic, conversational, and multimodal interactions with the LLM in QA_MGMT, moving beyond rigid template generation to support open Q&A, slash commands (`/plan`, `/informe`), image uploads, and extraction of reviewed document tables.

---

## 1. Architecture Overview

Prior to this implementation, the chat interface strictly executed `run_grounded_feature_stream`. If no RAG context chunks matched, the backend raised a hard `RuntimeError("Not found in connected sources")`, and the frontend expected code-block artifacts that overwrote or opened the document preview panel.

The new architecture decouples open conversational queries from document mutations and adds multimodal vision support:

```
[User Input] (Text + Images + Attached Documents)
      |
      v
[Intent Classifier] (`classify_prompt_intent`)
      |
      +---> `chat`             --> Direct conversational response in chat bubble (no panel mutation)
      +---> `generic_plan`     --> Plan artifact generation (test/implementation plan)
      +---> `generic_report`   --> Report artifact generation
      +---> `template_mutation`--> Updates corporate document templates
      |
      v
[Agentic Chat Runner] (`run_agentic_chat_stream`)
      |
      +---> Vision payload assembly via LiteLLM (`AIMessage.content` structure)
      +---> Dynamic system instructions per intent
      +---> Resilient RAG retrieval (graceful fallback when context is empty)
      |
      v
[Frontend Streaming & Parser]
      +---> Token-by-token live streaming directly into the assistant chat bubble
      +---> Attachment badges (images and documents) transferred into user bubble upon sending
      +---> Document preview panel opens ONLY when an explicit `<artifact>` is generated
```

---

## 2. Backend Enhancements

### 2.1 Multimodal Message Structure
- Modified [AIMessage](file:///c:/Dev/QA_MGMT/backend/app/ai/providers/base.py#L18) in `backend/app/ai/providers/base.py` to accept `Union[str, list[dict[str, Any]]]`.
- Supported data URL and remote image URLs compatible with LiteLLM and OpenAI-compatible vision models.

### 2.2 Extraction of Tables and Image Safeguards
- Updated [extract_text](file:///c:/Dev/QA_MGMT/backend/app/context/knowledge.py#L35) in `backend/app/context/knowledge.py`:
  - Added mime-type safeguards for image files to prevent binary corruptions.
  - Enhanced `_extract_docx` to iterate through `document.tables`, converting cells and rows into readable Markdown tables to preserve reviewed test tables.

### 2.3 Intent Classification and Conversational Guards
- Enhanced [classify_prompt_intent](file:///c:/Dev/QA_MGMT/backend/app/api/document_agent.py#L42) in `backend/app/api/document_agent.py`:
  - Recognizes questions and conversational inquiries (`¿...?`, `qué`, `cómo`, `cuál`, `explica`, etc.) and routes them to `chat`.
  - Natural language report and plan requests (`genera informe que...`, `crea un plan...`) are routed to `generic_report` and `generic_plan`.
  - Added guards in `handle_agentic_prompt` and `handle_agentic_prompt_stream` so conversational questions never trigger mock fast-correction operations.

---

## 3. Frontend Enhancements

### 3.1 Document & Image Attachment Lifecycle
- **Input Bar**: Selected documents and images display as detachable chips. Clicking the `(X)` detach button removes them cleanly from the prompt without triggering destructive backend delete calls or 404 error toasts.
- **Message Bubble**: When a prompt is submitted:
  - Both image thumbnails and document chips are transferred directly into the user message bubble (`Tú`).
  - The input bar is immediately cleared.
  - Documents and images are passed to the backend agent to provide context.

### 3.2 Live Token Streaming & Removal of 5-Point Checklist
- Refactored [AgenticThinkingBubble](file:///c:/Dev/QA_MGMT/frontend/src/features/document/components/AgenticThinkingBubble.tsx):
  - Removed the bulky 5-point Inspect-Plan-Execute-Verify checklist.
  - Replaced with a subtle, modern inline status indicator (`Pensando...`, `Generando plan...`).
- Updated [useAgenticGeneration](file:///c:/Dev/QA_MGMT/frontend/src/features/document/hooks/useAgenticGeneration.ts):
  - Streams response tokens live into the active assistant chat bubble.
  - Conversational Q&A is strictly separated from document mutation: chat queries never overwrite artifacts or force-open the document panel.

### 3.3 Artifact Splitter Heuristic Protection
- Updated [parseStreamForChatAndArtifacts](file:///c:/Dev/QA_MGMT/frontend/src/utils/artifactSplitter.ts#L256):
  - Requires explicit `<artifact>` XML tags before marking text as non-conversational.
  - Prevents conversational answers containing Markdown headings from accidentally splitting into synthetic document artifacts.

---

## 4. Verification

### 4.1 Automated Backend Tests
Ran the full unit test suite in `backend/tests/unit/test_document_agent_intent.py`:
```
backend\tests\unit\test_document_agent_intent.py::test_classify_prompt_intent_slash_commands PASSED
backend\tests\unit\test_document_agent_intent.py::test_classify_prompt_intent_qa_and_template PASSED
backend\tests\unit\test_document_agent_intent.py::test_classify_prompt_intent_explicit_mode PASSED
backend\tests\unit\test_assemble_multimodal_message_text_only PASSED
backend\tests\unit\test_assemble_multimodal_message_with_images PASSED
backend\tests\unit\test_extract_docx_with_paragraphs_and_tables PASSED
backend\tests\unit\test_extract_text_image_safeguard PASSED
7 passed in 3.65s
```

### 3.4 Markdown Rendering in Chat Bubbles
- Added [MarkdownMessage](file:///c:/Dev/QA_MGMT/frontend/src/features/document/components/MarkdownMessage.tsx):
  - Renders assistant chat bubbles and active streaming responses using `react-markdown`.
  - Parses Markdown titles (`h1`-`h3`), bullet lists, numbered lists, blockquotes, code snippets, and structured tables cleanly instead of showing raw symbols (`**`, `###`, `|`).
  - Styled with WCAG-compliant high-contrast styles, matching the application design system without decorative icons or emojis.

### 3.5 Ephemeral Chat Attachments (Isolated from Knowledge Base)
- **Problem solved**: Previously, picking a document in the chat prompt triggered `api.uploadDocumentsBatch`, immediately saving it to the permanent RAG database (pgvector).
- **In-memory parsing**: Added `POST /api/doc-agent/parse-attachment` which extracts text and tables from DOCX, PDF, XLSX, and TXT files directly in memory using `extract_text`.
- **Clean Separation**:
  - Ephemeral attachments in chat are sent directly within the prompt context (`attached_docs`) to the LLM runner without writing to the RAG database or disk.
  - The Knowledge Base remains strictly clean: only documents uploaded intentionally in the Knowledge Base module or final generated artifacts saved by the user are stored.

---

## 5. Database-Driven Prompt & Rubric Templates (Eliminating Hardcoded Prompts)

### 5.1 Industry Standard Alignment
- **Validation**: Hardcoding system prompts directly inside execution code violates separation of concerns. Industry standards (LangChain Hub, Dify, Bedrock Prompt Management) mandate a versioned Prompt Repository in PostgreSQL with runtime governance via UI.
- **Seeds & Defaults**:
  - Added factory seeds in [seeds.py](file:///c:/Dev/QA_MGMT/backend/app/ai/seeds.py) for `generic_plan` and `generic_report`, defining role, objectives, and `<chat>` / `<artifact>` dual-block contracts.
  - Replaced hardcoded string prompts in [runner.py](file:///c:/Dev/QA_MGMT/backend/app/ai/runner.py) with dynamic asynchronous retrieval via `await get_prompt(feature)` from the database.

### 5.2 Creation of Custom Prompts via UI & API
- **Backend Upsert**: Updated [template_repository.py](file:///c:/Dev/QA_MGMT/backend/app/db/repositories/template_repository.py) and [templates.py](file:///c:/Dev/QA_MGMT/backend/app/ai/templates.py) to support creating brand-new prompt template records (`AITemplateModel` + `AITemplateVersionModel` v1) via `POST /api/ai/prompts`.
- **UI Management**:
  - In [AiPromptsRubricsEditor.tsx](file:///c:/Dev/QA_MGMT/frontend/src/features/settings/components/AiPromptsRubricsEditor.tsx), added a **"Nuevo Prompt"** button and creation modal with fields for identifier slug, display name, category, role/objective, and output structure.
  - Custom prompts are badged with a "Personalizado" tag in [FeatureSelectorSidebar.tsx](file:///c:/Dev/QA_MGMT/frontend/src/features/settings/components/prompts_rubrics/FeatureSelectorSidebar.tsx).

---

## 6. Dynamic Chat & Clean Artifact Separation

### 6.1 Dynamic Slash Command Dispatching
- Replaced rigid, multi-nested `if (isPlan) ... else if (isReport)` branching in [useAgenticGeneration.ts](file:///c:/Dev/QA_MGMT/frontend/src/features/document/hooks/useAgenticGeneration.ts) with isolated `resolveIntentAndStatus`.
- Supports standard slash commands (`/plan`, `/informe`, `/plantilla`) and any custom prompt slug (`/<slug>`).
- Populates dynamic shortcut chips in [AgenticDocumentWorkspace.tsx](file:///c:/Dev/QA_MGMT/frontend/src/features/document/components/AgenticDocumentWorkspace.tsx) directly from the registered database prompts.

### 6.2 Dual-Block Protocol (<chat> vs <artifact>)
- **The Problem**: When generating an artifact, previous versions would either dump the raw multi-page Markdown into the chat bubble or leave the chat bubble empty.
- **Solution in [artifactSplitter.ts](file:///c:/Dev/QA_MGMT/frontend/src/utils/artifactSplitter.ts) and [artifacts.py](file:///c:/Dev/QA_MGMT/backend/app/ai/artifacts.py)**:
  - System prompts instruct the LLM to output a `<chat>` greeting/summary block followed by an `<artifact title="..." extension="...">` document block.
  - Streaming and completion parser extracts `<chat>...</chat>` strictly into the assistant chat bubble.
  - The `<artifact>` document is parsed in real time and directed to the artifact canvas / document studio.
  - The chat bubble never displays raw Markdown or XML artifact markup.

---

## 7. Verification Results

### 7.1 Backend Unit Tests
Ran `pytest backend/tests/unit/ -v`:
- **85 passed out of 85 tests (100% pass rate)**.
- Verified custom prompt creation: `test_create_custom_prompt` PASSED.
- Verified dynamic intent resolution and multimodal parsing: all PASSED.

### 7.2 Frontend Type Checking & Linting
- `npm run typecheck` (`tsc -b`): **0 errors** (code 0).
- `npx oxlint`: **0 errors** (code 0).
- Confirmed zero emojis across all newly modified UI and backend modules.
