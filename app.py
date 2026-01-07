from flask import Flask, render_template, request, redirect, session, g
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import timedelta, datetime

# 1️⃣ Crear app
app = Flask(__name__)

# 2️⃣ Configuración segura
app.secret_key = os.environ.get("SECRET_KEY", "iglesia_super_segura_2025")
app.permanent_session_lifetime = timedelta(minutes=20)

# ---------------- CONEXIÓN POSTGRES ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")

def conectar():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ---------------- CONTEXTO GLOBAL ----------------
@app.context_processor
def datos_usuario():
    return {
        "usuario_logueado": session.get("nombre"),
        "rol": session.get("usuario"),
        "ahora": datetime.now()
    }

# ---------------- SEGURIDAD ----------------
def requiere_login(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("logueado"):
            session["expirada"] = True
            return redirect("/login")
        return f(*args, **kwargs)
    return decorador

# ---------------- TABLAS ----------------
def crear_tablas():
    conn = conectar()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS visitas (
        id SERIAL PRIMARY KEY,
        fecha DATE NOT NULL,
        servicio TEXT,
        nombre TEXT,
        direccion TEXT,
        telefono TEXT,
        invitado_por TEXT,
        sexo TEXT,
        rango_edad TEXT,
        visita_casa TEXT,
        visitado TEXT DEFAULT 'No'
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS detalle_visita (
        id SERIAL PRIMARY KEY,
        visita_id INTEGER REFERENCES visitas(id) ON DELETE CASCADE,
        visitado_por TEXT,
        fecha_visita DATE,
        nota TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        usuario TEXT UNIQUE,
        password TEXT,
        nombre TEXT
    )
    """)

    usuarios_default = [
        ("pastor", "Salmo1263103", "Pastor"),
        ("secretaria", "Visitas126", "Secretaria"),
        ("asistente", "Iglesia126", "Asistente")
    ]

    for u, p, n in usuarios_default:
        c.execute("SELECT id FROM usuarios WHERE usuario=%s", (u,))
        if not c.fetchone():
            c.execute(
                "INSERT INTO usuarios (usuario, password, nombre) VALUES (%s,%s,%s)",
                (u, generate_password_hash(p), n)
            )

    conn.commit()
    conn.close()

crear_tablas()

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario_input = request.form["usuario"].strip().lower()
        clave = request.form["clave"]

        if usuario_input not in ["pastor", "secretaria", "asistente"]:
            return render_template("login.html", error="Usuario inválido")

        conn = conectar()
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE usuario=%s", (usuario_input,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], clave):
            session.permanent = True
            session["logueado"] = True
            session["usuario"] = user["usuario"]
            session["nombre"] = user["nombre"]
            session.pop("expirada", None)
            return redirect("/visitas")

        return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html")

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- REGISTRO PÚBLICO ----------
@app.route("/", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        conn = conectar()
        c = conn.cursor()

        c.execute("""
            INSERT INTO visitas
            (fecha, servicio, nombre, direccion, telefono,
             invitado_por, sexo, rango_edad, visita_casa)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            request.form["fecha"],
            request.form["servicio"],
            request.form["nombre"],
            request.form["direccion"],
            request.form["telefono"],
            request.form["invitado_por"],
            request.form["sexo"],
            request.form["rango_edad"],
            request.form["visita_casa"]
        ))

        conn.commit()
        conn.close()
        return redirect("/")

    return render_template("registro.html")

# ---------- VER VISITAS ----------
@app.route("/visitas")
@requiere_login
def visitas():
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    query = """
        SELECT 
            v.*,
            COUNT(d.id) AS total_visitas
        FROM visitas v
        LEFT JOIN detalle_visita d ON v.id = d.visita_id
        WHERE 1=1
    """
    params = []

    if desde:
        query += " AND v.fecha >= %s"
        params.append(desde)

    if hasta:
        query += " AND v.fecha <= %s"
        params.append(hasta)

    query += """
        GROUP BY v.id
        ORDER BY v.fecha DESC
    """

    conn = conectar()
    c = conn.cursor()
    c.execute(query, params)
    visitas = c.fetchall()

    # Estadísticas
    c.execute("SELECT COUNT(*) FROM visitas")
    total = c.fetchone()["count"]

    c.execute("SELECT COUNT(*) FROM visitas WHERE visitado='Si'")
    visitados = c.fetchone()["count"]

    c.execute("SELECT COUNT(*) FROM visitas WHERE visitado='No'")
    pendientes = c.fetchone()["count"]

    conn.close()

    return render_template(
        "visitas.html",
        visitas=visitas,
        desde=desde,
        hasta=hasta,
        total=total,
        visitados=visitados,
        pendientes=pendientes
    )


# ---------- PERFIL ----------
@app.route("/perfil/<int:id>")
@requiere_login
def perfil(id):
    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT * FROM visitas WHERE id=%s", (id,))
    p = c.fetchone()

    # Última visita
    c.execute("""
        SELECT fecha_visita, visitado_por
        FROM detalle_visita
        WHERE visita_id = %s
        ORDER BY fecha_visita DESC
        LIMIT 1
    """, (id,))
    ultima = c.fetchone()

    conn.close()

    return render_template("perfil.html", p=p, ultima=ultima)


# ---------- EDITAR ----------
@app.route("/editar/<int:id>", methods=["GET", "POST"])
@requiere_login
def editar(id):
    conn = conectar()
    c = conn.cursor()

    if request.method == "POST":
        c.execute("""
            UPDATE visitas SET
                fecha=%s, servicio=%s, nombre=%s, direccion=%s, telefono=%s,
                invitado_por=%s, sexo=%s, rango_edad=%s, visita_casa=%s
            WHERE id=%s
        """, (
            request.form["fecha"],
            request.form["servicio"],
            request.form["nombre"],
            request.form["direccion"],
            request.form["telefono"],
            request.form["invitado_por"],
            request.form["sexo"],
            request.form["rango_edad"],
            request.form["visita_casa"],
            id
        ))
        conn.commit()
        conn.close()
        return redirect("/visitas")

    c.execute("SELECT * FROM visitas WHERE id=%s", (id,))
    r = c.fetchone()
    conn.close()

    return render_template("editar.html", r=r)


# ---------- ELIMINAR ----------
@app.route("/eliminar/<int:id>")
@requiere_login
def eliminar(id):
    conn = conectar()
    c = conn.cursor()

    # Seguridad: borrar visitas hijas primero
    c.execute("DELETE FROM detalle_visita WHERE visita_id=%s", (id,))
    c.execute("DELETE FROM visitas WHERE id=%s", (id,))

    conn.commit()
    conn.close()
    return redirect("/visitas")


# ---------- VISITAR ----------
@app.route("/visitar/<int:id>", methods=["GET", "POST"])
@requiere_login
def visitar(id):
    conn = conectar()
    c = conn.cursor()

    if request.method == "POST":
        c.execute("""
            INSERT INTO detalle_visita
            (visita_id, visitado_por, fecha_visita, nota)
            VALUES (%s, %s, %s, %s)
        """, (
            id,
            request.form["visitado_por"],
            request.form["fecha_visita"],
            request.form.get("nota", "")
        ))

        # 🔥 Marcar como visitado si ya tiene al menos una visita
        c.execute("""
            UPDATE visitas
            SET visitado='Si'
            WHERE id=%s
        """, (id,))

        conn.commit()

    # Historial completo
    c.execute("""
        SELECT id, visitado_por, fecha_visita, nota
        FROM detalle_visita
        WHERE visita_id=%s
        ORDER BY fecha_visita DESC
    """, (id,))
    detalles = c.fetchall()

    conn.close()

    return render_template("detalle_visita.html", visitas=detalles, id=id)


# ---------- IMPRIMIR ----------
@app.route("/imprimir")
@requiere_login
def imprimir():
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    conn = conectar()
    c = conn.cursor()

    c.execute("""
        SELECT fecha, nombre, invitado_por, visitado
        FROM visitas
        WHERE fecha BETWEEN %s AND %s
        ORDER BY fecha
    """, (desde, hasta))

    visitas = c.fetchall()
    conn.close()

    return render_template("imprimir.html", visitas=visitas, desde=desde, hasta=hasta)

