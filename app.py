from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave_temporal")

# ---------------- CONEXIÓN POSTGRES ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")

def conectar():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ---------------- TABLAS ----------------
def crear_tablas():
    conn = conectar()
    c = conn.cursor()

    # Visitas
    c.execute("""
    CREATE TABLE IF NOT EXISTS visitas (
        id SERIAL PRIMARY KEY,
        fecha DATE,
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

    # Detalle visita
    c.execute("""
    CREATE TABLE IF NOT EXISTS detalle_visita (
        id SERIAL PRIMARY KEY,
        visita_id INTEGER UNIQUE REFERENCES visitas(id) ON DELETE CASCADE,
        visitado_por TEXT,
        fecha_visita DATE,
        nota TEXT
    )
    """)

    # Usuarios
    c.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        usuario TEXT UNIQUE,
        password TEXT,
        nombre TEXT
    )
    """)

    # Crear usuarios por defecto si no existen
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
        usuario = request.form["usuario"]
        clave = request.form["clave"]

        conn = conectar()
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE usuario=%s", (usuario,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], clave):
            session["logueado"] = True
            session["usuario"] = user["usuario"]
            session["nombre"] = user["nombre"]
            return redirect("/visitas")

        return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html")

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- REGISTRO (PÚBLICO) ----------
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

# ---------- PROTECCIÓN ----------
def protegido():
    return not session.get("logueado")

# ---------- VER VISITAS ----------
@app.route("/visitas")
def visitas():
    if protegido():
        return redirect("/login")

    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    query = "SELECT * FROM visitas WHERE 1=1"
    params = []

    if desde:
        query += " AND fecha >= %s"
        params.append(desde)

    if hasta:
        query += " AND fecha <= %s"
        params.append(hasta)

    query += " ORDER BY fecha DESC"

    conn = conectar()
    c = conn.cursor()
    c.execute(query, params)
    visitas = c.fetchall()
    conn.close()

    return render_template("visitas.html", visitas=visitas, desde=desde, hasta=hasta)

# ---------- PERFIL ----------
@app.route("/perfil/<int:id>")
def perfil(id):
    if protegido():
        return redirect("/login")

    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT * FROM visitas WHERE id=%s", (id,))
    p = c.fetchone()
    conn.close()

    return render_template("perfil.html", p=p)

# ---------- EDITAR ----------
@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    if protegido():
        return redirect("/login")

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
def eliminar(id):
    if protegido():
        return redirect("/login")

    conn = conectar()
    c = conn.cursor()
    c.execute("DELETE FROM visitas WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect("/visitas")

# ---------- VISITAR ----------
@app.route("/visitar/<int:id>", methods=["GET", "POST"])
def visitar(id):
    if protegido():
        return redirect("/login")

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT * FROM detalle_visita WHERE visita_id=%s", (id,))
    detalle = c.fetchone()

    if request.method == "POST" and detalle is None:
        c.execute("""
        INSERT INTO detalle_visita
        (visita_id, visitado_por, fecha_visita, nota)
        VALUES (%s,%s,%s,%s)
        """, (
            id,
            request.form["visitado_por"],
            request.form["fecha_visita"],
            request.form.get("nota", "")
        ))

        c.execute("UPDATE visitas SET visitado='Si' WHERE id=%s", (id,))
        conn.commit()

    conn.close()
    return render_template("detalle_visita.html", detalle=detalle, id=id)

# ---------- IMPRIMIR ----------
@app.route("/imprimir")
def imprimir():
    if protegido():
        return redirect("/login")

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
