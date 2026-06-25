import base64
import io
import os
import pandas as pd
from flask import Flask
from dash import Dash, dcc, html, Input, Output, State, dash_table
from dash.dash_table.Format import Format, Scheme, Group, Symbol
import plotly.graph_objs as go

# ==================== CONFIG DEL LOGO ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PATH_DEL_LOGO = os.path.join(BASE_DIR, "logo.png")

def encode_image(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""

logo_base64 = encode_image(PATH_DEL_LOGO)

# ==================== DICCIONARIO DE MESES ====================
MESES_ORDEN = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
    'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
    'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12
}

def obtener_clave_orden(mes_str):
    partes = str(mes_str).split()
    if len(partes) == 2:
        mes, año = partes
        return (int(año), MESES_ORDEN.get(mes.upper(), 0))
    return (0, 0)

# ==================== UTILIDADES PARA DETECCIÓN DE ENCABEZADO Y COLUMNAS ====================
def detectar_encabezado_y_columnas(df):
    """
    Busca la fila que contiene 'Código' y 'Nombre' y devuelve:
    header_row_idx, col_code, col_name, col_debe, col_haber
    Si no encuentra, devuelve índices por defecto pero imprime advertencia.
    """
    col_code = col_name = col_debe = col_haber = None
    header_row_idx = 0

    # Revisar primeras 12 filas para encontrar encabezado
    for r in range(min(12, len(df))):
        row_vals = [str(x).strip().lower() for x in df.iloc[r].fillna("").astype(str).tolist()]
        row_text = " ".join(row_vals)
        if "código" in row_text or "codigo" in row_text or "nombre de la cuenta" in row_text:
            header_row_idx = r
            for c in range(df.shape[1]):
                cell = str(df.iat[r, c]).strip().lower()
                if cell in ["código", "codigo", "cod", "codigo cuenta", "codigo de la cuenta"]:
                    col_code = c
                if "nombre" in cell and "cuenta" in cell:
                    col_name = c
                if cell in ["débito", "debito", "debe"]:
                    col_debe = c
                if cell in ["crédito", "credito", "haber"]:
                    col_haber = c
            break

    # Heurística si no se detectó encabezado
    if col_code is None or col_name is None:
        # Buscar columna con patrones de códigos (ej. '101', '201', '115')
        for c in range(df.shape[1]):
            sample = " ".join([str(x) for x in df.iloc[:8, c].fillna("").astype(str).tolist()]).lower()
            # si hay muchos valores con punto o números de cuenta, asumimos que es la columna código
            if any(part.strip().replace('.', '').isdigit() and len(part.strip()) >= 3 for part in sample.split()):
                if col_code is None:
                    col_code = c

    # Asignar valores por defecto si aún faltan
    if col_code is None: col_code = 0
    if col_name is None: col_name = 1
    if col_debe is None: col_debe = 6
    if col_haber is None: col_haber = 7

    return header_row_idx, col_code, col_name, col_debe, col_haber

# ==================== EXTRACCIÓN DE CATÁLOGO ====================
def construir_catalogo(df, col_code, col_name):
    """
    Recorre el df y construye un diccionario {codigo: nombre} con las filas que tengan código no vacío.
    Devuelve además la lista ordenada de códigos detectados.
    """
    catalogo = {}
    for i in range(len(df)):
        codigo = df.iat[i, col_code] if pd.notna(df.iat[i, col_code]) else ""
        nombre = df.iat[i, col_name] if pd.notna(df.iat[i, col_name]) else ""
        codigo_s = str(codigo).strip()
        nombre_s = str(nombre).strip()
        if codigo_s not in ["", "nan", "None"]:
            catalogo[codigo_s] = nombre_s
    codigos = sorted(catalogo.keys())
    return catalogo, codigos

# ==================== BÚSQUEDAS Y SUMAS POR LISTA EXACTA ====================
def obtener_saldo_por_catalogo_exacto(df, lista_codigos, col_code, col_debe, col_haber, es_acreedora=False):
    """
    Suma Débito y Crédito únicamente para los códigos exactos en lista_codigos.
    Retorna (debe - haber) o (haber - debe) si es_acreedora.
    """
    total_debe = 0.0
    total_haber = 0.0
    set_codigos = set([str(c).strip() for c in lista_codigos])

    for i in range(len(df)):
        codigo = str(df.iat[i, col_code]).strip() if pd.notna(df.iat[i, col_code]) else ""
        if codigo in set_codigos:
            debe = df.iat[i, col_debe] if pd.notna(df.iat[i, col_debe]) else 0.0
            haber = df.iat[i, col_haber] if pd.notna(df.iat[i, col_haber]) else 0.0
            try:
                total_debe += float(debe)
            except:
                pass
            try:
                total_haber += float(haber)
            except:
                pass

    return (total_haber - total_debe) if es_acreedora else (total_debe - total_haber)

# ==================== FUNCIONES EXISTENTES ADAPTADAS A COLUMNAS DINÁMICAS ====================
def obtener_valor_por_nombre_o_codigo(df, buscado, col_code, col_name, col_val):
    buscado_l = str(buscado).strip().lower()
    for i in range(len(df)):
        codigo = str(df.iat[i, col_code]).strip().lower() if pd.notna(df.iat[i, col_code]) else ""
        nombre = str(df.iat[i, col_name]).strip().lower() if pd.notna(df.iat[i, col_name]) else ""
        if codigo == buscado_l or nombre == buscado_l:
            val = df.iat[i, col_val]
            return float(val) if pd.notna(val) and val != "" else 0.0
    return 0.0

def obtener_movimiento_neto_por_nombre_o_codigo(df, buscado, col_code, col_name, col_cargo, col_abono, es_acreedora=False):
    buscado_l = str(buscado).strip().lower()
    for i in range(len(df)):
        codigo = str(df.iat[i, col_code]).strip().lower() if pd.notna(df.iat[i, col_code]) else ""
        nombre = str(df.iat[i, col_name]).strip().lower() if pd.notna(df.iat[i, col_name]) else ""
        if codigo == buscado_l or nombre == buscado_l:
            cargo = float(df.iat[i, col_cargo]) if not pd.isna(df.iat[i, col_cargo]) else 0.0
            abono = float(df.iat[i, col_abono]) if not pd.isna(df.iat[i, col_abono]) else 0.0
            return (abono - cargo) if es_acreedora else (cargo - abono)
    return 0.0

# ==================== PROCESADOR PRINCIPAL DEL EXCEL (INTEGRADO) ====================
def procesar_archivo_bytes(content, filename):
    header, encoded = content.split(",", 1)
    data = base64.b64decode(encoded)
    df_raw = pd.read_excel(io.BytesIO(data), header=None, dtype=object)

    mes_nombre = os.path.splitext(os.path.basename(filename))[0]

    # Detectar encabezado y columnas
    header_row_idx, col_code, col_name, col_debe, col_haber = detectar_encabezado_y_columnas(df_raw)

    # Construir catálogo de cuentas (lista exacta de códigos)
    catalogo, codigos_detectados = construir_catalogo(df_raw, col_code, col_name)

    # Si el catálogo está vacío, intentar heurística alternativa
    if not codigos_detectados:
        # intentar tomar la columna 0 como códigos y 1 como nombres
        catalogo, codigos_detectados = construir_catalogo(df_raw, 0, 1)

    # --- CÁLCULOS ESTADO DE RESULTADOS (ACUMULADO) ---
    # Para compatibilidad con tu estructura original, buscamos por nombres de secciones
    # Buscamos en la columna 'Nombre de la cuenta' (col_name) y tomamos la columna final (col_haber) o (col_debe) según corresponda
    # Nota: aquí asumimos que en tu archivo los saldos acumulados están en las columnas 6/7 como antes; si no, se puede adaptar.
    # Intentamos localizar las filas por texto exacto en la columna nombre
    def buscar_saldo_por_texto(texto, col_val):
        return obtener_valor_por_nombre_o_codigo(df_raw, texto, col_code, col_name, col_val)

    # Ingresos acumulados: buscar "4 Ingresos" en nombre o código
    ingresos_acum = buscar_saldo_por_texto("4 Ingresos", col_haber) + buscar_saldo_por_texto("704.04", col_haber)
    costos_acum = buscar_saldo_por_texto("5 Costos", col_debe)
    gastos_gen_acum = buscar_saldo_por_texto("6 Gastos generales", col_debe) + buscar_saldo_por_texto("701.10 Comisiones bancarias", col_debe)

    utilidad_bruta_acum = ingresos_acum - costos_acum
    utilidad_operacion_acum = utilidad_bruta_acum - gastos_gen_acum

    gastos_fin_acum = buscar_saldo_por_texto("701.01 Pérdida cambiaria", col_debe) + buscar_saldo_por_texto("701.04 Intereses a cargo bancario nacional", col_debe)
    prod_fin_acum = buscar_saldo_por_texto("702.01 Utilidad cambiaria", col_haber)

    utilidad_neta_acum = utilidad_operacion_acum - gastos_fin_acum + prod_fin_acum

    data_acumulada = {
        "Mes": mes_nombre, "Tipo_Reporte": "Acumulado",
        "Ingresos": ingresos_acum, "Costos": costos_acum, "% Costos": costos_acum/ingresos_acum if ingresos_acum else 0,
        "Utilidad Bruta": utilidad_bruta_acum, "% Utilidad Bruta": utilidad_bruta_acum/ingresos_acum if ingresos_acum else 0,
        "Gastos Generales": gastos_gen_acum, "% Gastos Gen.": gastos_gen_acum/ingresos_acum if ingresos_acum else 0,
        "Utilidad Operación": utilidad_operacion_acum, "% Util. Operación": utilidad_operacion_acum/ingresos_acum if ingresos_acum else 0,
        "Gastos Financieros": gastos_fin_acum, "% Gastos Fin.": gastos_fin_acum/ingresos_acum if ingresos_acum else 0,
        "Productos Financieros": prod_fin_acum, "% Prod. Fin.": prod_fin_acum/ingresos_acum if ingresos_acum else 0,
        "Utilidad Neta": utilidad_neta_acum, "% Utilidad Neta": utilidad_neta_acum/ingresos_acum if ingresos_acum else 0
    }

    # --- CÁLCULOS ESTADO DE RESULTADOS (MENSUAL) ---
    def buscar_movimiento_por_texto(texto, es_acreedora=False):
        return obtener_movimiento_neto_por_nombre_o_codigo(df_raw, texto, col_code, col_name, col_debe, col_haber, es_acreedora)

    ingresos_mes = buscar_movimiento_por_texto("4 Ingresos", es_acreedora=True) + buscar_movimiento_por_texto("704.04", es_acreedora=True)
    costos_mes = buscar_movimiento_por_texto("5 Costos", es_acreedora=False)
    gastos_gen_mes = buscar_movimiento_por_texto("6 Gastos generales", es_acreedora=False) + buscar_movimiento_por_texto("701.10 Comisiones bancarias", es_acreedora=False)

    utilidad_bruta_mes = ingresos_mes - costos_mes
    utilidad_operacion_mes = utilidad_bruta_mes - gastos_gen_mes

    gastos_fin_mes = buscar_movimiento_por_texto("701.01 Pérdida cambiaria", es_acreedora=False) + buscar_movimiento_por_texto("701.04 Intereses a cargo bancario nacional", es_acreedora=False)
    prod_fin_mes = buscar_movimiento_por_texto("702.01 Utilidad cambiaria", es_acreedora=True)

    utilidad_neta_mes = utilidad_operacion_mes - gastos_fin_mes + prod_fin_mes

    data_mensual = {
        "Mes": mes_nombre, "Tipo_Reporte": "Mensual",
        "Ingresos": ingresos_mes, "Costos": costos_mes, "% Costos": costos_mes/ingresos_mes if ingresos_mes else 0,
        "Utilidad Bruta": utilidad_bruta_mes, "% Utilidad Bruta": utilidad_bruta_mes/ingresos_mes if ingresos_mes else 0,
        "Gastos Generales": gastos_gen_mes, "% Gastos Gen.": gastos_gen_mes/ingresos_mes if ingresos_mes else 0,
        "Utilidad Operación": utilidad_operacion_mes, "% Util. Operación": utilidad_operacion_mes/ingresos_mes if ingresos_mes else 0,
        "Gastos Financieros": gastos_fin_mes, "% Gastos Fin.": gastos_fin_mes/ingresos_mes if ingresos_mes else 0,
        "Productos Financieros": prod_fin_mes, "% Prod. Fin.": prod_fin_mes/ingresos_mes if ingresos_mes else 0,
        "Utilidad Neta": utilidad_neta_mes, "% Utilidad Neta": utilidad_neta_mes/ingresos_mes if ingresos_mes else 0
    }

    # --- CÁLCULOS BALANCE (USANDO LISTA EXACTA DE CÓDIGOS DEL CATÁLOGO) ---
    # Construimos listas exactas de códigos para cada rubro usando el catálogo detectado.
    # Aquí puedes ajustar las reglas de selección: por ejemplo, incluir solo códigos que empiecen por '101' o incluir subcuentas específicas.
    # Como pediste "lista exacta", tomamos los códigos exactos detectados en el catálogo que correspondan a cada familia.
    def filtrar_codigos_por_prefijo_exacto(prefijos):
        # devuelve lista de códigos exactos del catálogo que empiezan por alguno de los prefijos
        res = []
        for c in codigos_detectados:
            for p in prefijos:
                if str(c).startswith(str(p)):
                    res.append(c)
                    break
        return res

    # Ejemplos de familias (ajusta si quieres otras agrupaciones)
    codigos_efectivo = filtrar_codigos_por_prefijo_exacto(['101', '102'])
    codigos_cxc = filtrar_codigos_por_prefijo_exacto(['105'])
    codigos_inventarios = filtrar_codigos_por_prefijo_exacto(['115'])
    codigos_imp_recuperar = filtrar_codigos_por_prefijo_exacto(['113', '114', '118', '119'])
    codigos_otras_cxc = filtrar_codigos_por_prefijo_exacto(['107'])

    efectivo = obtener_saldo_por_catalogo_exacto(df_raw, codigos_efectivo, col_code, col_debe, col_haber, es_acreedora=False)
    cxc = obtener_saldo_por_catalogo_exacto(df_raw, codigos_cxc, col_code, col_debe, col_haber, es_acreedora=False)
    inventarios = obtener_saldo_por_catalogo_exacto(df_raw, codigos_inventarios, col_code, col_debe, col_haber, es_acreedora=False)
    imp_recuperar = obtener_saldo_por_catalogo_exacto(df_raw, codigos_imp_recuperar, col_code, col_debe, col_haber, es_acreedora=False)
    otras_cxc = obtener_saldo_por_catalogo_exacto(df_raw, codigos_otras_cxc, col_code, col_debe, col_haber, es_acreedora=False)

    activo_circulante = efectivo + cxc + inventarios + imp_recuperar + otras_cxc

    # Activo fijo: equipo de cómputo y transporte (tomamos códigos exactos detectados)
    codigos_eq_computo = filtrar_codigos_por_prefijo_exacto(['154', '156'])
    codigos_depreciacion = filtrar_codigos_por_prefijo_exacto(['171'])

    eq_computo = obtener_saldo_por_catalogo_exacto(df_raw, codigos_eq_computo, col_code, col_debe, col_haber, es_acreedora=False)
    depreciacion = obtener_saldo_por_catalogo_exacto(df_raw, codigos_depreciacion, col_code, col_debe, col_haber, es_acreedora=False)
    activo_fijo = eq_computo + depreciacion

    total_activo = activo_circulante + activo_fijo

    # Pasivos
    codigos_proveedores = filtrar_codigos_por_prefijo_exacto(['201'])
    codigos_impuestos = filtrar_codigos_por_prefijo_exacto(['208', '209', '213', '216'])
    codigos_otros_pasivos = filtrar_codigos_por_prefijo_exacto(['205', '206', '210'])

    proveedores = obtener_saldo_por_catalogo_exacto(df_raw, codigos_proveedores, col_code, col_debe, col_haber, es_acreedora=True)
    imp_pagar = obtener_saldo_por_catalogo_exacto(df_raw, codigos_impuestos, col_code, col_debe, col_haber, es_acreedora=True)
    otros_pasivos = obtener_saldo_por_catalogo_exacto(df_raw, codigos_otros_pasivos, col_code, col_debe, col_haber, es_acreedora=True)

    pasivo_circulante = proveedores + imp_pagar + otros_pasivos

    # Capital contable: tomamos códigos 301 y 304 detectados
    codigos_capital_social = filtrar_codigos_por_prefijo_exacto(['301'])
    codigos_resultados_acum = filtrar_codigos_por_prefijo_exacto(['304'])

    capital_social = obtener_saldo_por_catalogo_exacto(df_raw, codigos_capital_social, col_code, col_debe, col_haber, es_acreedora=True)
    res_acumulados = obtener_saldo_por_catalogo_exacto(df_raw, codigos_resultados_acum, col_code, col_debe, col_haber, es_acreedora=True)
    utilidad_ejercicio = utilidad_neta_acum

    capital_contable = capital_social + res_acumulados + utilidad_ejercicio
    total_pasivo_capital = pasivo_circulante + capital_contable

    data_balance = {
        "Mes": mes_nombre, "Tipo_Reporte": "Balance",
        "Efectivo": efectivo, "% Efectivo": efectivo/total_activo if total_activo else 0,
        "Cuentas por Cobrar": cxc, "% Cuentas x Cobrar": cxc/total_activo if total_activo else 0,
        "Inventarios": inventarios, "% Inventarios": inventarios/total_activo if total_activo else 0,
        "Impuestos por Recuperar": imp_recuperar, "% Imp. Recuperar": imp_recuperar/total_activo if total_activo else 0,
        "Otras Cuentas x Cobrar": otras_cxc, "% Otras CxC": otras_cxc/total_activo if total_activo else 0,
        "Total Activo Circulante": activo_circulante, "% Act. Circulante": activo_circulante/total_activo if total_activo else 0,
        "Equipo de Cómputo": eq_computo,
        "Depreciación Acumulada": depreciacion,
        "Total Activo Fijo": activo_fijo, "% Act. Fijo": activo_fijo/total_activo if total_activo else 0,
        "Total Activo": total_activo,
        "Proveedores": proveedores, "% Proveedores": proveedores/total_pasivo_capital if total_pasivo_capital else 0,
        "Impuestos por Pagar": imp_pagar, "% Imp. Pagar": imp_pagar/total_pasivo_capital if total_pasivo_capital else 0,
        "Otros Pasivos": otros_pasivos, "% Otros Pasivos": otros_pasivos/total_pasivo_capital if total_pasivo_capital else 0,
        "Total Pasivo": pasivo_circulante, "% Total Pasivo": pasivo_circulante/total_pasivo_capital if total_pasivo_capital else 0,
        "Capital Social": capital_social,
        "Resultados Acumulados": res_acumulados,
        "Utilidad del Ejercicio": utilidad_ejercicio,
        "Total Capital": capital_contable, "% Total Capital": capital_contable/total_pasivo_capital if total_pasivo_capital else 0,
        "Total Pasivo y Capital": total_pasivo_capital
    }

    return data_acumulada, data_mensual, data_balance

# ==================== APP DASH (sin cambios funcionales importantes) ====================
server = Flask(__name__)
app = Dash(__name__, server=server)

app.index_string = """
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>Dashboard Financiero Ejecutivo</title>
    {%favicon%}
    {%css%}
    <style>
        html, body, #react-entry-point { width: 100%; height: 100%; margin: 0; padding: 0; background-color: #F8FAFC; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }
        .dash-table-container { width: 100% !important; }
        .Select-control { border: 1px solid #E2E8F0 !important; border-radius: 8px !important; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
"""

estilo_tab = {
    'borderBottom': '1px solid #E2E8F0', 'padding': '12px 24px', 'fontWeight': '600',
    'color': '#64748B', 'backgroundColor': '#F8FAFC', 'borderRadius': '8px 8px 0px 0px', 'marginRight': '4px'
}
estilo_tab_seleccionada = {
    'borderTop': '3px solid #0B2D5B', 'borderBottom': '3px solid #C9A227', 'backgroundColor': '#FFFFFF',
    'padding': '11px 24px', 'color': '#0B2D5B', 'fontWeight': '700', 'borderRadius': '8px 8px 0px 0px',
    'marginRight': '4px', 'boxShadow': '0px -2px 5px rgba(0,0,0,0.02)'
}

app.layout = html.Div([
    html.Div([
        html.Div([
            html.Img(src=f"data:image/png;base64,{logo_base64}" if logo_base64 else "", style={'height': '60px', 'marginRight': '20px', 'display': 'inline-block' if logo_base64 else 'none', 'backgroundColor': 'white', 'padding': '5px', 'borderRadius': '6px'}),
            html.Div([
                html.H2("REPORTE FINANCIERO INTEGRAL 2026", style={'color': '#FFFFFF', 'margin': '0', 'fontWeight': '700', 'fontSize': '26px', 'letterSpacing': '0.5px'}),
                html.Div("Resultados y Posición Financiera (Balance General)", style={'color': '#C9A227', 'fontSize': '13px', 'fontWeight': '5px', 'marginTop': '2px'})
            ], style={'display': 'inline-block', 'verticalAlign': 'middle'})
        ], style={'display': 'flex', 'alignItems': 'center'})
    ], style={'background': 'linear-gradient(135deg, #0B2D5B 0%, #1E3A61 100%)', 'padding': '20px 30px', 'borderRadius': '0px 0px 15px 15px', 'boxShadow': '0 4px 6px -1px rgba(0,0,0,0.1)', 'marginBottom': '25px', 'borderBottom': '4px solid #C9A227'}),

    html.Div([
        html.Label('Carga de Datos Operativos', style={'fontWeight': '700', 'color': '#0B2D5B', 'fontSize': '15px', 'display': 'block', 'marginBottom': '8px'}),
        dcc.Upload(
            id='upload-data',
            children=html.Div([html.Span('📂 ', style={'fontSize': '20px', 'marginRight': '8px'}), 'Arrastra o selecciona la carpeta con las balanzas (.xlsx)']),
            style={'width': '100%', 'height': '65px', 'lineHeight': '65px', 'borderWidth': '2px', 'borderStyle': 'dashed', 'borderColor': '#0B2D5B', 'borderRadius': '10px', 'textAlign': 'center', 'background': '#FFFFFF', 'color': '#0B2D5B', 'fontWeight': '600', 'cursor': 'pointer'},
            multiple=True, enable_folder_selection=True, accept='.xlsx'
        )
    ], style={'padding': '0 15px', 'marginBottom': '20px'}),

    html.Div(id='upload-status', style={'padding': '0 15px', 'fontWeight': '600', 'color': '#1E293B'}),

    html.Div([
        html.Div([
            html.Label('Filtrar por Mes', style={'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px', 'display': 'block'}),
            dcc.Dropdown(id='mes-filter', multi=True, placeholder='Todos los meses')
        ], style={'width':'23%','display':'inline-block','marginRight':'2%'}),
        html.Div([
            html.Label('Columnas Visibles', style={'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px', 'display': 'block'}),
            dcc.Dropdown(id='columns-filter', multi=True, placeholder='Todas las columnas', value=[])
        ], style={'width':'23%','display':'inline-block','marginRight':'2%'}),
        html.Div([
            html.Label('Métrica del Gráfico', style={'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px', 'display': 'block'}),
            dcc.Dropdown(id='metric-dropdown')
        ], style={'width':'23%','display':'inline-block','marginRight':'2%'}),
        html.Div([
            html.Label('Tipo de Vista', style={'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px', 'display': 'block'}),
            dcc.Dropdown(id='chart-type', options=[{'label':'Líneas de Tendencia','value':'lines'},{'label':'Barras Comparativas','value':'bars'}], value='lines', clearable=False)
        ], style={'width':'23%','display':'inline-block'})
    ], style={'margin': '15px', 'padding': '20px', 'background': '#FFFFFF', 'borderRadius': '12px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.05)'}),

    dcc.Tabs(id='report-tab', value='acumulado', children=[
        dcc.Tab(label='Estado de Resultados Acumulado', value='acumulado', style=estilo_tab, selected_style=estilo_tab_seleccionada),
        dcc.Tab(label='Estado de Resultados Mensual', value='mensual', style=estilo_tab, selected_style=estilo_tab_seleccionada),
        dcc.Tab(label='Balance General', value='balance', style=estilo_tab, selected_style=estilo_tab_seleccionada)
    ], style={'margin': '0 15px'}),

    html.Div([
        html.Div(
            style={'width': '100%', 'marginBottom': '25px', 'background': '#FFFFFF', 'borderRadius': '0px 0px 12px 12px', 'padding': '20px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.05)', 'borderTop': '1px solid #E2E8F0'},
            children=[
                dash_table.DataTable(
                    id='main-table', page_size=50, fixed_columns={'headers': True, 'data': 1},
                    style_table={'width':'100%', 'minWidth':'100%', 'overflowX':'auto'},
                    style_cell={'textAlign':'right', 'padding':'12px 15px', 'minWidth':'140px', 'width':'140px', 'maxWidth':'140px', 'fontFamily': 'Segoe UI, sans-serif', 'color': '#334155', 'border': '1px solid #E2E8F0'},
                    style_cell_conditional=[{'if':{'column_id':'Mes'}, 'textAlign':'center', 'fontWeight':'bold', 'color': '#0B2D5B', 'backgroundColor': '#F8FAFC'}],
                    style_header={'backgroundColor':'#0B2D5B', 'color':'white', 'fontWeight':'700', 'textAlign':'center', 'border': '1px solid #0B2D5B'},
                    style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#F8FAFC'}],
                    sort_action='custom', sort_mode='single', sort_by=[], page_action='native'
                )
            ]
        ),
        html.Div(id='graph-container', style={'width': '100%', 'background': '#FFFFFF', 'borderRadius': '12px', 'padding': '15px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.05)'})
    ], style={'padding': '0 15px'}),

    dcc.Store(id='df-store')
], style={'width':'100%', 'maxWidth':'100%', 'margin':'0', 'boxSizing': 'border-box'})

# ---------------------- CALLBACKS ----------------------
@app.callback(
    Output('df-store', 'data'),
    Output('upload-status', 'children'),
    Output('mes-filter', 'options'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def handle_upload(upload_contents, upload_names):
    if not upload_contents or not upload_names:
        return None, '', []

    resultados = []
    valid_files = [(c, n) for c, n in zip(upload_contents, upload_names) if n.lower().endswith('.xlsx')]

    for content, name in valid_files:
        try:
            acum, mens, bal = procesar_archivo_bytes(content, name)
            resultados.extend([acum, mens, bal])
        except Exception as e:
            return None, html.Div(f"Error procesando {name}: {e}", style={'color': '#EF4444'}), []

    df = pd.DataFrame(resultados)

    cols = df.columns.tolist()
    if 'Mes' in cols:
        cols.insert(0, cols.pop(cols.index('Mes')))
    if 'Tipo_Reporte' in cols:
        cols.insert(0, cols.pop(cols.index('Tipo_Reporte')))
    df = df[cols]

    meses_unicos = sorted(df['Mes'].unique(), key=obtener_clave_orden)
    mes_options = [{'label': m, 'value': m} for m in meses_unicos]

    status_msg = html.Div(f'✓ {len(valid_files)} archivos procesados con éxito.', style={'color': '#10B981', 'padding': '10px 0'})
    return df.to_json(date_format='iso', orient='split'), status_msg, mes_options

@app.callback(
    Output('metric-dropdown', 'options'),
    Output('metric-dropdown', 'value'),
    Output('columns-filter', 'options'),
    Output('columns-filter', 'value'),
    Input('df-store', 'data'),
    Input('report-tab', 'value')
)
def update_controls(df_json, tab):
    if not df_json: return [], None, [], []

    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except:
        df = pd.read_json(df_json, orient='split')

    filtro_tipo = "Balance" if tab == "balance" else ("Acumulado" if tab == "acumulado" else "Mensual")
    df = df[df['Tipo_Reporte'] == filtro_tipo]

    df = df.dropna(axis=1, how='all')
    columnas_disponibles = [c for c in df.columns if c not in ['Mes', 'Tipo_Reporte']]

    metric_options = [{'label': m, 'value': m} for m in columnas_disponibles]
    col_options = [{'label': c, 'value': c} for c in columnas_disponibles]

    default_metric = "Total Activo" if tab == "balance" else ("Utilidad Neta" if "Utilidad Neta" in columnas_disponibles else (columnas_disponibles[0] if columnas_disponibles else None))

    return metric_options, default_metric, col_options, []

@app.callback(
    Output('main-table', 'columns'),
    Output('main-table', 'data'),
    Output('graph-container', 'children'),
    Input('df-store', 'data'),
    Input('report-tab', 'value'),
    Input('metric-dropdown', 'value'),
    Input('chart-type', 'value'),
    Input('mes-filter', 'value'),
    Input('columns-filter', 'value'),
    Input('main-table', 'sort_by')
)
def update_views(df_json, tab, metric, chart_type, meses, cols_seleccionadas, sort_by):
    if not df_json: return [], [], html.Div('Esperando carga...', style={'textAlign': 'center', 'color': '#64748B', 'padding': '20px'})

    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except:
        df = pd.read_json(df_json, orient='split')

    filtro_tipo = "Balance" if tab == "balance" else ("Acumulado" if tab == "acumulado" else "Mensual")
    df = df[df['Tipo_Reporte'] == filtro_tipo].dropna(axis=1, how='all')
    df = df.drop('Tipo_Reporte', axis=1, errors='ignore')

    if meses and len(meses) > 0:
        df = df[df['Mes'].isin(meses)]

    if df.empty: return [], [], html.Div('Sin datos con los filtros actuales.', style={'color': '#EF4444', 'textAlign': 'center'})

    df['_sort_key'] = df['Mes'].apply(obtener_clave_orden)
    if sort_by and len(sort_by) > 0:
        col = sort_by[0]['column_id']
        asc = (sort_by[0]['direction'] == 'asc')
        df = df.sort_values('_sort_key' if col == 'Mes' else col, ascending=asc)
    else:
        df = df.sort_values('_sort_key', ascending=True)
    df = df.drop('_sort_key', axis=1)

    display_df = df.copy()
    if cols_seleccionadas:
        display_df = display_df[['Mes'] + cols_seleccionadas]
    else:
        cols_finales = display_df.columns.tolist()
        if 'Mes' in cols_finales:
            cols_finales.insert(0, cols_finales.pop(cols_finales.index('Mes')))
        display_df = display_df[cols_finales]

    columns_table = []
    for c in display_df.columns:
        if c == "Mes":
            columns_table.append({"name": c, "id": c, "type": "text"})
        elif "%" in c:
            columns_table.append({"name": c, "id": c, "type": "numeric", "format": Format(precision=2, scheme=Scheme.percentage)})
        else:
            columns_table.append({"name": c, "id": c, "type": "numeric", "format": Format(precision=2, scheme=Scheme.fixed, group=Group.yes, symbol=Symbol.yes)})

    fig = None
    if metric and metric in df.columns and not df.empty:
        df_graph = df.sort_values(by='Mes', key=lambda x: x.apply(obtener_clave_orden))
        x, y = df_graph['Mes'].tolist(), df_graph[metric].tolist()

        if chart_type == 'lines':
            fig = go.Figure(go.Scatter(x=x, y=y, mode='lines+markers', marker={'size': 9, 'color': '#C9A227', 'line': {'width': 2, 'color': '#0B2D5B'}}, line={'color':'#0B2D5B', 'width': 3}))
        else:
            fig = go.Figure(go.Bar(x=x, y=y, marker_color='#0B2D5B', marker_line_color='#C9A227', marker_line_width=1.5))

        fig.update_yaxes(tickformat='.1%' if '%' in metric else '$,')
        fig.update_layout(title={'text': f"Evolución de {metric} ({filtro_tipo})", 'font': {'size': 18, 'color': '#0B2D5B', 'family': 'Segoe UI'}}, margin={'t':50,'b':40, 'l': 60, 'r': 40}, hovermode='x unified', plot_bgcolor='#FFFFFF', paper_bgcolor='#FFFFFF', xaxis={'gridcolor': '#F1F5F9'}, yaxis={'gridcolor': '#F1F5F9'})

    graph = dcc.Graph(figure=fig, config={'displayModeBar': False}) if fig else html.Div()

    return columns_table, display_df.to_dict('records'), graph

if __name__ == '__main__':
    host = os.environ.get('DASH_HOST', '0.0.0.0')
    port = int(os.environ.get('DASH_PORT', 8050))
    print(f"Arrancando Dash en http://{host}:{port}/")
    app.run(debug=True, port=port, host=host)
