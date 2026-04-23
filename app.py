import os
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, session, flash, jsonify, url_for
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "troque-esta-chave")

SPREADSHEET_ID = (os.getenv("SPREADSHEET_ID") or "").strip()
GOOGLE_CREDENTIALS_FILE = (os.getenv("GOOGLE_CREDENTIALS") or "service_account.json").strip()
LOGIN_USER = (os.getenv("LOGIN_USER") or "admin").strip()
LOGIN_PASS = (os.getenv("LOGIN_PASS") or "123456").strip()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

MOTIVOS_SOLICITACAO = [
    "Férias",
    "Afastamento",
    "Licença",
    "Falta",
    "Cobertura",
    "Novo posto",
    "Reforço operacional",
    "Outro",
]


def conectar_sheets():
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("logado"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def ler_intervalo(range_name: str):
    service = conectar_sheets()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()

    return result.get("values", [])


def gravar_linha(range_name: str, values: list[list[str]]):
    service = conectar_sheets()
    sheet = service.spreadsheets()

    body = {"values": values}

    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()


def carregar_base_postos():
    values = ler_intervalo("BASE_POSTOS!A:D")

    if len(values) <= 1:
        return []

    registros = []
    for row in values[1:]:
        supervisor = row[0].strip() if len(row) > 0 else ""
        unidade = row[1].strip() if len(row) > 1 else ""
        posto = row[2].strip() if len(row) > 2 else ""
        nr_postos = row[3].strip() if len(row) > 3 else ""

        if supervisor and unidade and posto:
            registros.append({
                "Supervisor": supervisor,
                "Unidade": unidade,
                "Posto": posto,
                "NrPostos": nr_postos,
            })

    return registros


def listar_supervisores():
    base = carregar_base_postos()
    return sorted({item["Supervisor"] for item in base})


def listar_unidades_por_supervisor(supervisor: str):
    base = carregar_base_postos()
    return sorted({
        item["Unidade"]
        for item in base
        if item["Supervisor"] == supervisor
    })


def listar_postos_por_supervisor_unidade(supervisor: str, unidade: str):
    base = carregar_base_postos()
    return sorted({
        item["Posto"]
        for item in base
        if item["Supervisor"] == supervisor and item["Unidade"] == unidade
    })


def buscar_nr_postos(supervisor: str, unidade: str, posto: str):
    base = carregar_base_postos()
    for item in base:
        if (
            item["Supervisor"] == supervisor
            and item["Unidade"] == unidade
            and item["Posto"] == posto
        ):
            return item["NrPostos"]
    return ""


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("usuario") or request.form.get("user")
        senha = request.form.get("senha") or request.form.get("password")

        user = (user or "").strip()
        senha = (senha or "").strip()

        if user == LOGIN_USER and senha == LOGIN_PASS:
            session["logado"] = True
            return redirect(url_for("vagas"))

        flash("Usuário ou senha inválidos.", "erro")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/unidades")
@login_required
def api_unidades():
    supervisor = (request.args.get("supervisor") or "").strip()
    if not supervisor:
        return jsonify([])
    return jsonify(listar_unidades_por_supervisor(supervisor))


@app.route("/api/postos")
@login_required
def api_postos():
    supervisor = (request.args.get("supervisor") or "").strip()
    unidade = (request.args.get("unidade") or "").strip()

    if not supervisor or not unidade:
        return jsonify([])

    return jsonify(listar_postos_por_supervisor_unidade(supervisor, unidade))


@app.route("/api/nr-postos")
@login_required
def api_nr_postos():
    supervisor = (request.args.get("supervisor") or "").strip()
    unidade = (request.args.get("unidade") or "").strip()
    posto = (request.args.get("posto") or "").strip()

    if not supervisor or not unidade or not posto:
        return jsonify({"nr_postos": ""})

    return jsonify({
        "nr_postos": buscar_nr_postos(supervisor, unidade, posto)
    })


@app.route("/vagas", methods=["GET", "POST"])
@login_required
def vagas():
    supervisores = listar_supervisores()

    if request.method == "POST":
        supervisor = (request.form.get("supervisor") or "").strip()
        unidade = (request.form.get("unidade") or "").strip()
        posto = (request.form.get("posto") or "").strip()
        nr_postos = (request.form.get("nr_postos") or "").strip()
        motivo = (request.form.get("motivo") or "").strip()
        observacao = (request.form.get("observacao") or "").strip()

        if not supervisor or not unidade or not posto or not motivo:
            flash("Preencha todos os campos obrigatórios.", "erro")
            return redirect(url_for("vagas"))

        if not nr_postos:
            nr_postos = buscar_nr_postos(supervisor, unidade, posto)

        try:
            gravar_linha("VAGAS!A:G", [[
                datetime.now().strftime("%d/%m/%Y %H:%M"),
                supervisor,
                unidade,
                posto,
                nr_postos,
                motivo,
                observacao
            ]])
            flash("Vaga registrada com sucesso.", "sucesso")
        except Exception as exc:
            flash(f"Erro ao salvar vaga: {str(exc)}", "erro")

        return redirect(url_for("vagas"))

    vagas_salvas = ler_intervalo("VAGAS!A:G")

    return render_template(
        "vagas.html",
        supervisores=supervisores,
        motivos=MOTIVOS_SOLICITACAO,
        vagas=vagas_salvas
    )


@app.route("/debug-login")
def debug_login():
    return {
        "LOGIN_USER": LOGIN_USER,
        "LOGIN_PASS": LOGIN_PASS
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
