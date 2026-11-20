# Question-answering (RAG) design and evaluation

How MediCore answers a health question, what it searches, how it behaves when it is unsure, and how well that
works. All numbers below were measured by `python -m app.rag.qa_evaluation` and are stored in
`models/rag/qa_evaluation.json` (also served at `GET /api/rag/qa-evaluation`).

## 1. Trusted sources

| Source | Status | How it is read | Documents |
|---|---|---|---|
| WHO | ✅ indexed | Public fact-sheet pages | 16 |
| CDC | ✅ indexed | CDC's official content-syndication API (the main site refuses automated clients, so it is not crawled) | 53 |
| MedlinePlus (NIH) | ✅ indexed | NIH's official daily XML feed of every health topic | 1,017 |
| PubMed | ✅ indexed | NCBI E-utilities: guidelines and reviews with abstracts | 62 |
| NHS | ⚙️ ready, **needs a key** | NHS website content API. Without a free subscription key it answers 401. Set `NHS_API_KEY` and run the build. The adapter is tested with mocked responses and **has not been run against the live API** | 0 |
| Mayo Clinic | ❌ not indexed | No public API, and the site returns 403 to automated clients (even `robots.txt`). We do not scrape it. If you hold a content licence, put JSON files in `data/external/licensed/mayo_clinic/` and they are indexed like any other source | 0 |

Every document keeps its **source name, URL, document type, publication or "current as of" date and chunk id**
(`models/rag/chunks.jsonl`, `manifest.json`). For MedlinePlus the date is the feed's generation date, because the feed
does not carry a per-topic update date; the topic's original creation date is kept as metadata.

Rebuild: `python -m src.rag_ingestion.build_index` (all sources) or `--sources medlineplus,nhs`.

## 2. Pipeline

```
question
 ├─ understand   spelling repair · everyday phrase → medical terms ("tummy ache" → abdominal pain) · query rewrites
 │               · symptom detection · safety triage (emergency / urgent / diagnosis / medicine request)
 ├─ 1 direct     hybrid search on the corrected question:  FAISS vectors  +  BM25 keywords  → reciprocal-rank fusion
 ├─ 2 rewritten  if the evidence is not strong: also search the rewrites (+ optional Gemini rewrites)
 ├─ 3 per-source if still not strong: search each trusted source on its own
 ├─ rank         relevance (0.50) · keyword match (0.10) · source authority (0.12) · freshness (0.06)
 │               · question-word coverage (0.08) · title agreement (0.07)  [weights in app/rag/hybrid.py]
 ├─ select       drop near-duplicate passages · ≤ 2 chunks per document · no single source dominates
 └─ judge        strong | limited | none   (needs real word overlap, not just similarity)
```

| Evidence | What the user gets |
|---|---|
| **strong** | A full cited answer (Gemini if configured; otherwise sentences quoted from the sources) |
| **limited** | A cautious answer that says the sources only partly match. With Gemini it may add a section labelled **General background (not from the sources above)**, which is not checked against the sources and is flagged as less certain. Without Gemini: quoted sentences with the same warning |
| **none** | "I could not find a reliable answer", plus follow-up questions and a see-a-clinician line for symptoms. Nothing is invented and no citations are made up |
| no topic ("What does this medical term mean?") | The assistant asks which term you mean |

A high similarity score is never treated as proof that a passage is medically correct.

### Answer format
`Short answer` · `What may explain it` (symptoms) · `What you can do` · `When to get medical help` ·
`A few questions that could help` (when symptoms are unclear) · and the sources, with links, shown under the answer.
Gemini follows this format via its prompt. In quoted mode the same sections are filled with sentences copied from the
sources, each with its citation.

### Safety
* Emergency wording (chest pain, stroke signs, severe allergic reaction, …) shows an emergency alert.
* Urgent patterns (baby with a fever, blood in urine/stool, stiff neck with fever, …) add "this may need prompt medical advice".
* Requests for a diagnosis ("Do I have diabetes?") or a medicine/dose ("What can I take for a headache?") are answered with
  general information only, with a clear statement that MediCore cannot diagnose or recommend medicines. Sentences with
  doses are never quoted, and advice to take a medicine is dropped when a medicine was asked about.
* "Why do I have a headache?" is an explanation question, not a diagnosis request.
* After generation, every sentence is compared with the sources; unmatched ones are marked.

## 3. Evaluation

Benchmark: `data/external/rag_benchmark_v2.json`, 80 questions built by `python -m src.rag_ingestion.benchmark_v2`.
Categories: symptoms (10), medical terms (9), conditions (6), prevention (5), lab-report questions (5), misspelled or
incomplete (7), casual wording (12), hard/indirect wording (14), safety (7), out of scope (5). Reference pages were chosen
from the library by page URL and kept only if they exist and contain the required word. 69 questions are **held out**
(never used while tuning thresholds); 11 were used as a development set.

### Retrieval relevance (K = 4, questions with reference pages)

| Strategy | Precision@4 | Recall@4 | Hit@4 | MRR |
|---|---|---|---|---|
| Basic (vectors only) | 0.446 | 0.564 | 0.814 | 0.721 |
| Adaptive (previous default) | 0.400 | 0.577 | 0.857 | 0.748 |
| **Hybrid (new default)** | **0.496** | **0.633** | **0.886** | **0.801** |

Held-out only (61 questions): hybrid Hit@4 0.885, MRR 0.787 against basic 0.803 / 0.708.

Where it helps and where it does not:

| Category | Hit@4 basic → hybrid | MRR basic → hybrid |
|---|---|---|
| Misspelled / incomplete | 0.43 → **1.00** | 0.43 → **1.00** |
| Casual wording | 0.83 → 0.83 | 0.67 → 0.73 |
| Medical terms | 0.75 → 0.88 | 0.69 → 0.72 |
| Hard / indirect wording | 0.93 → 0.93 | 0.89 → 0.82 |

The gain comes mostly from spelling repair and everyday-phrase mapping. On vaguely worded questions, hybrid is **not**
better than plain vector search (its MRR is slightly lower).
Much of the other improvement comes from adding MedlinePlus: even the old strategy now finds the right topic for most
everyday questions.

### Answers, citations and fallbacks (hybrid, quoted-sentence answers)

| Measure | Result |
|---|---|
| Citations that point to an existing source | **100 %** |
| Citations that point to a reference page | 66.9 % (cited pages can be relevant without being in the short reference list) |
| Answer correctness, automatic proxy: answers matching ≥ half of the reference key points | 92.9 % (mean coverage 0.84) |
| Statements flagged "not found in the sources" | 3 of 362 (0.8 %) |
| Correct fallback behaviour: answer / decline / clarify / emergency alert / no diagnosis or dose / urgent note | 80 of 80 |
| Answered directly vs. needed the rewrite / other-source stages | 68 vs. 2 |
| Median time to answer (CPU, no LLM) | 1.5 s |

### Honest limits of these numbers
* **The answer-correctness figure is an automatic proxy** (embedding match to key points), not a clinician's review.
* The reference pages come from one annotator; there is no inter-rater agreement.
* The **fallback scores are not independent**: two safety patterns were found missing by this benchmark (a drooping-face
  phrasing and "what medicine can I take…") and then fixed, so those items are no longer a fair test.
* The fallback stages were needed for only 2 of 70 answerable questions, so their benefit is demonstrated mainly by unit
  tests (`tests/test_rag_hybrid.py`), not by this benchmark.
* **Gemini-written answers have not been evaluated** (no key was available). With a key, run
  `python -m app.rag.qa_evaluation --llm`.
* Thresholds were tuned on a small development set; the held-out rows exclude it.
* Answers are only as good as the sources: they come from US-centred pages (CDC, MedlinePlus) plus WHO, and the library
  has no NHS or Mayo Clinic content unless you add it.
