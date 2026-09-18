from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import io
import csv
from datetime import datetime

app = Flask(__name__)
app.secret_key = "famesa_explosivos_planta_2026_@hyperpro"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "famesa_multisede.db")

SEDES_VALIDAS = ["Puente Piedra", "Chancay", "La Joya"]

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nombre_completo TEXT NOT NULL,
        rol TEXT NOT NULL,
        sede_asignada TEXT NOT NULL DEFAULT 'TODAS',
        puede_registrar INTEGER DEFAULT 1,
        puede_editar INTEGER DEFAULT 0,
        puede_borrar INTEGER DEFAULT 0,
        puede_gestionar_categorias INTEGER DEFAULT 0,
        puede_exportar_excel INTEGER DEFAULT 1,
        puede_crear_usuarios INTEGER DEFAULT 0,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        aplica_comision INTEGER DEFAULT 0,
        color_tag TEXT DEFAULT '#E30613',
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS movimientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sede TEXT NOT NULL,
        fecha TEXT NOT NULL,
        hora TEXT NOT NULL,
        categoria TEXT NOT NULL,
        tipo_movimiento TEXT NOT NULL,
        cantidad INTEGER NOT NULL DEFAULT 1,
        empresa TEXT DEFAULT '-',
        placa TEXT DEFAULT '-',
        supervisor TEXT DEFAULT '-',
        motivo TEXT DEFAULT '-',
        registrado_por TEXT,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cats_default = [
        ("Personal Propio Famesa", 1, "#E30613"),
        ("Contratas / Servicios", 0, "#059669"),
        ("Transportistas / Carga", 0, "#2563EB"),
        ("Custodios / Seguridad", 0, "#7C3AED"),
        ("Policías / DINOES", 0, "#D97706"),
        ("Visitas Técnicas / Terceros", 0, "#0891B2")
    ]
    for nom, com, col in cats_default:
        c.execute("INSERT OR IGNORE INTO categorias (nombre, aplica_comision, color_tag) VALUES (?, ?, ?)", (nom, com, col))

    c.execute("SELECT * FROM usuarios WHERE username = 'admin'")
    if not c.fetchone():
        admin_hash = generate_password_hash("admin123")
        c.execute('''
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, sede_asignada,
                                  puede_registrar, puede_editar, puede_borrar, puede_gestionar_categorias,
                                  puede_exportar_excel, puede_crear_usuarios)
            VALUES (?, ?, ?, 'superadmin', 'TODAS', 1, 1, 1, 1, 1, 1)
        ''', ('admin', admin_hash, 'Administrador General FAMESA'))

        ops = [
            ("operador_pp", "pp123", "Operador Puente Piedra", "Puente Piedra"),
            ("operador_chancay", "chancay123", "Operador Chancay", "Chancay"),
            ("operador_lajoya", "lajoya123", "Operador La Joya", "La Joya")
        ]
        for u, p, n, s in ops:
            c.execute('''
                INSERT INTO usuarios (username, password_hash, nombre_completo, rol, sede_asignada,
                                      puede_registrar, puede_editar, puede_borrar, puede_gestionar_categorias,
                                      puede_exportar_excel, puede_crear_usuarios)
                VALUES (?, ?, ?, 'operador', ?, 1, 1, 0, 0, 1, 0)
            ''', (u, generate_password_hash(p), n, s))

    conn.commit()
    conn.close()

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM usuarios WHERE username = ?", (u,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], p):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["nombre"] = user["nombre_completo"]
            session["rol"] = user["rol"]
            session["sede_asignada"] = user["sede_asignada"]
            session["puede_registrar"] = bool(user["puede_registrar"])
            session["puede_editar"] = bool(user["puede_editar"])
            session["puede_borrar"] = bool(user["puede_borrar"])
            session["puede_gestionar_categorias"] = bool(user["puede_gestionar_categorias"])
            session["puede_exportar_excel"] = bool(user["puede_exportar_excel"])
            session["puede_crear_usuarios"] = bool(user["puede_crear_usuarios"])
            return redirect(url_for("panel_operativo"))
        else:
            flash("Credenciales incorrectas", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/panel")
def panel_operativo():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("panel_operativo.html")

@app.route("/usuarios")
def gestion_usuarios():
    if "user_id" not in session or not session.get("puede_crear_usuarios"):
        flash("Acceso denegado.", "error")
        return redirect(url_for("panel_operativo"))
    conn = get_db()
    users = conn.execute("SELECT * FROM usuarios ORDER BY id ASC").fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=users, sedes=SEDES_VALIDAS)

@app.route("/api/mi_perfil", methods=["PUT"])
def api_mi_perfil():
    if "user_id" not in session:
        return jsonify({"error": "No autenticado"}), 401
    d = request.json
    nuevo_username = d.get("username", "").strip()
    nueva_password = d.get("password", "").strip()
    user_id = session["user_id"]
    if not nuevo_username:
        return jsonify({"error": "Usuario requerido"}), 400
    conn = get_db()
    c = conn.cursor()
    try:
        if nueva_password:
            nueva_hash = generate_password_hash(nueva_password)
            c.execute("UPDATE usuarios SET username = ?, password_hash = ? WHERE id = ?", (nuevo_username, nueva_hash, user_id))
        else:
            c.execute("UPDATE usuarios SET username = ? WHERE id = ?", (nuevo_username, user_id))
        conn.commit()
        session["username"] = nuevo_username
        conn.close()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "El usuario ya existe"}), 400

@app.route("/api/categorias", methods=["GET", "POST", "DELETE"])
def api_categorias():
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST":
        if "user_id" not in session or not session.get("puede_gestionar_categorias"):
            conn.close()
            return jsonify({"error": "No autorizado"}), 403
        data = request.json
        nombre = data.get("nombre", "").strip()
        aplica_com = 1 if data.get("aplica_comision") else 0
        color = data.get("color_tag", "#E30613")
        if not nombre:
            conn.close()
            return jsonify({"error": "Nombre requerido"}), 400
        try:
            c.execute("INSERT INTO categorias (nombre, aplica_comision, color_tag) VALUES (?, ?, ?)", (nombre, aplica_com, color))
            conn.commit()
            conn.close()
            return jsonify({"success": True})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "Ya existe"}), 400
    elif request.method == "DELETE":
        if "user_id" not in session or not session.get("puede_gestionar_categorias"):
            conn.close()
            return jsonify({"error": "No autorizado"}), 403
        cat_id = request.args.get("id")
        cat_row = c.execute("SELECT nombre FROM categorias WHERE id = ?", (cat_id,)).fetchone()
        if cat_row:
            cat_nom = cat_row["nombre"]
            c.execute("DELETE FROM movimientos WHERE categoria = ?", (cat_nom,))
            c.execute("DELETE FROM categorias WHERE id = ?", (cat_id,))
            conn.commit()
        conn.close()
        return jsonify({"success": True})
    cats = c.execute("SELECT * FROM categorias ORDER BY id ASC").fetchall()
    conn.close()
    return jsonify([dict(row) for row in cats])

@app.route("/api/resumen")
def api_resumen():
    sede = request.args.get("sede", "Puente Piedra")
    fecha = request.args.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    conn = get_db()
    c = conn.cursor()
    cats_db = c.execute("SELECT * FROM categorias ORDER BY id ASC").fetchall()
    cats_map = {row["nombre"]: dict(row) for row in cats_db}

    if sede == "TODAS":
        movs = c.execute("SELECT * FROM movimientos WHERE fecha = ? ORDER BY id DESC", (fecha,)).fetchall()
    else:
        movs = c.execute("SELECT * FROM movimientos WHERE sede = ? AND fecha = ? ORDER BY id DESC", (sede, fecha)).fetchall()
    conn.close()

    metricas = {}
    for nom in cats_map:
        metricas[nom] = {
            "ingresos": 0, "salidas": 0, "com_sal": 0, "com_ret": 0,
            "com_activa": 0, "presentes": 0,
            "aplica_comision": cats_map[nom]["aplica_comision"],
            "color_tag": cats_map[nom]["color_tag"]
        }

    for m in movs:
        cat = m["categoria"]
        if cat in metricas:
            t = m["tipo_movimiento"]
            cant = int(m["cantidad"] or 0)
            if t == "INGRESO TURNO":
                metricas[cat]["ingresos"] += cant
            elif t == "SALIDA TURNO":
                metricas[cat]["salidas"] += cant
            elif t == "SALIDA COMISIÓN":
                metricas[cat]["com_sal"] += cant
            elif t == "RETORNO COMISIÓN":
                metricas[cat]["com_ret"] += cant

    tot_ing = tot_sal = tot_com_s = tot_com_r = tot_com_act = tot_presentes = 0
    tabla_resumen = []
    tarjetas_dinamicas = []

    for nom, item in metricas.items():
        if item["aplica_comision"] == 1:
            item["com_activa"] = max(0, item["com_sal"] - item["com_ret"])
            item["presentes"] = max(0, (item["ingresos"] - item["salidas"]) - item["com_activa"])
        else:
            item["com_activa"] = 0
            item["presentes"] = max(0, item["ingresos"] - item["salidas"])

        tot_ing += item["ingresos"]
        tot_sal += item["salidas"]
        tot_com_s += item["com_sal"]
        tot_com_r += item["com_ret"]
        tot_com_act += item["com_activa"]
        tot_presentes += item["presentes"]

        tarjetas_dinamicas.append({
            "categoria": nom,
            "presentes": item["presentes"],
            "color_tag": item["color_tag"],
            "ingresos": item["ingresos"],
            "salidas": item["salidas"],
            "com_activa": item["com_activa"] if item["aplica_comision"] else 0
        })

        tabla_resumen.append({
            "categoria": nom,
            "color_tag": item["color_tag"],
            "ingresos": item["ingresos"],
            "salidas": item["salidas"],
            "com_sal": item["com_sal"] if item["aplica_comision"] else "-",
            "com_ret": item["com_ret"] if item["aplica_comision"] else "-",
            "com_activa": item["com_activa"] if item["aplica_comision"] else "-",
            "presentes": item["presentes"]
        })

    return jsonify({
        "sede": sede,
        "fecha": fecha,
        "kpis": {
            "total_planta": tot_presentes,
            "total_ingresos": tot_ing,
            "total_salidas": tot_sal
        },
        "tarjetas": tarjetas_dinamicas,
        "tabla": tabla_resumen,
        "totales_pie": {
            "ingresos": tot_ing,
            "salidas": tot_sal,
            "com_sal": tot_com_s,
            "com_ret": tot_com_r,
            "com_activa": tot_com_act,
            "presentes": tot_presentes
        }
    })

@app.route("/api/movimientos", methods=["GET", "POST"])
def api_movimientos():
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST":
        if "user_id" not in session or not session.get("puede_registrar"):
            conn.close()
            return jsonify({"error": "Sin permisos"}), 403
        data = request.json
        sede = data.get("sede")
        sede_user = session.get("sede_asignada")
        if sede_user != "TODAS" and sede_user != sede:
            conn.close()
            return jsonify({"error": "Acceso denegado"}), 403

        c.execute('''
            INSERT INTO movimientos (sede, fecha, hora, categoria, tipo_movimiento, cantidad, empresa, placa, supervisor, motivo, registrado_por)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sede,
            data.get("fecha") or datetime.now().strftime("%Y-%m-%d"),
            data.get("hora") or datetime.now().strftime("%H:%M:%S"),
            data.get("categoria"),
            data.get("tipo_movimiento"),
            int(data.get("cantidad") or 1),
            (data.get("empresa") or "").strip() or "-",
            (data.get("placa") or "").strip() or "-",
            (data.get("supervisor") or "").strip() or "-",
            (data.get("motivo") or "").strip() or "-",
            session.get("username")
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    sede = request.args.get("sede", "Puente Piedra")
    fecha = request.args.get("fecha")
    mes = request.args.get("mes")
    sql = "SELECT * FROM movimientos WHERE 1=1"
    params = []
    if sede != "TODAS":
        sql += " AND sede = ?"
        params.append(sede)
    if mes:
        sql += " AND fecha LIKE ?"
        params.append(f"{mes}%")
    elif fecha:
        sql += " AND fecha = ?"
        params.append(fecha)
    sql += " ORDER BY id DESC"
    rows = c.execute(sql, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/movimientos/<int:id>", methods=["DELETE"])
def api_movimiento_del(id):
    if "user_id" not in session or not session.get("puede_borrar"):
        return jsonify({"error": "Sin permisos"}), 403
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM movimientos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/exportar_excel")
def exportar_excel():
    if "user_id" not in session or not session.get("puede_exportar_excel"):
        return "Acceso denegado", 403
    sede = request.args.get("sede", "TODAS").strip()
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    conn = get_db()
    c = conn.cursor()
    rows = c.execute("SELECT * FROM movimientos WHERE sede = ? OR ? = 'TODAS'", (sede, sede)).fetchall()
    conn.close()

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte"
    ws.cell(row=1, column=1, value="FAMESA EXPLOSIVOS - REPORTE")
    wb.save("reporte.xlsx")
    return send_file("reporte.xlsx", as_attachment=True)

@app.route("/api/usuarios", methods=["POST"])
def api_usuario_crear():
    if "user_id" not in session or not session.get("puede_crear_usuarios"):
        return jsonify({"error": "No autorizado"}), 403
    d = request.json
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, sede_asignada,
                                  puede_registrar, puede_editar, puede_borrar, puede_gestionar_categorias,
                                  puede_exportar_excel, puede_crear_usuarios)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            d.get("username"), generate_password_hash(d.get("password")), d.get("nombre"),
            d.get("rol", "operador"), d.get("sede_asignada", "Puente Piedra"),
            1 if d.get("puede_registrar") else 0, 1 if d.get("puede_editar") else 0,
            1 if d.get("puede_borrar") else 0, 1 if d.get("puede_gestionar_categorias") else 0,
            1 if d.get("puede_exportar_excel") else 0, 1 if d.get("rol") == "superadmin" else 0
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except:
        return jsonify({"error": "Error al crear"}), 400

@app.route("/api/usuarios/<int:id>", methods=["DELETE"])
def api_usuario_borrar(id):
    if "user_id" not in session or not session.get("puede_crear_usuarios"):
        return jsonify({"error": "No autorizado"}), 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/usuarios/<int:id>", methods=["GET"])
def api_usuario_get(id):
    conn = get_db()
    u = conn.execute("SELECT * FROM usuarios WHERE id = ?", (id,)).fetchone()
    conn.close()
    return jsonify(dict(u))

@app.route("/api/usuarios/<int:id>/editar", methods=["PUT"])
def api_usuario_editar_completo(id):
    if "user_id" not in session or not session.get("puede_crear_usuarios"):
        return jsonify({"error": "No autorizado"}), 403
    d = request.json
    conn = get_db()
    c = conn.cursor()
    if d.get("password"):
        c.execute("UPDATE usuarios SET nombre_completo=?, username=?, password_hash=?, sede_asignada=?, rol=?, puede_registrar=?, puede_editar=?, puede_borrar=?, puede_gestionar_categorias=?, puede_exportar_excel=? WHERE id=?",
                  (d.get("nombre"), d.get("username"), generate_password_hash(d.get("password")), d.get("sede_asignada"), d.get("rol"), 
                   1 if d.get("puede_registrar") else 0, 1 if d.get("puede_editar") else 0, 1 if d.get("puede_borrar") else 0, 1 if d.get("puede_gestionar_categorias") else 0, 1 if d.get("puede_exportar_excel") else 0, id))
    else:
        c.execute("UPDATE usuarios SET nombre_completo=?, username=?, sede_asignada=?, rol=?, puede_registrar=?, puede_editar=?, puede_borrar=?, puede_gestionar_categorias=?, puede_exportar_excel=? WHERE id=?",
                  (d.get("nombre"), d.get("username"), d.get("sede_asignada"), d.get("rol"), 
                   1 if d.get("puede_registrar") else 0, 1 if d.get("puede_editar") else 0, 1 if d.get("puede_borrar") else 0, 1 if d.get("puede_gestionar_categorias") else 0, 1 if d.get("puede_exportar_excel") else 0, id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)