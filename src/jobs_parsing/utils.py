from __future__ import annotations
 
import re
import unicodedata
 
# Невидимые символы, которые могут прятаться в тексте и ломать сравнение строк.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u200e\u200f\u00ad"), None)
 
 
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_INVISIBLE)
    return re.sub(r"\s+", " ", text).strip()
 
 
def casefold_key(text: str) -> str:
    return normalize(text).casefold()