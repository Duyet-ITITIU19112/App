# config.py

# ====== NLP Model and Resource Paths ======
BASE_ENCODER_DIR = r"D:\Thesis\App\src\encoder"

# NLTK Data (add to nltk.data.path if needed)
NLTK_DATA_PATH = rf"{BASE_ENCODER_DIR}\nltk"

# spaCy model path
SPACY_MODEL_PATH = rf"{BASE_ENCODER_DIR}\spacy\en_core_web_sm"

# Bi-encoder model (SentenceTransformer)
BIENCODER_MODEL_PATH = rf"{BASE_ENCODER_DIR}\sbert\all-MiniLM-L6-v2"

# Cross-encoder model (Transformers)
CROSS_ENCODER_MODEL_PATH = rf"{BASE_ENCODER_DIR}\cross"

# ====== Search Parameters ======
ELASTIC_INDEX = "user_files"
BM25_TOP_K = 500
EXPANSION_K = 3
SECOND_BM25_TOP_K = 200
EMBEDDING_TOP_K = 100
FINAL_RESULTS_K = 10
