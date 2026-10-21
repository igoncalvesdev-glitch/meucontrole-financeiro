
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from pathlib import Path
from datetime import date

app = Flask(__name__)

DB_PATH = Path(__file__).resolve().parent / "financeiro.db"

DATA_INICIAL = "2026-10-20"
DATA_FINAL = "2026-12-31"


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def criar_tabela():
    with conectar() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lancamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                descricao TEXT NOT NULL,
                tipo TEXT NOT NULL,
                categoria TEXT,
                valor REAL NOT NULL
            )
        """)


@app.route("/", methods=["GET", "POST"])
def index():
    erro = None

    if request.method == "POST":
        data_lancamento = request.form.get("data", "")
        descricao = request.form.get("descricao", "").strip()
        tipo = request.form.get("tipo", "")
        categoria = request.form.get("categoria", "").strip()
        valor_texto = request.form.get("valor", "").strip()

        try:
            data_obj = date.fromisoformat(data_lancamento)
            valor = float(valor_texto.replace(",", "."))

            if not DATA_INICIAL <= data_lancamento <= DATA_FINAL:
                raise ValueError("A data deve estar entre 20/10/2026 e 31/12/2026.")

            if not descricao:
                raise ValueError("Preencha a descrição.")

            if tipo not in ("Ganho", "Gasto", "Combustível"):
                raise ValueError("Selecione um tipo válido.")

            if valor <= 0:
                raise ValueError("O valor precisa ser maior que zero.")

            with conectar() as conn:
                conn.execute("""
                    INSERT INTO lancamentos
                    (data, descricao, tipo, categoria, valor)
                    VALUES (?, ?, ?, ?, ?)
                """, (data_obj.isoformat(), descricao, tipo, categoria, valor))

            return redirect(url_for("index"))

        except (ValueError, TypeError):
            erro = "Confira a data, o tipo e o valor. Use um valor maior que zero."

    with conectar() as conn:
        lancamentos = conn.execute("""
            SELECT * FROM lancamentos
            WHERE data >= ? AND data <= ?
            ORDER BY data DESC, id DESC
        """, (DATA_INICIAL, DATA_FINAL)).fetchall()

    ganhos = sum(
        item["valor"] for item in lancamentos
        if item["tipo"] == "Ganho"
    )
    gastos = sum(
        item["valor"] for item in lancamentos
        if item["tipo"] == "Gasto"
    )
    combustivel = sum(
        item["valor"] for item in lancamentos
        if item["tipo"] == "Combustível"
    )
    total_gastos = gastos + combustivel
    saldo = ganhos - total_gastos

    return render_template(
        "index.html",
        lancamentos=lancamentos,
        ganhos=ganhos,
        gastos=gastos,
        combustivel=combustivel,
        total_gastos=total_gastos,
        saldo=saldo,
        erro=erro,
        data_inicial=DATA_INICIAL,
        data_final=DATA_FINAL
    )


@app.route("/excluir/<int:id>", methods=["POST"])
def excluir(id):
    with conectar() as conn:
        conn.execute("DELETE FROM lancamentos WHERE id = ?", (id,))
    return redirect(url_for("index"))


@app.route("/limpar-tudo", methods=["POST"])
def limpar_tudo():
    confirmacao = request.form.get("confirmacao")

    if confirmacao == "SIM":
        with conectar() as conn:
            conn.execute("DELETE FROM lancamentos")

    return redirect(url_for("index"))


criar_tabela()

if __name__ == "__main__":
    app.run(debug=True)
