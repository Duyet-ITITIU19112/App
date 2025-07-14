from dotenv import load_dotenv
import os
import tempfile

load_dotenv()



print(tempfile.gettempdir())  # ✅ Now should print D:/Temp
