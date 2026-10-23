import os
import time
from datetime import date, timedelta
from functools import wraps

from flask import (
    Flask, g, redirect, render_template, request, session, url_for
)
from supabase import create_client

try:
    from dotenv import load_dotenv  # só para testar no computador (.env)
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.permanent_session_lifetime = timedelta(days=30)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),  # True no Render (https)
)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]  # só a chave anon, nunca a service_role

TIPOS = ("Ganho", "Gasto", "Combustível")

# ---------- Perfis (nome e foto) ----------
# TROQUE pelos e-mails que vocês usam para entrar (em letras minúsculas).
# As fotos ficam na pasta static/ (ex.: static/igor.jpg).

PERFIS = {
    "i.goncalvesdev@gmail.com":  {"nome": "Igor",  "foto": None},
    "drabrunahertzog@gmail.com":   {"nome": "Bruna", "foto": None},
}

# ---------- Categorias (ícone, cor e tipo padrão) ----------
CATEGORIAS = {
    "Salário":      {"icone": "⬇️", "cor": "#16a34a", "tipo": "Ganho"},
    "Rendimento":   {"icone": "⬆️", "cor": "#16a34a", "tipo": "Ganho"},
    "Supermercado": {"icone": "🛒", "cor": "#e91e63", "tipo": "Gasto"},
    "Restaurante":  {"icone": "🍴", "cor": "#ef4444", "tipo": "Gasto"},
    "Academia":     {"icone": "🏋️", "cor": "#7c3aed", "tipo": "Gasto"},
    "Combustível":  {"icone": "⛽", "cor": "#8e24aa", "tipo": "Combustível"},
    "Lazer":        {"icone": "💜", "cor": "#a855f7", "tipo": "Gasto"},
    "Outros":       {"icone": "📦", "cor": "#64748b", "tipo": "Gasto"},
}


def perfil_atual():
    email = (session.get("email") or "").lower()
    if email in PERFIS:
        return PERFIS[email]
    nome = email.split("@")[0].capitalize() if email else "Usuário"
    return {"nome": nome, "foto": None}


# ---------- Login e sessão ----------

def guardar_sessao(res):
    s = res.session
    session.permanent = True
    session["access_token"] = s.access_token
    session["refresh_token"] = s.refresh_token
    session["expires_at"] = s.expires_at
    session["user_id"] = res.user.id
    session["email"] = res.user.email


def cliente_do_usuario():
    """Cliente do Supabase que age com a identidade de quem está logado (RLS)."""
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if time.time() > session.get("expires_at", 0) - 60:
        guardar_sessao(c.auth.refresh_session(session["refresh_token"]))
    c.postgrest.auth(session["access_token"])
    return c


def login_obrigatorio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "access_token" not in session:
            return redirect(url_for("login"))
        try:
            g.db = cliente_do_usuario()
        except Exception:
            session.clear()
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        senha = request.form.get("senha", "")
        try:
            c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            res = c.auth.sign_in_with_password({"email": email, "password": senha})
            guardar_sessao(res)
            return redirect(url_for("index"))
        except Exception as e:
            print("ERRO LOGIN:", e)
            erro = "E-mail ou senha incorretos."
    return render_template("login.html", erro=erro)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- App ----------

@app.route("/", methods=["GET", "POST"])
@login_obrigatorio
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

            if not descricao:
                raise ValueError("Preencha a descrição.")

            if tipo not in TIPOS:
                raise ValueError("Selecione um tipo válido.")

            if categoria not in CATEGORIAS:
                categoria = "Outros"

            if valor <= 0:
                raise ValueError("O valor precisa ser maior que zero.")

            g.db.table("lancamentos").insert({
                "user_id": session["user_id"],
                "data": data_obj.isoformat(),
                "descricao": descricao,
                "tipo": tipo,
                "categoria": categoria,
                "valor": valor,
            }).execute()

            return redirect(url_for("index"))

        except (ValueError, TypeError):
            erro = "Confira a data, o tipo e o valor. Use um valor maior que zero."
        except Exception:
            erro = "Não foi possível salvar agora. Tente novamente."

    # Sem período fixo: traz todos os lançamentos (a RLS já filtra só os de quem está logado).
    # Os totais, filtros de ano/mês e gráficos são calculados na página.
    lancamentos = (
        g.db.table("lancamentos")
        .select("*")
        .order("data", desc=True)
        .order("id", desc=True)
        .execute()
        .data
    )

    return render_template(
        "index.html",
        lancamentos=lancamentos,
        categorias=CATEGORIAS,
        perfil=perfil_atual(),
        hoje=date.today().isoformat(),
        erro=erro,
    )


@app.route("/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir(id):
    g.db.table("lancamentos").delete().eq("id", id).execute()
    return redirect(url_for("index"))


@app.route("/limpar-tudo", methods=["POST"])
@login_obrigatorio
def limpar_tudo():
    if request.form.get("confirmacao") == "SIM":
        # apaga só os lançamentos de quem está logado
        g.db.table("lancamentos").delete().eq("user_id", session["user_id"]).execute()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
