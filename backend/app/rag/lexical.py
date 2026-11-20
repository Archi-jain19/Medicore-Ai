"""BM25 keyword search over the same chunks that FAISS indexes (the lexical half of hybrid retrieval).

Dense embeddings capture meaning ("tummy ache" ~ "abdominal pain"); BM25 captures exact terms (drug and test names,
"HbA1c", "25-hydroxyvitamin D") that embeddings can blur. Combining them is more robust than either alone.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import numpy as np

STOPWORDS = frozenset("""
a about above after again all also am an and any are as at be because been before being below between both but by can
could did do does doing down during each few for from further had has have having he her here hers him his how i if in
into is it its itself just me more most my no nor not now of off on once only or other our out over own same she should
so some such than that the their them then there these they this those through to too under until up very was we were
what when where which while who whom why will with would you your yours get got feel feeling feels please tell
really easily always keep keeps kept often sometimes lot lots bit quite pretty literally actually also like going
""".split())

_TOKEN = re.compile(r"[a-z0-9]+")


def stem(w: str) -> str:
    """Very light suffix stripping so 'headaches'/'headache', 'coughing'/'cough', 'causes'/'cause' meet."""
    if len(w) <= 3:
        return w
    for suf, rep in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3 and not (suf == "s" and w.endswith("ss")):
            w = w[: -len(suf)] + rep
            break
    # a final silent "e" is dropped so singular and plural meet: headache/headaches, bruise/bruises, patch/patches
    return w[:-1] if len(w) > 4 and w.endswith("e") else w


def tokenize(text: str, keep_stop: bool = False) -> list[str]:
    return [stem(t) for t in _TOKEN.findall(text.lower()) if keep_stop or t not in STOPWORDS]


def content_words(text: str) -> list[str]:
    """Unstemmed, non-stopword tokens (used for term coverage and typo repair)."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


class BM25Index:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.doc_len = np.zeros(self.n, dtype=np.float32)
        for i, d in enumerate(docs):
            toks = tokenize(d)
            self.doc_len[i] = len(toks)
            for term, tf in Counter(toks).items():
                self.postings[term].append((i, tf))
        self.avg_len = float(self.doc_len.mean()) if self.n else 0.0
        self.idf = {t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def scores(self, query: str) -> np.ndarray:
        s = np.zeros(self.n, dtype=np.float32)
        for term in set(tokenize(query)):
            post = self.postings.get(term)
            if not post:
                continue
            idf = self.idf[term]
            for i, tf in post:
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avg_len or 1))
                s[i] += idf * tf * (self.k1 + 1) / denom
        return s

    def search(self, query: str, n: int = 30) -> list[tuple[int, float]]:
        s = self.scores(query)
        if not s.any():
            return []
        top = np.argpartition(-s, min(n, self.n - 1))[:n]
        return [(int(i), float(s[i])) for i in top[np.argsort(-s[top])] if s[i] > 0]
