import torch

print("PyTorch version:", torch.__version__)
print("Built with CUDA:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
print("CUDA device count:", torch.cuda.device_count())
if torch.cuda.is_available():
    idx = torch.cuda.current_device()
    print("Current CUDA device:", idx, torch.cuda.get_device_name(idx))
