import os
from flask import Flask, render_template, request, redirect, session, flash
from dotenv import load_dotenv

from google.oauth2 import service_account
from googleapiclient.discovery import build

# =========================
# CONFIGURAÇÕES INICIAIS
# =========================

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS")

LOGIN_USER = os.getenv("LOGIN_USER")
LOGIN_PASS = os.getenv("LOGIN_PASS")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# =========================
# CONEXÃO COM GOOGLE SHEETS
# =========================

def conectar_sheets():
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    return service


# =========================
# BUSCAR BASE DE POSTOS
# =========================

def buscar_base_postos():
    service = conectar_sheets()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="BASE_POSTOS!A2:D"
    ).execute()

    values = result.get("values", [])

    dados = []
    for row in values:
        if len(row) < 4:
            continue

        dados.append({
            "Supervisor": row[0],
            "Unidade": row[1],
            "Posto": row[2],
            "NrPostos": row[3]
        })

    return dados


# =========================
# LOGIN
# =========================

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("usuario")
        senha = request.form.get("senha")

        if user == LOGIN_USER and senha == LOGIN_PASS:
            session["logado"] = True
            return redirect("/vagas")
        else:
            flash("Usuário ou senha inválidos")

    return render_template("login.html")


# =========================
# TELA DE VAGAS
# =========================

@app.route("/vagas", methods=["GET", "POST"])
def vagas():
    if not session.get("logado"):
        return redirect("/login")

    base = buscar_base_postos()

    supervisores = sorted(list(set([x["Supervisor"] for x in base])))
    unidades = sorted(list(set([x["Unidade"] for x in base])))
    postos = sorted(list(set([x["Posto"] for x in base])))

    if request.method == "POST":
        supervisor = request.form.get("supervisor")
        unidade = request.form.get("unidade")
        posto = request.form.get("posto")
        motivo = request.form.get("motivo")
        obs = request.form.get("observacao")

        nr_postos = ""
        for x in base:
            if x["Supervisor"] == supervisor and x["Unidade"] == unidade and x["Posto"] == posto:
                nr_postos = x["NrPostos"]
                break

        try:
            service = conectar_sheets()
            sheet = service.spreadsheets()

            values = [[
                "",  # data (opcional)
                supervisor,
                unidade,
                posto,
                nr_postos,
                motivo,
                obs
            ]]

            body = {"values": values}

            sheet.values().append(
                spreadsheetId=SPREADSHEET_ID,
                range="VAGAS!A1",
                valueInputOption="USER_ENTERED",
                body=body
            ).execute()

            flash("Vaga registrada com sucesso!")

        except Exception as e:
            flash(f"Erro ao salvar: {str(e)}")

        return redirect("/vagas")

    return render_template(
        "vagas.html",
        supervisores=supervisores,
        unidades=unidades,
        postos=postos
    )


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================
# RODAR APP (RENDER)
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
