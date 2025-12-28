from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "clave_super_secreta_cambia_esto"

# ---------------- USUARIO / CLAVE ----------------
USUARIO_ADMIN = "admin"
CLAVE_ADMIN = "1234"

# ---------------- CONEXIÓN ----------------
def conectar():
    conn = sqlite3.connect("asistencia.db")
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- TABLAS ----------------
def crear_tablas():
    conn = conectar()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS visitas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visita_id INTEGER UNIQUE,
        visitado_por TEXT,
        fecha_visita TEXT,
        nota TEXT
    )
    """)

    conn.commit()
    conn.close()

crear_tablas()

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        clave = request.form["clave"]

        if usuario == USUARIO_ADMIN and clave == CLAVE_ADMIN:
            session["logueado"] = True
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
        conn.execute("""
        INSERT INTO visitas
        (fecha, servicio, nombre, direccion, telefono,
         invitado_por, sexo, rango_edad, visita_casa)
        VALUES (?,?,?,?,?,?,?,?,?)
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


# ---------- VER VISITAS (PROTEGIDO) ----------
@app.route("/visitas")
def visitas():
    if not session.get("logueado"):
        return redirect("/login")

    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    query = "SELECT * FROM visitas WHERE 1=1"
    params = []

    if desde:
        query += " AND fecha >= ?"
        params.append(desde)

    if hasta:
        query += " AND fecha <= ?"
        params.append(hasta)

    query += " ORDER BY fecha DESC"

    conn = conectar()
    visitas = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        "visitas.html",
        visitas=visitas,
        desde=desde,
        hasta=hasta
    )


# ---------- PERFIL (PROTEGIDO) ----------
@app.route("/perfil/<int:id>")
def perfil(id):
    if not session.get("logueado"):
        return redirect("/login")

    conn = conectar()
    p = conn.execute(
        "SELECT * FROM visitas WHERE id=?",
        (id,)
    ).fetchone()
    conn.close()

    return render_template("perfil.html", p=p)


# ---------- EDITAR (PROTEGIDO) ----------
@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    if not session.get("logueado"):
        return redirect("/login")

    conn = conectar()

    if request.method == "POST":
        conn.execute("""
        UPDATE visitas SET
            fecha=?, servicio=?, nombre=?, direccion=?, telefono=?,
            invitado_por=?, sexo=?, rango_edad=?, visita_casa=?
        WHERE id=?
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

    r = conn.execute(
        "SELECT * FROM visitas WHERE id=?",
        (id,)
    ).fetchone()
    conn.close()

    return render_template("editar.html", r=r)


# ---------- ELIMINAR (PROTEGIDO) ----------
@app.route("/eliminar/<int:id>")
def eliminar(id):
    if not session.get("logueado"):
        return redirect("/login")

    conn = conectar()
    conn.execute("DELETE FROM visitas WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/visitas")


# ---------- VISITAR / DETALLE (PROTEGIDO) ----------
@app.route("/visitar/<int:id>", methods=["GET", "POST"])
def visitar(id):
    if not session.get("logueado"):
        return redirect("/login")

    conn = conectar()

    detalle = conn.execute(
        "SELECT * FROM detalle_visita WHERE visita_id=?",
        (id,)
    ).fetchone()

    if request.method == "POST" and detalle is None:
        conn.execute("""
        INSERT INTO detalle_visita
        (visita_id, visitado_por, fecha_visita, nota)
        VALUES (?,?,?,?)
        """, (
            id,
            request.form["visitado_por"],
            request.form["fecha_visita"],
            request.form.get("nota", "")
        ))

        conn.execute(
            "UPDATE visitas SET visitado='Si' WHERE id=?",
            (id,)
        )

        conn.commit()

    conn.close()

    return render_template(
        "detalle_visita.html",
        detalle=detalle,
        id=id
    )


# ---------- IMPRIMIR (PROTEGIDO) ----------
@app.route("/imprimir")
def imprimir():
    if not session.get("logueado"):
        return redirect("/login")

    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    conn = conectar()
    visitas = conn.execute("""
        SELECT fecha, nombre, invitado_por, visitado
        FROM visitas
        WHERE fecha BETWEEN ? AND ?
        ORDER BY fecha
    """, (desde, hasta)).fetchall()
    conn.close()

    return render_template(
        "imprimir.html",
        visitas=visitas,
        desde=desde,
        hasta=hasta
    )


# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(debug=True)
