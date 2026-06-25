import base64
import io
import os
import pandas as pd
from flask import Flask
from dash import Dash, dcc, html, Input, Output, State, dash_table
from dash.dash_table.Format import Format, Scheme, Group, Symbol
import plotly.graph_objs as go

print("Iniciando servidor Dash para el dashboard web")

# ==================== CONFIGURACIÓN DEL LOGO ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PATH_DEL_LOGO = os.path.join(BASE_DIR, "logo.png")

def encode_image(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""

logo_base64 = encode_image(PATH_DEL_LOGO)

# ==================== DICCIONARIO DE MESES (ORDEN CRONOLÓGICO) ====================
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

# ==================== UTILIDADES: DETECCIÓN DE ENCABEZADO Y COLUMNAS ====================
def detectar_encabezado_y_columnas(df):
    """
    Detecta fila de encabezado (si existe) y devuelve:
    header_row_idx, col_code, col_name, mov_debe, mov_haber, sal_debe, sal_haber
    Heurísticas revisan primeras 12 filas; si no encuentra, aplica índices por defecto.
    """
    col_code = col_name = None
    mov_debe = mov_haber = None
    sal_debe = sal_haber = None
    header_row_idx = 0

    # Buscar fila de encabezado en primeras 12 filas
    for r in range(min(12, len(df))):
        row_vals = [str(x).strip().lower() for x in df.iloc[r].fillna("").astype(str).tolist()]
        row_text = " ".join(row_vals)
        if "código" in row_text or "codigo" in row_text or "nombre de la cuenta" in row_text or "nombre" in row_text:
            header_row_idx = r
            for c in range(df.shape[1]):
                cell = str(df.iat[r, c]).strip().lower()
                if cell in ["código", "codigo", "cod", "codigo cuenta", "codigo de la cuenta"]:
                    col_code = c
                if "nombre" in cell and "cuenta" in cell:
                    col_name = c
                if cell in ["cargo", "cargos", "cargo (debe)", "debe", "débito", "debito"]:
                    if mov_debe is None:
                        mov_debe = c
                    elif sal_debe is None:
                        sal_debe = c
                if cell in ["abono", "abonos", "abono (haber)", "haber", "crédito", "credito"]:
                    if mov_haber is None:
                        mov_haber = c
                    elif sal_haber is None:
                        sal_haber = c
            break

    # Heurística por contenido si no detectó encabezado
    if col_code is None or col_name is None:
        for c in range(df.shape[1]):
            sample = " ".join([str(x) for x in df.iloc[:8, c].fillna("").astype(str).tolist()]).lower()
            if any(part.strip().replace('.', '').isdigit() and len(part.strip()) >= 3 for part in sample.split()):
                if col_code is None:
                    col_code = c
            if any(k in sample for k in ['clientes', 'proveedores', 'iva', 'inventario', 'caja', 'efectivo', 'ventas']):
                if col_name is None and c != col_code:
                    col_name = c

    # Valores por defecto si faltan (compatibles con tu archivo original)
    if mov_debe is None: mov_debe = 4
    if mov_haber is None: mov_haber = 5
    if sal_debe is None: sal_debe = 6
    if sal_haber is None: sal_haber = 7
    if col_code is None: col_code = 0
    if col_name is None: col_name = 1

    return header_row_idx, col_code, col_name, mov_debe, mov_haber, sal_debe, sal_haber

# ==================== CONSTRUCCIÓN DEL CATÁLOGO (CÓDIGOS EXACTOS) ====================
def construir_catalogo(df, col_code, col_name):
    """
    Recorre df y construye diccionario {codigo: nombre} con filas que tengan código no vacío.
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

# ==================== SELECCIÓN DE CÓDIGOS EXACTOS (POR PREFIJO Y/O KEYWORDS) ====================
def seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=None, keywords=None):
    """
    Devuelve lista de códigos exactos que:
    - empiezan por alguno de los prefijos (si se pasa prefijos)
    - o cuyo nombre contiene alguna keyword (si se pasa keywords)
    Combina ambas reglas para asegurar cobertura.
    """
    res = set()
    if prefijos:
        for c in codigos_detectados:
            for p in prefijos:
                if str(c).startswith(str(p)):
                    res.add(c)
                    break
    if keywords:
        for c in codigos_detectados:
            nombre = catalogo.get(c, "").lower()
            for k in keywords:
                if k.lower() in nombre:
                    res.add(c)
                    break
    return sorted(list(res))

# ==================== SUMAS POR LISTA EXACTA ====================
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

# ==================== BÚSQUEDAS POR TEXTO (para filas de ingresos/costos/gastos) ====================
def buscar_valor_por_texto(df, texto, col_code, col_name, col_val):
    """
    Busca coincidencia exacta en código o coincidencia parcial en nombre (case-insensitive).
    Devuelve el valor en la columna col_val (ej. saldo final).
    """
    buscado_l = str(texto).strip().lower()
    for i in range(len(df)):
        codigo = str(df.iat[i, col_code]).strip().lower() if pd.notna(df.iat[i, col_code]) else ""
        nombre = str(df.iat[i, col_name]).strip().lower() if pd.notna(df.iat[i, col_name]) else ""
        if codigo == buscado_l or buscado_l in nombre:
            val = df.iat[i, col_val]
            return float(val) if pd.notna(val) and val != "" else 0.0
    return 0.0

def movimiento_neto_por_texto(df, texto, col_code, col_name, mov_debe, mov_haber, es_acreedora=False):
    buscado_l = str(texto).strip().lower()
    for i in range(len(df)):
        codigo = str(df.iat[i, col_code]).strip().lower() if pd.notna(df.iat[i, col_code]) else ""
        nombre = str(df.iat[i, col_name]).strip().lower() if pd.notna(df.iat[i, col_name]) else ""
        if codigo == buscado_l or buscado_l in nombre:
            cargo = float(df.iat[i, mov_debe]) if not pd.isna(df.iat[i, mov_debe]) else 0.0
            abono = float(df.iat[i, mov_haber]) if not pd.isna(df.iat[i, mov_haber]) else 0.0
            return (abono - cargo) if es_acreedora else (cargo - abono)
    return 0.0

# ==================== PROCESADOR PRINCIPAL DEL EXCEL ====================
def procesar_archivo_bytes(content, filename):
    header, encoded = content.split(",", 1)
    data = base64.b64decode(encoded)
    df_raw = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
    mes_nombre = os.path.splitext(os.path.basename(filename))[0]

    # Detectar encabezado y columnas
    header_row_idx, col_code, col_name, mov_debe, mov_haber, sal_debe, sal_haber = detectar_encabezado_y_columnas(df_raw)

    # Construir catálogo de cuentas (lista exacta de códigos)
    catalogo, codigos_detectados = construir_catalogo(df_raw, col_code, col_name)
    if not codigos_detectados:
        catalogo, codigos_detectados = construir_catalogo(df_raw, 0, 1)

    # Depuración: imprimir índices y muestra de catálogo (puedes comentar en producción)
    print(f"[{mes_nombre}] header_row_idx={header_row_idx}, col_code={col_code}, col_name={col_name}, mov_debe={mov_debe}, mov_haber={mov_haber}, sal_debe={sal_debe}, sal_haber={sal_haber}")
    print(f"[{mes_nombre}] códigos detectados (muestra 40): {codigos_detectados[:40]}")
    # También puedes descomentar para ver nombres:
    # print(f"[{mes_nombre}] catálogo muestra: {{k: catalogo[k] for k in list(catalogo)[:40]}}")

    # -------------------------
    # 1. ESTADO DE RESULTADOS ACUMULADO (usa columnas de saldo final)
    # -------------------------
    ingresos_acum = buscar_valor_por_texto(df_raw, "4 Ingresos", col_code, col_name, sal_haber) + buscar_valor_por_texto(df_raw, "704.04", col_code, col_name, sal_haber)
    costos_acum = buscar_valor_por_texto(df_raw, "5 Costos", col_code, col_name, sal_debe)
    gastos_gen_acum = buscar_valor_por_texto(df_raw, "6 Gastos generales", col_code, col_name, sal_debe) + buscar_valor_por_texto(df_raw, "701.10 Comisiones bancarias", col_code, col_name, sal_debe)

    utilidad_bruta_acum = ingresos_acum - costos_acum
    utilidad_operacion_acum = utilidad_bruta_acum - gastos_gen_acum

    gastos_fin_acum = buscar_valor_por_texto(df_raw, "701.01 Pérdida cambiaria", col_code, col_name, sal_debe) + buscar_valor_por_texto(df_raw, "701.04 Intereses a cargo bancario nacional", col_code, col_name, sal_debe)
    prod_fin_acum = buscar_valor_por_texto(df_raw, "702.01 Utilidad cambiaria", col_code, col_name, sal_haber)

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

    # -------------------------
    # 2. ESTADO DE RESULTADOS MENSUAL (usa columnas de movimiento: mov_debe/mov_haber)
    # -------------------------
    ingresos_mes = movimiento_neto_por_texto(df_raw, "4 Ingresos", col_code, col_name, mov_debe, mov_haber, es_acreedora=True) + movimiento_neto_por_texto(df_raw, "704.04", col_code, col_name, mov_debe, mov_haber, es_acreedora=True)
    costos_mes = movimiento_neto_por_texto(df_raw, "5 Costos", col_code, col_name, mov_debe, mov_haber, es_acreedora=False)
    gastos_gen_mes = movimiento_neto_por_texto(df_raw, "6 Gastos generales", col_code, col_name, mov_debe, mov_haber, es_acreedora=False) + movimiento_neto_por_texto(df_raw, "701.10 Comisiones bancarias", col_code, col_name, mov_debe, mov_haber, es_acreedora=False)

    utilidad_bruta_mes = ingresos_mes - costos_mes
    utilidad_operacion_mes = utilidad_bruta_mes - gastos_gen_mes

    gastos_fin_mes = movimiento_neto_por_texto(df_raw, "701.01 Pérdida cambiaria", col_code, col_name, mov_debe, mov_haber, es_acreedora=False) + movimiento_neto_por_texto(df_raw, "701.04 Intereses a cargo bancario nacional", col_code, col_name, mov_debe, mov_haber, es_acreedora=False)
    prod_fin_mes = movimiento_neto_por_texto(df_raw, "702.01 Utilidad cambiaria", col_code, col_name, mov_debe, mov_haber, es_acreedora=True)

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

    # -------------------------
    # 3. BALANCE (USANDO LISTA EXACTA + MATCH POR NOMBRE PARA COMPLETAR)
    # -------------------------
    # Reglas para seleccionar códigos exactos: combinamos prefijos y keywords por nombre para asegurar cobertura.
    codigos_efectivo = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['101', '102'], keywords=['caja', 'efectivo', 'banco'])
    codigos_cxc = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['105'], keywords=['clientes', 'cuentas por cobrar'])
    codigos_inventarios = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['115'], keywords=['inventario', 'mercancías', 'mercancias'])
    codigos_imp_recuperar = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['113', '114', '118', '119'], keywords=['iva', 'pagos provisionales', 'iva acreditable', 'iva pendiente'])
    codigos_otras_cxc = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['107'], keywords=['otros deudores', 'deudores diversos', 'funcionarios', 'empleados', 'toka'])

    efectivo = obtener_saldo_por_catalogo_exacto(df_raw, codigos_efectivo, col_code, sal_debe, sal_haber, es_acreedora=False)
    cxc = obtener_saldo_por_catalogo_exacto(df_raw, codigos_cxc, col_code, sal_debe, sal_haber, es_acreedora=False)
    inventarios = obtener_saldo_por_catalogo_exacto(df_raw, codigos_inventarios, col_code, sal_debe, sal_haber, es_acreedora=False)
    imp_recuperar = obtener_saldo_por_catalogo_exacto(df_raw, codigos_imp_recuperar, col_code, sal_debe, sal_haber, es_acreedora=False)
    otras_cxc = obtener_saldo_por_catalogo_exacto(df_raw, codigos_otras_cxc, col_code, sal_debe, sal_haber, es_acreedora=False)

    activo_circulante = efectivo + cxc + inventarios + imp_recuperar + otras_cxc

    # Activo fijo
    codigos_eq_computo = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['154', '156'], keywords=['equipo de cómputo', 'laptop', 'computo'])
    codigos_depreciacion = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['171'], keywords=['depreciacion', 'depreciación', 'depre'])

    eq_computo = obtener_saldo_por_catalogo_exacto(df_raw, codigos_eq_computo, col_code, sal_debe, sal_haber, es_acreedora=False)
    depreciacion = obtener_saldo_por_catalogo_exacto(df_raw, codigos_depreciacion, col_code, sal_debe, sal_haber, es_acreedora=False)
    activo_fijo = eq_computo + depreciacion

    total_activo = activo_circulante + activo_fijo

    # Pasivos
    codigos_proveedores = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['201'], keywords=['proveedores'])
    codigos_impuestos = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['208', '209', '213', '216'], keywords=['iva trasladado', 'iva por pagar', 'isr', 'retencion'])
    codigos_otros_pasivos = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['205', '206', '210'], keywords=['acreedores', 'anticipo', 'provision'])

    proveedores = obtener_saldo_por_catalogo_exacto(df_raw, codigos_proveedores, col_code, sal_debe, sal_haber, es_acreedora=True)
    imp_pagar = obtener_saldo_por_catalogo_exacto(df_raw, codigos_impuestos, col_code, sal_debe, sal_haber, es_acreedora=True)
    otros_pasivos = obtener_saldo_por_catalogo_exacto(df_raw, codigos_otros_pasivos, col_code, sal_debe, sal_haber, es_acreedora=True)

    pasivo_circulante = proveedores + imp_pagar + otros_pasivos

    # Capital contable
    codigos_capital_social = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['301'], keywords=['capital'])
    codigos_resultados_acum = seleccionar_codigos_exactos(codigos_detectados, catalogo, prefijos=['304'], keywords=['utilidad', 'pérdida', 'perdida', 'resultados acumulados'])

    capital_social = obtener_saldo_por_catalogo_exacto(df_raw, codigos_capital_social, col_code, sal_debe, sal_haber, es_acreedora=True)
    res_acumulados = obtener_saldo_por_catalogo_exacto(df_raw, codigos_resultados_acum, col_code, sal_debe, sal_haber, es_acreedora=True)

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

# ==================== APP Dash (interfaz original preservada) ====================
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
    # HEADER
    html.Div([
        html.Div([
            html.Img(src=f"data:image/png;base64,{logo_base64}" if logo_base64 else "", style={'height': '60px', 'marginRight': '20px', 'display': 'inline-block' if logo_base64 else 'none', 'backgroundColor': 'white', 'padding': '5px', 'borderRadius': '6px'}),
            html.Div([
                html.H2("REPORTE FINANCIERO INTEGRAL 2026", style={'color': '#FFFFFF', 'margin': '0', 'fontWeight': '700', 'fontSize': '26px', 'letterSpacing': '0.5px'}),
                html.Div("Resultados y Posición Financiera (Balance General)", style={'color': '#C9A227', 'fontSize': '13px', 'fontWeight': '5px', 'marginTop': '2px'})
            ], style={'display': 'inline-block', 'verticalAlign': 'middle'})
        ], style={'display': 'flex', 'alignItems': 'center'})
    ], style={'background': 'linear-gradient(135deg, #0B2D5B 0%, #1E3A61 100%)', 'padding': '20px 30px', 'borderRadius': '0px 0px 15px 15px', 'boxShadow': '0 4px 6px -1px rgba(0,0,0,0.1)', 'marginBottom': '25px', 'borderBottom': '4px solid #C9A227'}),

    # ZONA DE CARGA
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

    # FILTROS Y CONTROLES
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

    # PESTAÑAS
    dcc.Tabs(id='report-tab', value='acumulado', children=[
        dcc.Tab(label='Estado de Resultados Acumulado', value='acumulado', style=estilo_tab, selected_style=estilo_tab_seleccionada),
        dcc.Tab(label='Estado de Resultados Mensual', value='mensual', style=estilo_tab, selected_style=estilo_tab_seleccionada),
        dcc.Tab(label='Balance General', value='balance', style=estilo_tab, selected_style=estilo_tab_seleccionada)
    ], style={'margin': '0 15px'}),

    # CONTENEDOR TABLA Y GRÁFICO
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

    # Forzar orden de columnas: Mes y Tipo_Reporte al inicio
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
