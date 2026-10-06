from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import datetime

app = Flask(__name__)
app.secret_key = 'almacen_general_secret_key_2026'

# Usuarios registrados en el sistema
USUARIOS = {
    "admin": "1234",
    "almacen": "ecu2026"
}

def init_db():
    conn = sqlite3.connect('inventario_ecu_whs.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            fecha TEXT,
            badge TEXT,
            tipo TEXT,
            almacen TEXT DEFAULT 'ECU WHS',
            np TEXT,
            cantidad INTEGER,
            num_salida TEXT,
            consecutivo TEXT,
            ubicacion TEXT,
            qr_raw TEXT,
            fecha_prod TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_sap (
            np TEXT PRIMARY KEY,
            cantidad_sap INTEGER,
            fecha_actualizacion TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exactitud_mensual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT UNIQUE,
            porcentaje REAL,
            meta REAL DEFAULT 100.0,
            estatus TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incidencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            badge TEXT,
            np TEXT,
            ubicacion TEXT,
            tipo_incidencia TEXT,
            descripcion TEXT,
            estatus TEXT DEFAULT 'Abierta'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def obtener_estructura_racks():
    return {
        'ECU WHS (Racks A al H)': {
            'RACK A': [f"BA-{lvl:02d}-{b:02d}" for lvl in range(4, 0, -1) for b in range(1, 6)],
            'RACK B': [f"BB-{lvl:02d}-{b:02d}" for lvl in range(4, 0, -1) for b in range(1, 6)],
            'RACK C': [f"BC-{lvl:02d}-{b:02d}" for lvl in range(4, 0, -1) for b in range(1, 6)],
            'RACK D': [f"BD-{lvl:02d}-{b:02d}" for lvl in range(4, 0, -1) for b in range(1, 6)],
            'RACK F': [f"BF-{lvl:02d}-{b:02d}" for lvl in range(6, 0, -1) for b in range(1, 6)],
            'RACK G': [f"BG-{lvl:02d}-{b:02d}" for lvl in range(5, 0, -1) for b in range(1, 6)],
            'RACK H': [f"BH-{lvl:02d}-{b:02d}" for lvl in range(7, 0, -1) for b in (range(1, 4) if lvl == 7 else range(1, 6))]
        },
        'THT (Pasillos A01 y A02)': {
            'PASILLO A01 (30 BAHÍAS)': [f"A01-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 31)],
            'PASILLO A02 (26 BAHÍAS)': [f"A02-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 27)]
        },
        'PLANTA 2 (Zona C1 a C7)': {
            'RACK C1 (34 BAHÍAS)': [f"C01-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 35)],
            'RACK C2 (34 BAHÍAS)': [f"C02-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 35)],
            'RACK C3 (34 BAHÍAS)': [f"C03-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 35)],
            'RACK C4 (34 BAHÍAS)': [f"C04-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 35)],
            'RACK C5 (23 BAHÍAS)': [f"C05-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 24)],
            'RACK C6 (32 BAHÍAS)': [f"C06-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 33)],
            'RACK C7 (32 BAHÍAS)': [f"C07-{b:02d}-{lvl:02d}" for lvl in range(3, 0, -1) for b in range(1, 33)]
        }
    }

def parse_qr_bolsa(qr_str):
    raw = qr_str.strip()
    partes = raw.split(']')
    np, cant, fecha_prod = raw, 1, ""
    if len(partes) >= 4:
        np = partes[1].replace('Q', '').strip()
        fecha_prod = partes[3].strip()
        if len(partes) >= 6:
            try: cant = int(partes[5].strip())
            except: cant = 1
    elif len(partes) >= 2:
        np = partes[1].replace('Q', '').strip()
    return np, cant, fecha_prod, raw

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('index.html', usuario=session.get('user'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    # Soporta envíos desde Formulario HTML tradicional o JSON
    usuario = request.form.get('usuario')
    password = request.form.get('password')

    if not usuario and request.is_json:
        data = request.get_json(silent=True) or {}
        usuario = data.get('usuario')
        password = data.get('password')

    if usuario in USUARIOS and USUARIOS[usuario] == password:
        session['logged_in'] = True
        session['user'] = usuario
        if request.is_json:
            return jsonify({'status': 'ok'})
        return redirect('/')
    
    if request.is_json:
        return jsonify({'error': 'Credenciales inválidas'}), 401
    return render_template('login.html', error='Usuario o contraseña incorrectos')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/registrar', methods=['POST'])
def registrar():
    if not session.get('logged_in'): return jsonify({'error': 'No autorizado'}), 401
    data = request.json or {}
    np, cant, fecha_prod, qr_clean = parse_qr_bolsa(data.get('qr_raw', ''))
    
    conn = sqlite3.connect('inventario_ecu_whs.db')
    cursor = conn.cursor()
    fecha_act = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    folio = f"FOL-{int(datetime.datetime.now().timestamp())}"

    cursor.execute('''
        INSERT INTO movimientos (folio, fecha, badge, tipo, almacen, np, cantidad, ubicacion, qr_raw, fecha_prod)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (folio, fecha_act, data.get('badge', 'OP'), data.get('tipo', 'Entrada'), data.get('almacen'), np, cant, data.get('ubicacion'), qr_clean, fecha_prod))

    conn.commit()
    conn.close()
    return jsonify({'mensaje': 'Registrado', 'np': np, 'cantidad': cant, 'fecha_prod': fecha_prod})

@app.route('/api/layout/estratificado', methods=['GET'])
def get_layout_estratificado():
    try:
        alm_param = request.args.get('almacen', 'ECU WHS (Racks A al H)')
        estructuras = obtener_estructura_racks().get(alm_param, {})

        alm_db = "PLANTA 2" if "PLANTA 2" in alm_param else ("THT" if "THT" in alm_param else "ECU WHS")

        conn = sqlite3.connect('inventario_ecu_whs.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ubicacion, np, SUM(CASE WHEN tipo IN ('Entrada', 'Entrada de embarque', 'Retorno', 'Adicional') THEN cantidad ELSE -cantidad END) as total, fecha_prod
            FROM movimientos
            WHERE almacen LIKE ?
            GROUP BY ubicacion, np
        ''', (f"%{alm_db}%",))
        rows = cursor.fetchall()
        conn.close()

        inventario_map = {}
        for r in rows:
            ubi, np, cant, f_prod = r[0], r[1], r[2], r[3]
            if ubi and cant and cant > 0:
                if ubi not in inventario_map: inventario_map[ubi] = []
                inventario_map[ubi].append({'np': np, 'cantidad': cant, 'fecha_prod': f_prod})

        resultado = {}
        for nombre_rack, ubis in estructuras.items():
            resultado[nombre_rack] = []
            for u in ubis:
                items = inventario_map.get(u, [])
                resultado[nombre_rack].append({'ubicacion': u, 'items': items})

        return jsonify(resultado)
    except Exception as e:
        print("Error en layout:", str(e))
        return jsonify({}), 200

@app.route('/api/fifo/sugerir/<string:np_buscar>', methods=['GET'])
def sugerir_fifo(np_buscar):
    conn = sqlite3.connect('inventario_ecu_whs.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, folio, fecha, ubicacion, cantidad, fecha_prod
        FROM movimientos
        WHERE np = ? AND tipo IN ('Entrada', 'Entrada de embarque', 'Retorno', 'Adicional')
        ORDER BY CASE WHEN fecha_prod != '' THEN fecha_prod ELSE fecha END ASC
        LIMIT 1
    ''', (np_buscar,))
    r = cursor.fetchone()
    conn.close()

    if r:
        return jsonify({'encontrado': True, 'ubicacion_fifo': r[3], 'cantidad': r[4], 'fecha_prod': r[5], 'fecha_ingreso': r[2]})
    return jsonify({'encontrado': False, 'mensaje': 'Sin stock para este NP.'})

@app.route('/api/stock', methods=['GET'])
def get_stock():
    alm = request.args.get('almacen', 'TODOS')
    conn = sqlite3.connect('inventario_ecu_whs.db')
    cursor = conn.cursor()
    if alm == 'TODOS':
        cursor.execute('''
            SELECT COALESCE(almacen, 'ECU WHS') as a, np, SUM(CASE WHEN tipo IN ('Entrada', 'Entrada de embarque', 'Retorno', 'Adicional') THEN cantidad ELSE -cantidad END) as total 
            FROM movimientos GROUP BY a, np HAVING total > 0
        ''')
    else:
        cursor.execute('''
            SELECT COALESCE(almacen, 'ECU WHS') as a, np, SUM(CASE WHEN tipo IN ('Entrada', 'Entrada de embarque', 'Retorno', 'Adicional') THEN cantidad ELSE -cantidad END) as total 
            FROM movimientos WHERE COALESCE(almacen, 'ECU WHS') = ? GROUP BY np HAVING total > 0
        ''', (alm,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{'almacen': r[0], 'np': r[1], 'total': r[2]} for r in rows])

@app.route('/api/movimientos', methods=['GET'])
def get_movimientos():
    conn = sqlite3.connect('inventario_ecu_whs.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, folio, fecha, badge, tipo, np, cantidad, ubicacion, num_salida, almacen, fecha_prod FROM movimientos ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'folio': r[1], 'fecha': r[2], 'badge': r[3], 'tipo': r[4],
        'np': r[5], 'cantidad': r[6], 'ubicacion': r[7], 'num_salida': r[8], 'almacen': r[9], 'fecha_prod': r[10]
    } for r in rows])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)