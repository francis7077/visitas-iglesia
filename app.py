from flask import Flask, render_template, request, redirect, session, url_for, flash
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
app.permanent_session_lifetime = timedelta(minutes=60) # Aumentado para mejor flujo en móvil

# ---------------- CONEXIÓN POSTGRES ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")

def conectar():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ---------------- FILTRO DE FECHA SEGURO ----------------
@app.template_filter('formato_fecha')
def formato_fecha(value):
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except:
            return value
    return value.strftime('%d/%m/%Y')

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
            return redirect(url_for("login"))
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
    );
    CREATE TABLE IF NOT EXISTS detalle_visita (
        id SERIAL PRIMARY KEY,
        visita_id INTEGER REFERENCES visitas(id) ON DELETE CASCADE,
        visitado_por TEXT,
        fecha_visita DATE,
        nota TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        usuario TEXT UNIQUE,
        password TEXT,
        nombre TEXT
    );
    """)
    # Usuarios por defecto si no existen
    usuarios_default = [
        ("pastor", "Salmo1263103", "Pastor"),
        ("secretaria", "Visitas126", "Secretaria"),
        ("asistente", "Iglesia126", "Asistente")
    ]
    for u, p, n in usuarios_default:
        c.execute("SELECT id FROM usuarios WHERE usuario=%s", (u,))
        if not c.fetchone():
            c.execute("INSERT INTO usuarios (usuario, password, nombre) VALUES (%s,%s,%s)",
                      (u, generate_password_hash(p), n))
    conn.commit()
    conn.close()

crear_tablas()

# ---------- LOGIN / LOGOUT ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario_input = request.form["usuario"].strip().lower()
        clave = request.form["clave"]
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
            return redirect(url_for("visitas"))
        return render_template("login.html", error="Credenciales incorrectas")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------- REGISTRO PÚBLICO ----------
@app.route("/", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        conn = conectar()
        c = conn.cursor()
        c.execute("""
            INSERT INTO visitas (fecha, servicio, nombre, direccion, telefono, invitado_por, sexo, rango_edad, visita_casa)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (request.form["fecha"], request.form["servicio"], request.form["nombre"], request.form["direccion"],
              request.form["telefono"], request.form["invitado_por"], request.form["sexo"], 
              request.form["rango_edad"], request.form["visita_casa"]))
        conn.commit()
        conn.close()
        return redirect(url_for("registro"))
    return render_template("registro.html")

# ---------- PANEL PRINCIPAL ----------
@app.route("/visitas")
@requiere_login
def visitas():
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    query = """
        SELECT v.*, COUNT(d.id) AS total_visitas 
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

    query += " GROUP BY v.id ORDER BY v.fecha DESC"

    conn = conectar()
    c = conn.cursor()
    c.execute(query, params)
    visitas_lista = c.fetchall()

    # 🔥 LÓGICA REAL: el estado depende del historial
    for r in visitas_lista:
        if r["total_visitas"] > 0:
            r["visitado"] = "Si"
        else:
            r["visitado"] = "No"

    total = len(visitas_lista)
    visitados = sum(1 for r in visitas_lista if r["visitado"] == "Si")
    pendientes = total - visitados

    conn.close()

    return render_template(
        "visitas.html",
        visitas=visitas_lista,
        desde=desde,
        hasta=hasta,
        total=total,
        visitados=visitados,
        pendientes=pendientes
    )


# ---------- GESTIÓN DE PERSONA (VISITANTE) ----------
@app.route("/perfil/<int:id>")
@requiere_login
def perfil(id):
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT * FROM visitas WHERE id=%s", (id,))
    p = c.fetchone()
    c.execute("SELECT * FROM detalle_visita WHERE visita_id=%s ORDER BY fecha_visita DESC LIMIT 1", (id,))
    ultima = c.fetchone()
    conn.close()
    return render_template("perfil.html", p=p, ultima=ultima)

@app.route("/editar/<int:id>", methods=["GET", "POST"])
@requiere_login
def editar(id):
    conn = conectar()
    c = conn.cursor()
    if request.method == "POST":
        c.execute("""
            UPDATE visitas SET fecha=%s, servicio=%s, nombre=%s, direccion=%s, telefono=%s,
            invitado_por=%s, sexo=%s, rango_edad=%s, visita_casa=%s WHERE id=%s
        """, (request.form["fecha"], request.form["servicio"], request.form["nombre"], request.form["direccion"],
              request.form["telefono"], request.form["invitado_por"], request.form["sexo"], 
              request.form["rango_edad"], request.form["visita_casa"], id))
        conn.commit()
        conn.close()
        return redirect(url_for("visitas"))
    c.execute("SELECT * FROM visitas WHERE id=%s", (id,))
    r = c.fetchone()
    conn.close()
    return render_template("editar.html", r=r)

@app.route("/eliminar/<int:id>")
@requiere_login
def eliminar(id):
    conn = conectar()
    c = conn.cursor()
    c.execute("DELETE FROM visitas WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("visitas"))

# ---------- VALOR AGREGADO: GESTIÓN DE SEGUIMIENTOS (MULTIVISITAS) ----------

@app.route("/visitar/<int:id>", methods=["GET", "POST"])
@requiere_login
def visitar(id):
    conn = conectar()
    c = conn.cursor()
    if request.method == "POST":
        visitado_por = request.form.get("visitado_por")
        fecha_visita = request.form.get("fecha_visita")
        nota = request.form.get("nota", "")
        if visitado_por and fecha_visita:
            c.execute("INSERT INTO detalle_visita (visita_id, visitado_por, fecha_visita, nota) VALUES (%s, %s, %s, %s)",
                      (id, visitado_por, fecha_visita, nota))
            c.execute("UPDATE visitas SET visitado='Si' WHERE id=%s", (id,))
            conn.commit()
            conn.close()
            return redirect(url_for("visitar", id=id)) # Redirección para permitir más visitas

    c.execute("SELECT * FROM detalle_visita WHERE visita_id=%s ORDER BY fecha_visita DESC", (id,))
    detalles = c.fetchall()
    c.execute("SELECT nombre FROM visitas WHERE id=%s", (id,))
    persona = c.fetchone()
    conn.close()
    return render_template("detalle_visita.html", visitas=detalles, id=id, persona=persona, total_visitas=len(detalles))

# SOLUCIÓN AL ERROR 404: Ruta para editar una visita específica del historial
@app.route("/editar_visita/<int:id>", methods=["GET", "POST"])
@requiere_login
def editar_visita(id):
    conn = conectar()
    c = conn.cursor()
    if request.method == "POST":
        c.execute("""
            UPDATE detalle_visita SET visitado_por=%s, fecha_visita=%s, nota=%s WHERE id=%s RETURNING visita_id
        """, (request.form["visitado_por"], request.form["fecha_visita"], request.form["nota"], id))
        visita_id = c.fetchone()['visita_id']
        conn.commit()
        conn.close()
        return redirect(url_for("visitar", id=visita_id))
    
    c.execute("SELECT * FROM detalle_visita WHERE id=%s", (id,))
    v = c.fetchone()
    conn.close()
    return render_template("editar_seguimiento.html", v=v)

# SOLUCIÓN AL ERROR 404: Ruta para eliminar una visita específica del historial
@app.route("/eliminar_visita/<int:id>")
@requiere_login
def eliminar_visita(id):
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT visita_id FROM detalle_visita WHERE id=%s", (id,))
    res = c.fetchone()
    if res:
        v_id = res['visita_id']
        c.execute("DELETE FROM detalle_visita WHERE id=%s", (id,))
        conn.commit()
        conn.close()
        return redirect(url_for("visitar", id=v_id))
    conn.close()
    return redirect(url_for("visitas"))

@app.route("/imprimir")
@requiere_login
def imprimir():
    desde, hasta = request.args.get("desde"), request.args.get("hasta")
    conn = conectar(); c = conn.cursor()
    c.execute("SELECT * FROM visitas WHERE fecha BETWEEN %s AND %s ORDER BY fecha", (desde, hasta))
    visitas_reporte = c.fetchall()
    conn.close()
    return render_template("imprimir.html", visitas=visitas_reporte, desde=desde, hasta=hasta)

if __name__ == "__main__":
    app.run(debug=True)