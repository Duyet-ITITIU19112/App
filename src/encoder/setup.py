from transformers import AutoTokenizer, AutoModel
import os

# Set your target local directory
save_dir = r"D:\Thesis\App\src\encoder\cross"

# Load and save the tokenizer and model locally
model_name = "cross-encoder/ms-marco-MiniLM-L6-v2"

# Download and cache to memory
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name)

# Save them to your directory
tokenizer.save_pretrained(save_dir)
model.save_pretrained(save_dir)

print(f"✅ Model and tokenizer saved to {save_dir}")
