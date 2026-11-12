"""Answer bank: saved answers to custom application questions, looked up by
question similarity.

The embedder is a deterministic feature-hashing model, so lookups need no
network call and no extra dependency. It sits behind `Embedder`; swapping in a
real embedding model (or sqlite-vec) changes this file only."""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from . import repo

DIM = 512
_STOP = set("""a an and are as at be been by can could did do does for from had has have
how i if in is it its me my of on or our please so that the their them there these this
those to us was we were what when where which who will with would you your yours
tell describe explain share briefly about role position company team job here
""".split())
def _stem(word: str) -> str:
    """Tiny suffix stripper: enough to fold plurals and verb endings."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    for suffix in ("ation", "ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def canonical(question: str, company: str = "") -> str:
    """Lowercase, drop the employer's name and boilerplate, so 'Why Stripe?'
    and 'Why Acme?' land on the same entry."""
    q = (question or "").lower()
    for word in re.findall(r"[a-z0-9]+", (company or "").lower()):
        if len(word) > 2:
            q = re.sub(rf"\b{re.escape(word)}\b", " ", q)
    q = re.sub(r"\(optional\)|\*|\brequired\b", " ", q)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", q)).strip()


def tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())
            if w not in _STOP and len(w) > 1]


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Unigrams and bigrams of stemmed content words, hashed into DIM buckets
    with a sign bit, then L2 normalized."""

    def embed(self, text: str) -> list[float]:
        toks = tokens(text)
        feats = [(t, 1.0) for t in toks]
        feats += [(f"{a}_{b}", 0.6) for a, b in zip(toks, toks[1:])]
        vec = [0.0] * DIM
        for feat, weight in feats:
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            vec[h % DIM] += weight if (h >> 40) & 1 else -weight
        norm = math.sqrt(sum(v * v for v in vec))
        return [round(v / norm, 6) for v in vec] if norm else vec


embedder: Embedder = HashingEmbedder()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def lookup(bank: list[dict], question: str, company: str = "") -> tuple[dict | None, float]:
    """Best bank entry for a question and its similarity (0..1)."""
    q = canonical(question, company)
    if not q:
        return None, 0.0
    vec = embedder.embed(q)
    best, best_sim = None, 0.0
    for entry in bank:
        sim = 1.0 if canonical(entry["question"]) == q else cosine(vec, entry["embedding"])
        if sim > best_sim:
            best, best_sim = entry, sim
    return best, best_sim


def save(conn, question: str, answer: str, company: str = "") -> int:
    """Insert, or update the entry that already holds this question."""
    q = canonical(question, company)
    answer = (answer or "").strip()
    if not q or not answer:
        return 0
    entry, sim = lookup(repo.list_bank(conn), question, company)
    if entry and sim >= 0.93:
        repo.update_bank(conn, entry["id"], answer=answer)
        return entry["id"]
    display = re.sub(r"\s+", " ", question).strip()
    return repo.add_bank(conn, display, answer, embedder.embed(q))


def reembed(conn) -> None:
    for entry in repo.list_bank(conn):
        repo.update_bank(conn, entry["id"],
                         embedding=embedder.embed(canonical(entry["question"])))
