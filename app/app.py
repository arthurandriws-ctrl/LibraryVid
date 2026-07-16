from flask import Flask, render_template
import os
from db import db 
import models

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"))
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://root:@localhost:3307/libraryvid"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    db.create_all()
    
@app.route("/")
def homepage():
    return render_template("index.html")

#trbalhar no formulário de newvideo, e usar dados_video como variável para ia.py
@app.route("/newvideo")
def videonovo():
    return render_template("newvideo.html")


@app.route("/estatisticas")
def estatisticas():
    return render_template("estatistica.html")

if __name__ == '__main__':
    app.run(debug=True)