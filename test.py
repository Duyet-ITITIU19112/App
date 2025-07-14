from flask import Flask
app = Flask(__name__)

@app.route("/")
def hello():
    print("▶ hello.py: got /")
    return "👋 Hello!"

if __name__ == "__main__":
    print("▶ hello.py starting")
    app.run(port=5001, use_reloader=False)
