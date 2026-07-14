from flask import Flask, render_template
import os

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"))

@app.route("/")
def homepage():
    return render_template("index.html")

@app.route("/newvideo")
def videonovo():
    return render_template("newvideo.html")

@app.route("/estatisticas")
def estatisticas():
    return render_template("estatisticas.html")

if __name__ == '__main__':
    app.run(debug=True)