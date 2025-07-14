# src/services/text_preprocessing.py

import os
import re
import spacy
from nltk.stem import PorterStemmer

# Set spaCy model path (custom or env)
DEFAULT_SPACY_PATH = r"D:\Thesis\App\src\encoder\spacy\en_core_web_sm\en_core_web_sm-3.7.1"
SPACY_MODEL_PATH = os.getenv("SPACY_MODEL_PATH", DEFAULT_SPACY_PATH)

# Load spaCy
try:
    nlp = spacy.load(SPACY_MODEL_PATH)
    nlp.max_length = 2_000_000  # ⬅️ Increase the limit to handle large documents
except OSError as e:
    raise RuntimeError(f"❌ Failed to load spaCy model from {SPACY_MODEL_PATH}\n{e}")

stemmer = PorterStemmer()

# --- Utility ---

def normalize(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s\-]', ' ', text)  # remove punctuation but keep hyphens
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def split_compounds(text):
    # Handle camelCase and hyphenated words
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    text = text.replace('-', ' ')
    return text

# --- Core tokenizer wrapper ---

def tokenize_doc(text, remove_stopwords=True, lemmatize=True, stem=False):
    doc = nlp(text)
    tokens = []
    for token in doc:
        if token.is_alpha and (not remove_stopwords or not token.is_stop):
            word = token.lemma_ if lemmatize else token.text
            if stem:
                word = stemmer.stem(word)
            tokens.append(word)
    return tokens

# --- Preprocessing Pipelines ---

def preprocess_bm25_query(text):
    text = normalize(text)
    tokens = tokenize_doc(text, remove_stopwords=True, lemmatize=False, stem=True)
    return ' '.join(tokens)


def preprocess_bm25_document(text):
    text = normalize(text)
    tokens = tokenize_doc(text, remove_stopwords=True, lemmatize=False, stem=True)
    return ' '.join(tokens)


def preprocess_for_encoder(text):
    text = normalize(text)  # No compound split
    tokens = tokenize_doc(text, remove_stopwords=False, lemmatize=True, stem=False)
    return ' '.join(tokens)
