"""RAG benchmark: questions, reference evidence (doc-level relevance labels) and reference answers.

Labelling protocol (documented so results can be audited):
  * Questions were written to cover the platform's scope (definitions, comparisons, thresholds, risk
    factors, lifestyle, multi-part questions) plus out-of-scope questions that SHOULD be refused.
  * Candidate reference documents were chosen by the author from the corpus manifest (titles and
    content), not from retrieval output, to avoid biasing labels toward the retriever.
  * A candidate is kept only if it exists in the corpus and contains every `must_contain` term
    (case-insensitive). Dropped candidates are reported.
  * `key_points` are short facts a correct answer should contain; they are drawn from the reference
    documents and used for answer-relevance scoring when generation is evaluated.

Usage: python -m src.rag_ingestion.benchmark   (validates and writes data/external/rag_benchmark.json)
"""
import json
import logging

from src.config import DATA_RAW, ROOT

log = logging.getLogger("rag.benchmark")
OUT = ROOT / "data" / "external" / "rag_benchmark.json"

Q = [
    # id, question, type, candidate relevant docs, must_contain terms, key points
    ("q01", "What is diabetes?", "definition",
     ["who:diabetes", "cdc:335185", "pubmed:34708622", "cdc:234263"], ["insulin"],
     ["chronic disease", "insulin", "blood glucose / blood sugar"]),
    ("q02", "What is the difference between HDL and LDL cholesterol?", "comparison",
     ["who:dyslipidaemia", "pubmed:31071007", "pubmed:39043480", "pubmed:37307585", "cdc:229679"], ["ldl"],
     ["LDL is associated with plaque build-up in arteries", "HDL helps remove cholesterol"]),
    ("q03", "Explain hypertension using reliable medical sources.", "definition",
     ["who:hypertension", "cdc:229514", "pubmed:34019821", "pubmed:32024986", "pubmed:33793326"], ["blood pressure"],
     ["high blood pressure", "risk of heart disease and stroke", "often no symptoms"]),
    ("q04", "What blood pressure readings are used to diagnose hypertension?", "threshold",
     ["who:hypertension", "pubmed:33793326"], ["140", "90"],
     ["systolic at least 140 mmHg", "diastolic at least 90 mmHg", "measured on two different days"]),
    ("q05", "What does an HbA1c test measure?", "lab_term",
     ["pubmed:37471273", "who:diabetes"], ["hba1c"],
     ["average blood glucose over about 2-3 months", "used to diagnose and monitor diabetes"]),
    ("q06", "What is anaemia?", "definition",
     ["who:anaemia", "cdc:218528"], ["haemoglobin|hemoglobin"],
     ["insufficient red blood cells or haemoglobin", "reduced oxygen-carrying capacity"]),
    ("q07", "What are common causes of iron deficiency anaemia?", "risk_factors",
     ["pubmed:37497686", "pubmed:41252836", "pubmed:41525691", "pubmed:36706856", "who:anaemia", "cdc:218528"], ["iron"],
     ["blood loss (e.g. heavy menstrual bleeding)", "inadequate intake or absorption", "pregnancy"]),
    ("q08", "What is prediabetes?", "definition",
     ["cdc:281798", "cdc:416309", "cdc:335185", "cdc:234263"], ["prediabetes"],
     ["blood sugar higher than normal but not yet type 2 diabetes", "can often be reversed"]),
    ("q09", "What are the risk factors for type 2 diabetes?", "risk_factors",
     ["cdc:335185", "pubmed:41857071", "who:diabetes", "cdc:281798", "cdc:234263"], ["type 2"],
     ["overweight / obesity", "physical inactivity", "family history", "age"]),
    ("q10", "What is chronic kidney disease?", "definition",
     ["who:kidney-disease", "cdc:220027", "pubmed:31573641", "pubmed:41314225", "pubmed:34175022",
      "pubmed:39885176", "pubmed:31939529", "pubmed:40921075"], ["kidney"],
     ["gradual loss of kidney function", "diabetes and high blood pressure are common causes"]),
    ("q11", "What are the warning signs of a stroke?", "symptoms",
     ["cdc:125431", "cdc:220110", "cdc:421908", "cdc:729364"], ["stroke"],
     ["sudden numbness or weakness (often one side)", "sudden confusion or trouble speaking", "call emergency services"]),
    ("q12", "What are the symptoms of a heart attack?", "symptoms",
     ["who:heart-attack", "cdc:224874", "who:cardiovascular-diseases-(cvds)"], ["chest"],
     ["chest pain or discomfort", "pain in arms, jaw, back", "shortness of breath"]),
    ("q13", "How much physical activity do adults need each week?", "lifestyle",
     ["who:physical-activity", "cdc:226207"], ["150"],
     ["at least 150-300 minutes of moderate activity per week", "or 75-150 minutes vigorous", "muscle strengthening"]),
    ("q14", "How is obesity defined using BMI?", "threshold",
     ["who:obesity-and-overweight", "cdc:230305", "pubmed:39159652", "pubmed:38015216"], ["30"],
     ["BMI of 30 or more is obesity in adults", "BMI 25 or more is overweight"]),
    ("q15", "How does sodium intake affect blood pressure?", "lifestyle",
     ["cdc:125427", "cdc:422954", "cdc:222842", "who:healthy-diet", "who:hypertension"], ["sodium|salt"],
     ["too much sodium raises blood pressure", "reducing sodium lowers blood pressure"]),
    ("q16", "What does WHO recommend for a healthy diet?", "lifestyle",
     ["who:healthy-diet"], ["salt"],
     ["fruits and vegetables", "limit free sugars", "limit salt", "limit saturated / trans fats"]),
    ("q17", "What is vitamin D deficiency and how is vitamin D status measured?", "lab_term",
     ["pubmed:38828931", "pubmed:33549285", "pubmed:32972636"], ["vitamin d"],
     ["serum 25-hydroxyvitamin D", "bone health"]),
    ("q18", "What is gestational diabetes?", "definition",
     ["pubmed:31296866", "pubmed:34560536", "pubmed:35613728"], ["gestational"],
     ["diabetes first recognised during pregnancy", "risk to mother and baby"]),
    ("q19", "What is type 1 diabetes?", "definition",
     ["cdc:419813", "pubmed:35254878", "who:diabetes", "pubmed:34708622"], ["type 1"],
     ["the body makes little or no insulin", "autoimmune", "requires insulin"]),
    ("q20", "What are cardiovascular diseases?", "definition",
     ["who:cardiovascular-diseases-(cvds)", "cdc:224874", "who:heart-attack"], ["heart"],
     ["disorders of the heart and blood vessels", "include coronary heart disease and stroke"]),
    ("q21", "What is pre-eclampsia?", "definition",
     ["who:pre-eclampsia", "pubmed:35066406"], ["pre-eclampsia|preeclampsia"],
     ["high blood pressure in pregnancy", "after 20 weeks", "can affect organs"]),
    ("q22", "What is dyslipidaemia?", "definition",
     ["who:dyslipidaemia", "pubmed:37307585", "pubmed:37956957", "pubmed:37979064"], ["lipid"],
     ["abnormal levels of blood lipids", "raises cardiovascular risk"]),
    ("q23", "How can people prevent high cholesterol?", "lifestyle",
     ["cdc:229679", "who:dyslipidaemia"], ["cholesterol"],
     ["healthy diet low in saturated fat", "physical activity", "not smoking", "healthy weight"]),
    ("q24", "What is depression?", "definition",
     ["who:depression"], ["depress"],
     ["common mental disorder", "persistent low mood or loss of interest"]),
    ("q25", "How are diabetes and kidney disease related, and why does blood pressure matter?", "multi_part",
     ["who:kidney-disease", "who:diabetes", "cdc:220027", "pubmed:37053276", "pubmed:31573641", "pubmed:41314225"],
     ["kidney"],
     ["diabetes is a leading cause of kidney disease", "high blood pressure damages kidneys and is also a consequence"]),
    ("q26", "Does obesity increase the risk of cancer?", "risk_factors",
     ["cdc:418404", "who:obesity-and-overweight"], ["cancer"],
     ["obesity is linked to higher risk of several cancers"]),
    ("q27", "What does the eGFR test show about kidney function?", "lab_term",
     ["pubmed:31573641", "pubmed:41314225", "pubmed:34175022", "pubmed:39885176", "cdc:220027", "who:kidney-disease"],
     ["glomerular filtration"],
     ["estimated glomerular filtration rate", "how well kidneys filter blood"]),
    ("q28", "What are noncommunicable diseases and what are their main risk factors?", "multi_part",
     ["who:noncommunicable-diseases"], ["tobacco"],
     ["chronic diseases such as cardiovascular disease, cancer, diabetes, chronic respiratory disease",
      "tobacco use, physical inactivity, harmful alcohol use, unhealthy diet"]),
    ("q29", "Why does diabetes increase the risk of heart disease, and how can that risk be reduced?", "multi_part",
     ["who:diabetes", "pubmed:37193856", "cdc:224874", "who:cardiovascular-diseases-(cvds)", "cdc:235606"], ["heart"],
     ["diabetes damages blood vessels", "control blood pressure, cholesterol and glucose", "healthy lifestyle"]),
    ("q30", "Compare the health effects of physical activity and a healthy diet on preventing type 2 diabetes.", "comparison",
     ["who:physical-activity", "who:healthy-diet", "who:diabetes", "cdc:281798", "cdc:335185", "cdc:281797"],
     ["diabetes"],
     ["physical activity lowers diabetes risk", "healthy diet and weight help prevent type 2 diabetes"]),
    # out of scope / not covered -> the system should report insufficient evidence
    ("u01", "How do I change a flat tyre on a car?", "unanswerable", [], [], []),
    ("u02", "What is the capital city of Australia?", "unanswerable", [], [], []),
    ("u03", "How do I reset my router password?", "unanswerable", [], [], []),
    ("u04", "What is the incubation period of Lassa fever?", "unanswerable_medical", [], [], []),
    ("u05", "Which programming language is best for machine learning?", "unanswerable", [], [], []),
]


def build() -> dict:
    docs = {}
    for line in (DATA_RAW / "rag" / "documents.jsonl").read_text(encoding="utf-8").split("\n"):
        if line:
            d = json.loads(line)
            docs[d["doc_id"]] = (d["title"] + " " + d["text"]).lower()
    items, dropped = [], []
    for qid, question, qtype, cands, must, keys in Q:
        relevant = []
        for c in cands:
            text = docs.get(c)
            ok = text is not None and all(any(alt in text for alt in m.split("|")) for m in must)
            (relevant if ok else dropped).append(c if ok else f"{qid}:{c}")
        if qtype.startswith("unanswerable") or relevant:
            items.append({"id": qid, "question": question, "type": qtype, "relevant_doc_ids": relevant,
                          "key_points": keys, "answerable": not qtype.startswith("unanswerable")})
        else:
            log.warning("Dropping %s: no valid reference document", qid)
    bench = {"version": 1, "n": len(items), "labelling_protocol": __doc__.split("Labelling protocol")[1].split("Usage")[0].strip(),
             "dropped_candidates": dropped, "items": items}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bench, indent=2), encoding="utf-8")
    log.info("Benchmark: %d items (%d answerable); %d candidate labels dropped: %s",
             len(items), sum(i["answerable"] for i in items), len(dropped), dropped)
    return bench


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build()
