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
 
 
# ==================== CATÁLOGO EXACTO PARA BALANCE ====================
CATALOGO_BALANCE = {
    'Efectivo': ['101.01.002', '102.01.001', '102.01.002'], 
    'Cuentas_por_Cobrar': ['105.01.001'],
    'Inventarios': ['115.01.001', '115.01.002', '115.01.003'], 
    'Impuestos_por_Recuperar': ['113.01.001', '114.01.001', '118.01.001', '119.01.001', '119.01.003'],
    
    # SE ACTUALIZAN CON LOS CÓDIGOS ESPECÍFICOS QUE COMPONEN TUS GRUPOS
    'Otras_CxC_Grupos': ['107.01', '107.05', '120.01', '184.01', '899.01'], 
    
    'Equipo_de_Computo': ['154.01.001', '154.01.002', '156.01.001'],
    'Depreciacion_Acumulada': ['171.03.001', '171.03.002', '171.05.001'],
    
    'Proveedores': ['201.01.001'],
    'Acreedores_Diversos': ['201.03.001', '205.02.001', '205.06.002'],
    'Impuestos_por_Pagar': [
        '208.01.001', '209.01.001', '209.01.002', '213.01.001', 
        '213.03.001', '216.01.001', '216.04.001', '216.05.001', 
        '216.10.001', '216.10.002', '216.11.001', '216.12.001', '216.12.002'
    ],
    'Otros_Pasivos': ['206.01.001', '210.01.001'],
    
    'Capital_Social': ['301.01.001'],
    'Resultados_Acumulados_Grupos': ['304.01', '304.02'] 
}
 
# ---------------------- LÓGICA DE PROCESAMIENTO CONTABLE ----------------------
 
def obtener_valor(df, cuenta, columna):
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if valor_cuenta.lower() == cuenta.lower():
            valor = df.iat[i, columna]
            if pd.isna(valor): return 0.0
            return float(valor)
    return 0.0
 
def obtener_704_04(df, columna):
    texto_busqueda = "704.04"
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if texto_busqueda in valor_cuenta:
            valor = df.iat[i, columna]
            if pd.isna(valor): return 0.0
            return float(valor)
    return 0.0
 
def obtener_movimiento_neto(df, cuenta, es_acreedora=False):
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if valor_cuenta.lower() == cuenta.lower():
            cargo = float(df.iat[i, 4]) if not pd.isna(df.iat[i, 4]) else 0.0
            abono = float(df.iat[i, 5]) if not pd.isna(df.iat[i, 5]) else 0.0
            return (abono - cargo) if es_acreedora else (cargo - abono)
    return 0.0
 
def obtener_704_04_neto(df, es_acreedora=False):
    texto_busqueda = "704.04"
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if texto_busqueda in valor_cuenta:
            cargo = float(df.iat[i, 4]) if not pd.isna(df.iat[i, 4]) else 0.0
            abono = float(df.iat[i, 5]) if not pd.isna(df.iat[i, 5]) else 0.0
            return (abono - cargo) if es_acreedora else (cargo - abono)
    return 0.0
 
def obtener_saldo_exacto(df, lista_codigos_exactos, es_acreedora=False):
    total_debe = 0.0
    total_haber = 0.0
    for i in range(len(df)):
        codigo = str(df.iat[i, 0]).strip()
        if codigo in lista_codigos_exactos:
            debe = df.iat[i, 6]
            haber = df.iat[i, 7]
            if pd.notna(debe) and isinstance(debe, (int, float)): total_debe += float(debe)
            if pd.notna(haber) and isinstance(haber, (int, float)): total_haber += float(haber)
                
    return (total_haber - total_debe) if es_acreedora else (total_debe - total_haber)
 
# --- NUEVAS FUNCIONES ESPECÍFICAS SOLICITADAS POR EL USUARIO ---
 
def calcular_otras_cuentas_cobrar(df, grupos):
    """
    Suma columna G (Débito Final) y resta columna H (Crédito Final)
    buscando la coincidencia exacta de que el código empiece con los grupos.
    """
    total = 0.0
    for i in range(len(df)):
        codigo = str(df.iat[i, 0]).strip()
        # Verificamos si la cuenta pertenece a alguno de los grupos dados (ej. 107.01)
        if pd.notna(df.iat[i, 0]) and codigo != 'nan' and codigo != '':
            if any(codigo.startswith(grupo) for grupo in grupos):
                g_debito = df.iat[i, 6]
                h_credito = df.iat[i, 7]
                
                g_val = float(g_debito) if pd.notna(g_debito) and isinstance(g_debito, (int, float)) else 0.0
                h_val = float(h_credito) if pd.notna(h_credito) and isinstance(h_credito, (int, float)) else 0.0
                
                # Fórmula exacta solicitada: Suma G, Resta H (+ G - H)
                total += (g_val - h_val)
    return total
 
def obtener_compras_acum(df):
    # Compras = movimiento Credito (indice 5) de la cuenta/totalizador 201.01
    # Se busca en col[0] (código) Y en col[1] (nombre) para cubrir ambos formatos
    total = 0.0
    for i in range(len(df)):
        codigo = str(df.iat[i, 0]).strip()
        nombre = str(df.iat[i, 1]).strip()
        # Coincide si el código ES exactamente '201.01' o empieza con '201.01.'
        # o si el nombre empieza con '201.01' (totalizador de grupo)
        if (codigo == '201.01' or codigo.startswith('201.01.') or nombre.startswith('201.01')):
            v = df.iat[i, 5]  # col F = movimiento crédito del período
            if pd.notna(v) and isinstance(v, (int, float)):
                total += float(v)
    return total
 
 
def calcular_resultados_acumulados(df, grupos):
    """
    Lógica exacta para Resultados Acumulados:
    - Fila de grupo '304.01 ...' (col B empieza con '304.01'): suma H (col[7]), resta G (col[6])
    - Fila de grupo '304.02 ...' (col B empieza con '304.02'): suma H (col[7]), resta G (col[6])
    - Fila 'GANANCIAS/PERDIDAS NO DISTRIBUIDAS' (col B): resta H (col[7])
    Se busca por nombre en col[1] porque estas son filas de totalizadores de grupo
    (no tienen código propio en col[0]).
    """
    total = 0.0
 
    for i in range(len(df)):
        nombre = str(df.iat[i, 1]).strip().upper()
        nombre_raw = str(df.iat[i, 1]).strip()
 
        def _g(): 
            v = df.iat[i, 6]
            return float(v) if pd.notna(v) and isinstance(v, (int, float)) else 0.0
        def _h():
            v = df.iat[i, 7]
            return float(v) if pd.notna(v) and isinstance(v, (int, float)) else 0.0
 
        # Totalizador del grupo 304.01 (formato: "304.01 Utilidad de ejercicios anteriores")
        if nombre_raw.startswith('304.01'):
            total += (_h() - _g())
 
        # Totalizador del grupo 304.02 (formato: "304.02 Pérdida de ejercicios anteriores")
        elif nombre_raw.startswith('304.02'):
            total += (_h() - _g())
 
        # GANANCIAS/PERDIDAS NO DISTRIBUIDAS — no se toma en cuenta
 
    return total
 
 
# --- Días acumulados por mes (para indicadores) ---
def _dias_acumulados(mes_nombre):
    DIAS_MES = {
        'ENERO': 30, 'FEBRERO': 60, 'MARZO': 90, 'ABRIL': 120,
        'MAYO': 150, 'JUNIO': 180, 'JULIO': 210, 'AGOSTO': 240,
        'SEPTIEMBRE': 270, 'OCTUBRE': 300, 'NOVIEMBRE': 330, 'DICIEMBRE': 360
    }
    partes = str(mes_nombre).upper().split()
    return DIAS_MES.get(partes[0], 30) if partes else 30
 
 
# --- Procesador Principal del Excel ---
def procesar_archivo_bytes(content, filename):
    header, encoded = content.split(",", 1)
    data = base64.b64decode(encoded)
    df = pd.read_excel(io.BytesIO(data), header=None)
    mes_nombre = os.path.splitext(os.path.basename(filename))[0]
 
    # ==========================================
    # 1. ESTADO DE RESULTADOS (ACUMULADO)
    # ==========================================
    ingresos_acum = obtener_valor(df, "4 Ingresos", 7) + obtener_704_04(df, 7)
    costos_acum = obtener_valor(df, "5 Costos", 6)
    gastos_gen_acum = obtener_valor(df, "6 Gastos generales", 6) + obtener_valor(df, "701.10 Comisiones bancarias", 6)
    
    utilidad_bruta_acum = ingresos_acum - costos_acum
    utilidad_operacion_acum = utilidad_bruta_acum - gastos_gen_acum
    
    gastos_fin_acum = obtener_valor(df, "701.01 Pérdida cambiaria", 6) + obtener_valor(df, "701.04 Intereses a cargo bancario nacional", 6)
    prod_fin_acum = obtener_valor(df, "702.01 Utilidad cambiaria", 7)
    
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
 
    # ==========================================
    # 2. ESTADO DE RESULTADOS (MENSUAL)
    # ==========================================
    ingresos_mes = obtener_movimiento_neto(df, "4 Ingresos", es_acreedora=True) + obtener_704_04_neto(df, es_acreedora=True)
    costos_mes = obtener_movimiento_neto(df, "5 Costos", es_acreedora=False)
    gastos_gen_mes = obtener_movimiento_neto(df, "6 Gastos generales", es_acreedora=False) + obtener_movimiento_neto(df, "701.10 Comisiones bancarias", es_acreedora=False)
    
    utilidad_bruta_mes = ingresos_mes - costos_mes
    utilidad_operacion_mes = utilidad_bruta_mes - gastos_gen_mes
    
    gastos_fin_mes = obtener_movimiento_neto(df, "701.01 Pérdida cambiaria", es_acreedora=False) + obtener_movimiento_neto(df, "701.04 Intereses a cargo bancario nacional", es_acreedora=False)
    prod_fin_mes = obtener_movimiento_neto(df, "702.01 Utilidad cambiaria", es_acreedora=True)
    
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
 
    # ==========================================
    # 3. BALANCE GENERAL (POSICIÓN FINANCIERA)
    # ==========================================
    efectivo = obtener_saldo_exacto(df, CATALOGO_BALANCE['Efectivo'])
    cxc = obtener_saldo_exacto(df, CATALOGO_BALANCE['Cuentas_por_Cobrar'])
    inventarios = obtener_saldo_exacto(df, CATALOGO_BALANCE['Inventarios'])
    imp_recuperar = obtener_saldo_exacto(df, CATALOGO_BALANCE['Impuestos_por_Recuperar'])
    
    # -----------------------------------------------------
    # LÓGICAS NUEVAS APLICADAS AQUÍ:
    # -----------------------------------------------------
    otras_cxc = calcular_otras_cuentas_cobrar(df, CATALOGO_BALANCE['Otras_CxC_Grupos'])
    res_acumulados = calcular_resultados_acumulados(df, CATALOGO_BALANCE['Resultados_Acumulados_Grupos'])
    
    activo_circulante = efectivo + cxc + inventarios + imp_recuperar + otras_cxc
    
    eq_computo = obtener_saldo_exacto(df, CATALOGO_BALANCE['Equipo_de_Computo'])
    depreciacion = obtener_saldo_exacto(df, CATALOGO_BALANCE['Depreciacion_Acumulada']) 
    activo_fijo = eq_computo + depreciacion
    total_activo = activo_circulante + activo_fijo
 
    proveedores = obtener_saldo_exacto(df, CATALOGO_BALANCE['Proveedores'], es_acreedora=True)
    acreedores_diversos = obtener_saldo_exacto(df, CATALOGO_BALANCE['Acreedores_Diversos'], es_acreedora=True)
    imp_pagar = obtener_saldo_exacto(df, CATALOGO_BALANCE['Impuestos_por_Pagar'], es_acreedora=True)
    otros_pasivos = obtener_saldo_exacto(df, CATALOGO_BALANCE['Otros_Pasivos'], es_acreedora=True)
    pasivo_circulante = proveedores + acreedores_diversos + imp_pagar + otros_pasivos
    
    capital_social = obtener_saldo_exacto(df, CATALOGO_BALANCE['Capital_Social'], es_acreedora=True)
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
        "Acreedores Diversos": acreedores_diversos, "% Acreedores Div.": acreedores_diversos/total_pasivo_capital if total_pasivo_capital else 0,
        "Impuestos por Pagar": imp_pagar, "% Imp. Pagar": imp_pagar/total_pasivo_capital if total_pasivo_capital else 0,
        "Otros Pasivos": otros_pasivos, "% Otros Pasivos": otros_pasivos/total_pasivo_capital if total_pasivo_capital else 0,
        "Total Pasivo": pasivo_circulante, "% Total Pasivo": pasivo_circulante/total_pasivo_capital if total_pasivo_capital else 0,
        "Capital Social": capital_social,
        "Resultados Acumulados": res_acumulados,
        "Utilidad del Ejercicio": utilidad_ejercicio,
        "Total Capital": capital_contable, "% Total Capital": capital_contable/total_pasivo_capital if total_pasivo_capital else 0,
        "Total Pasivo y Capital": total_pasivo_capital
    }
 
    # ==========================================
    # 4. VALORES CRUDOS PARA INDICADORES
    # Los indicadores finales se calculan en handle_upload donde
    # tenemos todos los meses disponibles para promedios acumulados.
    # ==========================================
    compras_mes = obtener_compras_acum(df)  # compras del mes (col F de 201.01)
 
    data_indicadores_raw = {
        'Mes': mes_nombre, 'Tipo_Reporte': '_IndRaw',
        '_cxc':           cxc,
        '_inventarios':   inventarios,
        '_activo_circ':   activo_circulante,
        '_total_activo':  total_activo,
        '_pasivo':        pasivo_circulante,
        '_ingresos_acum': ingresos_acum,
        '_costos_acum':   costos_acum,
        '_compras_mes':   compras_mes,
    }
 
    return data_acumulada, data_mensual, data_balance, data_indicadores_raw
 
 
# ---------------------- APP Dash ----------------------
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
        /* Celda de dinero: $ a la izquierda, número a la derecha, igual que Excel */
        .dash-cell div { overflow: hidden; }
        .dash-cell div span { display: inline; }
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
                html.H2("REPORTE FINANCIERO INTEGRAL", style={'color': '#FFFFFF', 'margin': '0', 'fontWeight': '700', 'fontSize': '26px', 'letterSpacing': '0.5px'}),
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
            html.Label('Conceptos Visibles', style={'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px', 'display': 'block'}), 
            dcc.Dropdown(id='columns-filter', multi=True, placeholder='Todos los conceptos', value=[])
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
 
    # PESTAÑAS PRINCIPALES
    dcc.Tabs(id='report-tab', value='acumulado', children=[
        dcc.Tab(label='Estado de Resultados Acumulado', value='acumulado', style=estilo_tab, selected_style=estilo_tab_seleccionada),
        dcc.Tab(label='Estado de Resultados Mensual', value='mensual', style=estilo_tab, selected_style=estilo_tab_seleccionada),
        dcc.Tab(label='Balance General', value='balance', style=estilo_tab, selected_style=estilo_tab_seleccionada),
        dcc.Tab(label='Indicadores Financieros', value='indicadores', style=estilo_tab, selected_style=estilo_tab_seleccionada)
    ], style={'margin': '0 15px'}),
 
    # SUB-SECCIONES DEL BALANCE — selección múltiple con botones toggle
    html.Div(id='balance-subtabs-container', children=[
        html.Div([
            html.Label('Secciones del Balance:', style={'fontWeight': '700', 'color': '#0B2D5B', 'marginRight': '12px', 'fontSize': '13px'}),
            dcc.Checklist(
                id='balance-subtab',
                options=[
                    {'label': '  Activo Circulante',  'value': 'activo_circulante'},
                    {'label': '  Activo Fijo',         'value': 'activo_fijo'},
                    {'label': '  Pasivo Circulante',   'value': 'pasivo_circulante'},
                    {'label': '  Capital Contable',    'value': 'capital_contable'},
                ],
                value=['activo_circulante'],
                inline=True,
                inputStyle={'marginRight': '5px', 'accentColor': '#0B2D5B'},
                labelStyle={
                    'marginRight': '16px', 'padding': '8px 16px',
                    'backgroundColor': '#F1F5F9', 'borderRadius': '20px',
                    'border': '1.5px solid #CBD5E1', 'cursor': 'pointer',
                    'fontWeight': '600', 'fontSize': '13px', 'color': '#334155',
                    'display': 'inline-flex', 'alignItems': 'center'
                },
            )
        ], style={
            'margin': '8px 15px 0 15px', 'padding': '14px 20px',
            'background': '#FFFFFF', 'borderRadius': '10px',
            'boxShadow': '0 1px 3px rgba(0,0,0,0.05)',
            'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '6px'
        })
    ], style={'display': 'none'}),
 
    # CONTENEDOR TABLA Y GRÁFICO
    html.Div([
        html.Div(
            style={'width': '100%', 'marginBottom': '25px', 'background': '#FFFFFF', 'borderRadius': '0px 0px 12px 12px', 'padding': '20px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.05)', 'borderTop': '1px solid #E2E8F0'},
            children=[
                dash_table.DataTable(
                    id='main-table', page_size=50,
                    fixed_columns={'headers': True, 'data': 1},
                    fixed_rows={'headers': True},
                    markdown_options={"html": True},
                    style_table={'width':'100%', 'minWidth':'100%', 'overflowX':'auto', 'maxHeight':'600px', 'overflowY':'auto'},
                    style_cell={
                        'textAlign':'left', 'padding':'10px 14px',
                        'minWidth':'165px', 'width':'165px', 'maxWidth':'165px',
                        'fontFamily': 'Segoe UI, sans-serif', 'fontSize': '13px',
                        'fontWeight': '700', 'color': '#1E293B',
                        'border': '1px solid #E2E8F0', 'whiteSpace': 'nowrap',
                        'overflow': 'hidden'
                    },
                    style_cell_conditional=[
                        {'if':{'column_id':'Concepto'},
                         'textAlign':'left', 'fontWeight':'800',
                         'color': '#0B2D5B', 'backgroundColor': '#F8FAFC',
                         'minWidth':'230px', 'width':'230px', 'maxWidth':'230px'},
                    ],
                    style_header={
                        'backgroundColor':'#0B2D5B', 'color':'white',
                        'fontWeight':'700', 'textAlign':'center',
                        'border': '1px solid #0B2D5B', 'fontSize': '13px'
                    },
                    style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#F8FAFC'}],
                    sort_action='custom', sort_mode='single', sort_by=[], page_action='native'
                )
            ]
        ),
        html.Div(id='graph-container', style={'width': '100%', 'background': '#FFFFFF', 'borderRadius': '12px', 'padding': '15px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.05)'})
    ], style={'padding': '0 15px'}),
 
    # PANEL DE COMPARACIÓN MENSUAL (solo visible en pestaña Mensual)
    html.Div(id='comparacion-container', children=[
        html.Div([
            # Título del panel
            html.Div([
                html.Span('⚖️', style={'fontSize': '20px', 'marginRight': '10px'}),
                html.Span('Comparación entre Meses', style={
                    'fontWeight': '700', 'fontSize': '16px', 'color': '#0B2D5B'
                })
            ], style={'marginBottom': '16px', 'display': 'flex', 'alignItems': 'center'}),
 
            # Selectores de mes A y mes B
            html.Div([
                html.Div([
                    html.Label('Mes Base', style={
                        'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px',
                        'display': 'block', 'fontSize': '13px'
                    }),
                    dcc.Dropdown(id='comp-mes-a', placeholder='Selecciona mes base...',
                                 clearable=False,
                                 style={'fontWeight': '600'})
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '3%'}),
 
                html.Div([
                    html.Label('Mes a Comparar', style={
                        'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px',
                        'display': 'block', 'fontSize': '13px'
                    }),
                    dcc.Dropdown(id='comp-mes-b', placeholder='Selecciona mes a comparar...',
                                 clearable=False,
                                 style={'fontWeight': '600'})
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '3%'}),
 
                html.Div([
                    html.Label(' ', style={'display': 'block', 'marginBottom': '6px'}),
                    html.Button('Comparar', id='btn-comparar',
                        style={
                            'backgroundColor': '#0B2D5B', 'color': 'white',
                            'border': 'none', 'borderRadius': '8px',
                            'padding': '10px 28px', 'fontWeight': '700',
                            'fontSize': '14px', 'cursor': 'pointer',
                            'boxShadow': '0 2px 4px rgba(0,0,0,0.15)'
                        })
                ], style={'width': '15%', 'display': 'inline-block', 'verticalAlign': 'bottom'}),
            ], style={'marginBottom': '20px'}),
 
            # Resultado de comparación
            html.Div(id='comparacion-resultado')
 
        ], style={
            'background': '#FFFFFF', 'borderRadius': '12px',
            'padding': '24px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.07)',
            'border': '1.5px solid #E2E8F0'
        })
    ], style={'padding': '20px 15px 0 15px', 'display': 'none'}),
 
    # PANEL DE COMPARACIÓN BALANCE (solo visible en pestaña Balance)
    html.Div(id='comp-balance-container', children=[
        html.Div([
            html.Div([
                html.Span('⚖️', style={'fontSize': '20px', 'marginRight': '10px'}),
                html.Span('Comparación entre Meses — Balance General', style={
                    'fontWeight': '700', 'fontSize': '16px', 'color': '#0B2D5B'
                })
            ], style={'marginBottom': '16px', 'display': 'flex', 'alignItems': 'center'}),
 
            html.Div([
                html.Div([
                    html.Label('Mes Base', style={
                        'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px',
                        'display': 'block', 'fontSize': '13px'
                    }),
                    dcc.Dropdown(id='comp-bal-mes-a', placeholder='Selecciona mes base...',
                                 clearable=False, style={'fontWeight': '600'})
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '3%'}),
 
                html.Div([
                    html.Label('Mes a Comparar', style={
                        'fontWeight': '600', 'color': '#1E293B', 'marginBottom': '6px',
                        'display': 'block', 'fontSize': '13px'
                    }),
                    dcc.Dropdown(id='comp-bal-mes-b', placeholder='Selecciona mes a comparar...',
                                 clearable=False, style={'fontWeight': '600'})
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '3%'}),
 
                html.Div([
                    html.Label(' ', style={'display': 'block', 'marginBottom': '6px'}),
                    html.Button('Comparar', id='btn-comp-balance',
                        style={
                            'backgroundColor': '#0B2D5B', 'color': 'white',
                            'border': 'none', 'borderRadius': '8px',
                            'padding': '10px 28px', 'fontWeight': '700',
                            'fontSize': '14px', 'cursor': 'pointer',
                            'boxShadow': '0 2px 4px rgba(0,0,0,0.15)'
                        })
                ], style={'width': '15%', 'display': 'inline-block', 'verticalAlign': 'bottom'}),
            ], style={'marginBottom': '20px'}),
 
            html.Div(id='comp-balance-resultado')
 
        ], style={
            'background': '#FFFFFF', 'borderRadius': '12px',
            'padding': '24px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.07)',
            'border': '1.5px solid #E2E8F0'
        })
    ], style={'padding': '20px 15px 0 15px', 'display': 'none'}),
 
    dcc.Store(id='df-store')
], style={'width':'100%', 'maxWidth':'100%', 'margin':'0', 'boxSizing': 'border-box'})
 
 
# ==================== MAPEO DE SECCIONES DEL BALANCE ====================
BALANCE_SECCIONES = {
    'activo_circulante': [
        'Efectivo', '% Efectivo',
        'Cuentas por Cobrar', '% Cuentas x Cobrar',
        'Inventarios', '% Inventarios',
        'Impuestos por Recuperar', '% Imp. Recuperar',
        'Otras Cuentas x Cobrar', '% Otras CxC',
        'Total Activo Circulante', '% Act. Circulante',
    ],
    'activo_fijo': [
        'Equipo de Cómputo',
        'Depreciación Acumulada',
        'Total Activo Fijo', '% Act. Fijo',
        'Total Activo',
    ],
    'pasivo_circulante': [
        'Proveedores', '% Proveedores',
        'Acreedores Diversos', '% Acreedores Div.',
        'Impuestos por Pagar', '% Imp. Pagar',
        'Otros Pasivos', '% Otros Pasivos',
        'Total Pasivo', '% Total Pasivo',
    ],
    'capital_contable': [
        'Capital Social',
        'Resultados Acumulados',
        'Utilidad del Ejercicio',
        'Total Capital', '% Total Capital',
        'Total Pasivo y Capital',
    ],
}
 
# ---------------------- CALLBACKS ----------------------
 
@app.callback(
    Output('balance-subtabs-container', 'style'),
    Input('report-tab', 'value')
)
def toggle_balance_subtabs(tab):
    if tab == 'balance':
        return {'display': 'block'}
    return {'display': 'none'}
 
 
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
            acum, mens, bal, ind = procesar_archivo_bytes(content, name)
            resultados.extend([acum, mens, bal, ind])
        except Exception as e:
            return None, html.Div(f"Error procesando {name}: {e}", style={'color': '#EF4444'}), []
 
    df_raw = pd.DataFrame(resultados)
 
    # ── Recalcular indicadores con promedios acumulados ──────────────────────
    # Extraer filas crudas y ordenar por mes
    raw = df_raw[df_raw['Tipo_Reporte'] == '_IndRaw'].copy()
    raw_sorted = raw.sort_values('Mes', key=lambda s: s.map(
        lambda m: obtener_clave_orden(m)
    )).reset_index(drop=True)
 
    indicadores_finales = []
    hist_cxc  = []   # saldo CxC de cada mes (para PROMEDIO)
    hist_inv  = []   # saldo Inventarios de cada mes (para PROMEDIO)
    hist_prov = []   # saldo Proveedores de cada mes (para PROMEDIO)
    hist_comp = []   # compras de cada mes (para SUMA acumulada)
 
    # Días por mes — tabla fija según el Excel
    DIAS_POR_MES = {
        'ENERO': 30, 'FEBRERO': 60, 'MARZO': 90, 'ABRIL': 120,
        'MAYO': 150, 'JUNIO': 180, 'JULIO': 210, 'AGOSTO': 240,
        'SEPTIEMBRE': 270, 'OCTUBRE': 300, 'NOVIEMBRE': 330, 'DICIEMBRE': 360
    }
 
    for _, row in raw_sorted.iterrows():
        mes        = row['Mes']
        cxc_val    = float(row['_cxc'])          if pd.notna(row['_cxc'])         else 0.0
        inv_val    = float(row['_inventarios'])   if pd.notna(row['_inventarios']) else 0.0
        act_circ   = float(row['_activo_circ'])   if pd.notna(row['_activo_circ']) else 0.0
        tot_activo = float(row['_total_activo'])  if pd.notna(row['_total_activo'])else 0.0
        pasivo     = float(row['_pasivo'])        if pd.notna(row['_pasivo'])      else 0.0
        ing_acum   = float(row['_ingresos_acum']) if pd.notna(row['_ingresos_acum'])else 0.0
        cos_acum   = float(row['_costos_acum'])   if pd.notna(row['_costos_acum']) else 0.0
        comp_mes   = float(row['_compras_mes'])   if pd.notna(row['_compras_mes']) else 0.0
 
        # Acumular histórico
        hist_cxc.append(cxc_val)
        hist_inv.append(inv_val)
        hist_prov.append(pasivo)
        hist_comp.append(comp_mes)
 
        # Días del período según el mes (tabla fija del Excel)
        mes_upper = str(mes).upper().split()[0]  # ej: "ENERO" de "Enero 2026"
        dias_n    = DIAS_POR_MES.get(mes_upper, len(hist_cxc) * 30)
 
        n         = len(hist_cxc)
        prom_cxc  = sum(hist_cxc)  / n   # AVERAGE(CxC de ene..mes actual)
        prom_inv  = sum(hist_inv)  / n   # AVERAGE(Inventarios de ene..mes actual)
        prom_prov = sum(hist_prov) / n   # AVERAGE(Proveedores de ene..mes actual)
        sum_comp  = sum(hist_comp)        # SUM(Compras de ene..mes actual)
 
        # Fórmulas exactas del Excel (todas referenciadas a Balance (2)):
        # Capital de trabajo  : f13 - f29  = Activo Circ - Total Pasivo
        # Razón circulante    : f20 / f29  = Total Activo / Total Pasivo
        # Prueba ácida        : (f13 - f9) / f29 = (Activo Circ - Inv) / Pasivo
        # Razón endeudamiento : f29 / f20  = Total Pasivo / Total Activo
        # Días CxC  : AVERAGE(CxC meses) / Ingresos_acum  × días_n
        # Días CxP  : AVERAGE(Proveedores) / SUM(Compras) × días_n
        # Rot. inv  : AVERAGE(Inventarios) / Costos_acum   × días_n
        # Ciclo     : Días CxC - Días CxP + Rot. inv
        capital_trabajo     = act_circ - pasivo
        razon_circulante    = tot_activo / pasivo           if pasivo     else 0
        prueba_acida        = (act_circ - inv_val) / pasivo if pasivo     else 0
        razon_endeudamiento = pasivo / tot_activo            if tot_activo else 0
        dias_cxc            = (prom_cxc  / ing_acum * dias_n) if ing_acum  else 0
        dias_cxp            = (prom_prov / sum_comp * dias_n) if sum_comp  else 0
        rotacion_inv        = (prom_inv  / cos_acum * dias_n) if cos_acum  else 0
        ciclo_efectivo      = dias_cxc - dias_cxp + rotacion_inv
 
        indicadores_finales.append({
            'Mes': mes, 'Tipo_Reporte': 'Indicadores',
            'Capital de Trabajo':     capital_trabajo,
            'Razón Circulante':       razon_circulante,
            'Prueba Ácida':           prueba_acida,
            'Razón de Endeudamiento': razon_endeudamiento,
            'Días CxC':               dias_cxc,
            'Días CxP':               dias_cxp,
            'Rotación de Inventario': rotacion_inv,
            'Ciclo del Efectivo':     ciclo_efectivo,
        })
 
    # Reemplazar filas _IndRaw con los indicadores calculados correctamente
    df_sin_raw = df_raw[df_raw['Tipo_Reporte'] != '_IndRaw']
    df_ind     = pd.DataFrame(indicadores_finales)
    df         = pd.concat([df_sin_raw, df_ind], ignore_index=True)
 
    # REORDENAMIENTO MAESTRO
    cols = df.columns.tolist()
    if 'Mes' in cols:
        cols.insert(0, cols.pop(cols.index('Mes')))
    if 'Tipo_Reporte' in cols:
        cols.insert(0, cols.pop(cols.index('Tipo_Reporte')))
    df = df[cols]
 
    meses_unicos = sorted(df['Mes'].unique(), key=obtener_clave_orden)
    mes_options  = [{'label': m, 'value': m} for m in meses_unicos]
 
    status_msg = html.Div(
        f'✓ {len(valid_files)} archivos procesados con éxito. Balance calculado con reglas actualizadas.',
        style={'color': '#10B981', 'padding': '10px 0'}
    )
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
        
    filtro_tipo = "Balance" if tab == "balance" else ("Acumulado" if tab == "acumulado" else ("Mensual" if tab == "mensual" else "Indicadores"))
    df = df[df['Tipo_Reporte'] == filtro_tipo]
    
    df = df.dropna(axis=1, how='all')
    columnas_disponibles = [c for c in df.columns if c not in ['Mes', 'Tipo_Reporte']]
    
    metric_options = [{'label': m, 'value': m} for m in columnas_disponibles]
    col_options = [{'label': c, 'value': c} for c in columnas_disponibles]
    
    if tab == "balance":
        default_metric = "Total Activo"
    elif tab == "indicadores":
        default_metric = columnas_disponibles[0] if columnas_disponibles else None
    else:
        default_metric = "Utilidad Neta" if "Utilidad Neta" in columnas_disponibles else (columnas_disponibles[0] if columnas_disponibles else None)
    
    return metric_options, default_metric, col_options, []
 
 
@app.callback(
    Output('main-table', 'columns'),
    Output('main-table', 'data'),
    Output('graph-container', 'children'),
    Output('main-table', 'style_data_conditional'),
    Input('df-store', 'data'),
    Input('report-tab', 'value'),
    Input('balance-subtab', 'value'),
    Input('metric-dropdown', 'value'),
    Input('chart-type', 'value'),
    Input('mes-filter', 'value'),
    Input('columns-filter', 'value'),
    Input('main-table', 'sort_by')
)
def update_views(df_json, tab, balance_subtab, metric, chart_type, meses, cols_seleccionadas, sort_by):
    if not df_json: return [], [], html.Div('Esperando carga...', style={'textAlign': 'center', 'color': '#64748B', 'padding': '20px'}), []
    
    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except:
        df = pd.read_json(df_json, orient='split')
    
    filtro_tipo = "Balance" if tab == "balance" else ("Acumulado" if tab == "acumulado" else ("Mensual" if tab == "mensual" else "Indicadores"))
    df = df[df['Tipo_Reporte'] == filtro_tipo].dropna(axis=1, how='all')
    df = df.drop('Tipo_Reporte', axis=1, errors='ignore')
    
    if meses and len(meses) > 0:
        df = df[df['Mes'].isin(meses)]
        
    if df.empty: return [], [], html.Div('Sin datos con los filtros actuales.', style={'color': '#EF4444', 'textAlign': 'center'}), []
    
    df['_sort_key'] = df['Mes'].apply(obtener_clave_orden)
    if sort_by and len(sort_by) > 0:
        col = sort_by[0]['column_id']
        asc = (sort_by[0]['direction'] == 'asc')
        df = df.sort_values('_sort_key' if col == 'Mes' else col, ascending=asc)
    else:
        df = df.sort_values('_sort_key', ascending=True)
    df = df.drop('_sort_key', axis=1)
 
    # FILTRAR CONCEPTOS POR SECCIÓN(ES) DEL BALANCE (soporte multi-selección)
    if tab == 'balance' and balance_subtab and len(balance_subtab) > 0:
        # Unimos los conceptos de todas las secciones seleccionadas en orden
        conceptos_union = []
        for sec in ['activo_circulante', 'activo_fijo', 'pasivo_circulante', 'capital_contable']:
            if sec in balance_subtab:
                for c in BALANCE_SECCIONES[sec]:
                    if c not in conceptos_union:
                        conceptos_union.append(c)
        cols_disponibles = df.columns.tolist()
        cols_seccion = ['Mes'] + [c for c in conceptos_union if c in cols_disponibles]
        df = df[cols_seccion]
 
    # TRANSPONER: Meses como columnas (arriba), conceptos como filas (izquierda)
    display_df = df.copy()
    if cols_seleccionadas and tab != 'balance':
        # Filtramos solo los conceptos seleccionados (antes de transponer son columnas)
        display_df = display_df[['Mes'] + [c for c in cols_seleccionadas if c in display_df.columns]]
    else:
        cols_finales = display_df.columns.tolist()
        if 'Mes' in cols_finales:
            cols_finales.insert(0, cols_finales.pop(cols_finales.index('Mes')))
        display_df = display_df[cols_finales]
 
    # Guardamos los tipos de cada columna antes de transponer
    col_types = {}
    for c in display_df.columns:
        if c == 'Mes':
            col_types[c] = 'text'
        elif '%' in c:
            col_types[c] = 'pct'
        else:
            col_types[c] = 'num'
 
    # Transponemos: conceptos pasan a ser filas, meses pasan a ser columnas
    display_df = display_df.set_index('Mes').T.reset_index()
    display_df = display_df.rename(columns={'index': 'Concepto'})
 
    # Identificar filas de porcentaje por nombre del concepto
    pct_concepto_indices = [i for i, r in enumerate(display_df['Concepto'].tolist()) if '%' in str(r)]
    mes_cols = [c for c in display_df.columns if c != 'Concepto']
 
    # CRÍTICO: convertir todas las columnas de mes a object ANTES de asignar strings
    for col in mes_cols:
        display_df[col] = display_df[col].astype(object)
 
    # Formateo de celdas según el tipo de reporte
    # Indicadores: ratios con 2 dec o días enteros; Dinero: $ sin decimales; %: porcentaje
    INDICADORES_RATIO = {'Razón Circulante', 'Prueba Ácida', 'Razón de Endeudamiento'}
    INDICADORES_DIAS  = {'Capital de Trabajo', 'Días CxC', 'Días CxP',
                         'Rotación de Inventario', 'Ciclo del Efectivo'}
 
    def fmt_peso(num):
        if num < 0:
            numero_str = f"-{abs(num):,.0f}"
        else:
            numero_str = f"{num:,.0f}"
        return (
            '<div style="display:flex;justify-content:space-between;'
            'font-weight:700;width:100%;">'
            f'<span>$</span><span>{numero_str}</span></div>'
        )
 
    def fmt_pct(num):
        return f'<div style="text-align:right;font-weight:700">{num * 100:,.2f}%</div>'
 
    def fmt_ratio(num):
        return f'<div style="text-align:right;font-weight:700">{num:,.4f}</div>'
 
    def fmt_dias(num):
        return f'<div style="text-align:right;font-weight:700">{num:,.2f}</div>'
 
    def fmt_capital_trabajo(num):
        if num < 0:
            numero_str = f"-{abs(num):,.0f}"
        else:
            numero_str = f"{num:,.0f}"
        return (
            '<div style="display:flex;justify-content:space-between;'
            'font-weight:700;width:100%;">'
            f'<span>$</span><span>{numero_str}</span></div>'
        )
 
    for i, row_concepto in enumerate(display_df['Concepto'].tolist()):
        es_pct = '%' in str(row_concepto)
        es_ratio = row_concepto in INDICADORES_RATIO
        es_dias  = row_concepto in (INDICADORES_DIAS - {'Capital de Trabajo'})
        es_cap_trabajo = row_concepto == 'Capital de Trabajo'
        for col in mes_cols:
            raw = display_df.at[i, col]
            try:
                if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                    display_df.at[i, col] = '-'
                    continue
                num = float(raw)
                if es_pct:
                    display_df.at[i, col] = fmt_pct(num)
                elif es_ratio:
                    display_df.at[i, col] = fmt_ratio(num)
                elif es_dias:
                    display_df.at[i, col] = fmt_dias(num)
                elif es_cap_trabajo:
                    display_df.at[i, col] = fmt_capital_trabajo(num)
                else:
                    display_df.at[i, col] = fmt_peso(num)
            except (ValueError, TypeError):
                display_df.at[i, col] = str(raw) if raw is not None else '-'
 
    # Concepto: tipo text. Columnas de mes: presentation='markdown' para renderizar HTML inline
    columns_table = []
    for c in display_df.columns:
        if c == 'Concepto':
            columns_table.append({"name": "Concepto", "id": c, "type": "text"})
        else:
            columns_table.append({"name": c, "id": c, "type": "text",
                                   "presentation": "markdown"})
 
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
 
    # Estilos dinámicos por fila: filas % en gris/itálica, filas alternas en gris claro
    style_data_cond = [{'if': {'row_index': 'odd'}, 'backgroundColor': '#F8FAFC'}]
    for idx in pct_concepto_indices:
        style_data_cond.append({
            'if': {'row_index': idx},
            'color': '#64748B', 'fontStyle': 'italic', 'backgroundColor': '#F1F5F9'
        })
 
    return columns_table, display_df.to_dict('records'), graph, style_data_cond
 
 
# ── Mostrar/ocultar panel de comparación según pestaña activa ──────────────
@app.callback(
    Output('comparacion-container', 'style'),
    Input('report-tab', 'value')
)
def toggle_comparacion(tab):
    if tab == 'mensual':
        return {'padding': '20px 15px 0 15px', 'display': 'block'}
    return {'padding': '20px 15px 0 15px', 'display': 'none'}
 
 
# ── Poblar los dropdowns de mes con los meses disponibles ───────────────────
@app.callback(
    Output('comp-mes-a', 'options'),
    Output('comp-mes-b', 'options'),
    Input('df-store', 'data')
)
def poblar_dropdowns_comparacion(df_json):
    if not df_json:
        return [], []
    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except:
        df = pd.read_json(df_json, orient='split')
 
    df_mens = df[df['Tipo_Reporte'] == 'Mensual']
    meses = sorted(df_mens['Mes'].unique(), key=obtener_clave_orden)
    opciones = [{'label': m, 'value': m} for m in meses]
    return opciones, opciones
 
 
# ── Generar tabla + gráfico de comparación al pulsar el botón ───────────────
@app.callback(
    Output('comparacion-resultado', 'children'),
    Input('btn-comparar', 'n_clicks'),
    State('df-store', 'data'),
    State('comp-mes-a', 'value'),
    State('comp-mes-b', 'value'),
    prevent_initial_call=True
)
def generar_comparacion(n_clicks, df_json, mes_a, mes_b):
    if not df_json or not mes_a or not mes_b:
        return html.Div('Selecciona ambos meses para comparar.',
                        style={'color': '#94A3B8', 'padding': '12px', 'fontStyle': 'italic'})
    if mes_a == mes_b:
        return html.Div('Selecciona dos meses diferentes.',
                        style={'color': '#EF4444', 'padding': '12px', 'fontWeight': '600'})
 
    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except:
        df = pd.read_json(df_json, orient='split')
 
    df_mens = df[df['Tipo_Reporte'] == 'Mensual'].drop('Tipo_Reporte', axis=1, errors='ignore')
    df_mens = df_mens.dropna(axis=1, how='all')
 
    fila_a = df_mens[df_mens['Mes'] == mes_a]
    fila_b = df_mens[df_mens['Mes'] == mes_b]
 
    if fila_a.empty or fila_b.empty:
        return html.Div('No se encontraron datos para los meses seleccionados.',
                        style={'color': '#EF4444', 'padding': '12px'})
 
    conceptos = [c for c in df_mens.columns if c != 'Mes']
 
    # Separar conceptos monetarios y de porcentaje
    conceptos_dinero = [c for c in conceptos if '%' not in c]
    conceptos_pct    = [c for c in conceptos if '%' in c]
 
    # ── Construir tabla de comparación ─────────────────────────────────────
    filas_tabla = []
    graf_conceptos, graf_a, graf_b = [], [], []
 
    for c in conceptos:
        es_pct = '%' in c
        try:
            val_a = float(fila_a[c].values[0])
            val_b = float(fila_b[c].values[0])
        except:
            val_a, val_b = 0.0, 0.0
 
        if es_pct:
            fmt_a   = f"{val_a * 100:,.2f}%"
            fmt_b   = f"{val_b * 100:,.2f}%"
            diff    = (val_b - val_a) * 100
            fmt_dif = f"{'+' if diff >= 0 else ''}{diff:,.2f} pp"
            color_dif = '#10B981' if diff >= 0 else '#EF4444'
            variacion = '-'
        else:
            def fp(n):
                s = f"{abs(n):,.0f}"
                return f"$ -{s}" if n < 0 else f"$  {s}"
            fmt_a = fp(val_a)
            fmt_b = fp(val_b)
            diff  = val_b - val_a
            fmt_dif = (f"$ +{abs(diff):,.0f}" if diff >= 0 else f"$ -{abs(diff):,.0f}")
            color_dif = '#10B981' if diff >= 0 else '#EF4444'
            variacion = (f"+{(diff/val_a*100):,.1f}%" if val_a != 0 else 'N/A')
            graf_conceptos.append(c)
            graf_a.append(val_a)
            graf_b.append(val_b)
 
        filas_tabla.append({
            'Concepto': c,
            mes_a: fmt_a,
            mes_b: fmt_b,
            'Diferencia': fmt_dif,
            '% Variación': variacion,
            '_color_dif': color_dif,
            '_es_pct': es_pct
        })
 
    # Estilos condicionales por fila
    style_rows = []
    for idx, fila in enumerate(filas_tabla):
        color = fila['_color_dif']
        if fila['_es_pct']:
            style_rows.append({'if': {'row_index': idx}, 'color': '#64748B',
                                'fontStyle': 'italic', 'backgroundColor': '#F8FAFC'})
        style_rows.append({'if': {'row_index': idx, 'column_id': 'Diferencia'},
                           'color': color, 'fontWeight': '700'})
        style_rows.append({'if': {'row_index': idx, 'column_id': '% Variación'},
                           'color': color, 'fontWeight': '700'})
 
    # Limpiar columnas auxiliares
    data_tabla = [{k: v for k, v in f.items() if not k.startswith('_')} for f in filas_tabla]
 
    columnas_tabla = [
        {'name': 'Concepto',     'id': 'Concepto',     'type': 'text'},
        {'name': mes_a,          'id': mes_a,           'type': 'text'},
        {'name': mes_b,          'id': mes_b,           'type': 'text'},
        {'name': 'Diferencia',   'id': 'Diferencia',    'type': 'text'},
        {'name': '% Variación',  'id': '% Variación',   'type': 'text'},
    ]
 
    tabla = dash_table.DataTable(
        columns=columnas_tabla,
        data=data_tabla,
        style_table={'overflowX': 'auto', 'borderRadius': '8px', 'border': '1px solid #E2E8F0'},
        style_cell={
            'textAlign': 'right', 'padding': '10px 14px',
            'fontFamily': 'Segoe UI, sans-serif', 'fontSize': '13px',
            'fontWeight': '600', 'color': '#1E293B', 'border': '1px solid #E2E8F0',
            'minWidth': '130px', 'whiteSpace': 'nowrap'
        },
        style_cell_conditional=[
            {'if': {'column_id': 'Concepto'}, 'textAlign': 'left',
             'fontWeight': '800', 'color': '#0B2D5B',
             'backgroundColor': '#F8FAFC', 'minWidth': '200px'}
        ],
        style_header={
            'backgroundColor': '#0B2D5B', 'color': 'white',
            'fontWeight': '700', 'textAlign': 'center',
            'border': '1px solid #0B2D5B', 'fontSize': '13px'
        },
        style_data_conditional=style_rows,
        page_action='native', page_size=20
    )
 
    # ── Gráfico de barras agrupadas solo para conceptos monetarios ──────────
    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(
        name=mes_a, x=graf_conceptos, y=graf_a,
        marker_color='#0B2D5B', marker_line_color='#C9A227', marker_line_width=1.5
    ))
    fig_comp.add_trace(go.Bar(
        name=mes_b, x=graf_conceptos, y=graf_b,
        marker_color='#C9A227', marker_line_color='#0B2D5B', marker_line_width=1.5
    ))
    fig_comp.update_layout(
        title={'text': f'Comparación: {mes_a}  vs  {mes_b}',
               'font': {'size': 16, 'color': '#0B2D5B', 'family': 'Segoe UI'}},
        barmode='group',
        plot_bgcolor='#FFFFFF', paper_bgcolor='#FFFFFF',
        xaxis={'gridcolor': '#F1F5F9', 'tickangle': -30},
        yaxis={'gridcolor': '#F1F5F9', 'tickprefix': '$', 'tickformat': ',.0f'},
        legend={'orientation': 'h', 'y': 1.12, 'x': 0.5, 'xanchor': 'center'},
        margin={'t': 70, 'b': 80, 'l': 60, 'r': 20},
        height=400
    )
 
    return html.Div([
        # Tabla
        html.Div([
            html.Div(f'{mes_a}  ⚖️  {mes_b}', style={
                'fontWeight': '700', 'color': '#0B2D5B', 'fontSize': '14px',
                'marginBottom': '12px', 'paddingBottom': '8px',
                'borderBottom': '2px solid #C9A227'
            }),
            tabla
        ], style={'marginBottom': '28px'}),
 
        # Gráfico
        dcc.Graph(figure=fig_comp, config={'displayModeBar': False})
    ])
 
 
# ── Mostrar/ocultar panel de comparación del Balance ───────────────────────
@app.callback(
    Output('comp-balance-container', 'style'),
    Input('report-tab', 'value')
)
def toggle_comp_balance(tab):
    if tab == 'balance':
        return {'padding': '20px 15px 0 15px', 'display': 'block'}
    return {'padding': '20px 15px 0 15px', 'display': 'none'}
 
 
# ── Poblar dropdowns de mes con los meses del Balance ───────────────────────
@app.callback(
    Output('comp-bal-mes-a', 'options'),
    Output('comp-bal-mes-b', 'options'),
    Input('df-store', 'data')
)
def poblar_dropdowns_comp_balance(df_json):
    if not df_json:
        return [], []
    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except:
        df = pd.read_json(df_json, orient='split')
    df_bal = df[df['Tipo_Reporte'] == 'Balance']
    meses = sorted(df_bal['Mes'].unique(), key=obtener_clave_orden)
    opciones = [{'label': m, 'value': m} for m in meses]
    return opciones, opciones
 
 
# ── Generar tabla + gráfico de comparación del Balance ──────────────────────
@app.callback(
    Output('comp-balance-resultado', 'children'),
    Input('btn-comp-balance', 'n_clicks'),
    State('df-store', 'data'),
    State('comp-bal-mes-a', 'value'),
    State('comp-bal-mes-b', 'value'),
    prevent_initial_call=True
)
def generar_comp_balance(n_clicks, df_json, mes_a, mes_b):
    if not df_json or not mes_a or not mes_b:
        return html.Div('Selecciona ambos meses para comparar.',
                        style={'color': '#94A3B8', 'padding': '12px', 'fontStyle': 'italic'})
    if mes_a == mes_b:
        return html.Div('Selecciona dos meses diferentes.',
                        style={'color': '#EF4444', 'padding': '12px', 'fontWeight': '600'})
 
    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except:
        df = pd.read_json(df_json, orient='split')
 
    df_bal = df[df['Tipo_Reporte'] == 'Balance'].drop('Tipo_Reporte', axis=1, errors='ignore')
    df_bal = df_bal.dropna(axis=1, how='all')
 
    fila_a = df_bal[df_bal['Mes'] == mes_a]
    fila_b = df_bal[df_bal['Mes'] == mes_b]
 
    if fila_a.empty or fila_b.empty:
        return html.Div('No se encontraron datos para los meses seleccionados.',
                        style={'color': '#EF4444', 'padding': '12px'})
 
    conceptos = [c for c in df_bal.columns if c != 'Mes']
 
    filas_tabla = []
    graf_conceptos, graf_a, graf_b = [], [], []
 
    for c in conceptos:
        es_pct = '%' in c
        try:
            val_a = float(fila_a[c].values[0])
            val_b = float(fila_b[c].values[0])
        except:
            val_a, val_b = 0.0, 0.0
 
        if es_pct:
            fmt_a   = f"{val_a * 100:,.2f}%"
            fmt_b   = f"{val_b * 100:,.2f}%"
            diff    = (val_b - val_a) * 100
            fmt_dif = f"{'+' if diff >= 0 else ''}{diff:,.2f} pp"
            color_dif = '#10B981' if diff >= 0 else '#EF4444'
            variacion = '-'
        else:
            def fp(n):
                s = f"{abs(n):,.0f}"
                return f"$ -{s}" if n < 0 else f"$  {s}"
            fmt_a = fp(val_a)
            fmt_b = fp(val_b)
            diff  = val_b - val_a
            fmt_dif = (f"$ +{abs(diff):,.0f}" if diff >= 0 else f"$ -{abs(diff):,.0f}")
            color_dif = '#10B981' if diff >= 0 else '#EF4444'
            variacion = (f"+{(diff/val_a*100):,.1f}%" if val_a != 0 else 'N/A')
            graf_conceptos.append(c)
            graf_a.append(val_a)
            graf_b.append(val_b)
 
        filas_tabla.append({
            'Concepto': c,
            mes_a: fmt_a,
            mes_b: fmt_b,
            'Diferencia': fmt_dif,
            '% Variación': variacion,
            '_color_dif': color_dif,
            '_es_pct': es_pct
        })
 
    style_rows = []
    for idx, fila in enumerate(filas_tabla):
        color = fila['_color_dif']
        if fila['_es_pct']:
            style_rows.append({'if': {'row_index': idx}, 'color': '#64748B',
                                'fontStyle': 'italic', 'backgroundColor': '#F8FAFC'})
        style_rows.append({'if': {'row_index': idx, 'column_id': 'Diferencia'},
                           'color': color, 'fontWeight': '700'})
        style_rows.append({'if': {'row_index': idx, 'column_id': '% Variación'},
                           'color': color, 'fontWeight': '700'})
 
    data_tabla = [{k: v for k, v in f.items() if not k.startswith('_')} for f in filas_tabla]
 
    columnas_tabla = [
        {'name': 'Concepto',    'id': 'Concepto',    'type': 'text'},
        {'name': mes_a,         'id': mes_a,          'type': 'text'},
        {'name': mes_b,         'id': mes_b,          'type': 'text'},
        {'name': 'Diferencia',  'id': 'Diferencia',   'type': 'text'},
        {'name': '% Variación', 'id': '% Variación',  'type': 'text'},
    ]
 
    tabla = dash_table.DataTable(
        columns=columnas_tabla,
        data=data_tabla,
        style_table={'overflowX': 'auto', 'borderRadius': '8px', 'border': '1px solid #E2E8F0'},
        style_cell={
            'textAlign': 'right', 'padding': '10px 14px',
            'fontFamily': 'Segoe UI, sans-serif', 'fontSize': '13px',
            'fontWeight': '600', 'color': '#1E293B', 'border': '1px solid #E2E8F0',
            'minWidth': '130px', 'whiteSpace': 'nowrap'
        },
        style_cell_conditional=[
            {'if': {'column_id': 'Concepto'}, 'textAlign': 'left',
             'fontWeight': '800', 'color': '#0B2D5B',
             'backgroundColor': '#F8FAFC', 'minWidth': '220px'}
        ],
        style_header={
            'backgroundColor': '#0B2D5B', 'color': 'white',
            'fontWeight': '700', 'textAlign': 'center',
            'border': '1px solid #0B2D5B', 'fontSize': '13px'
        },
        style_data_conditional=style_rows,
        page_action='native', page_size=25
    )
 
    # Gráfico Balance: solo Total Activo Circulante, Total Pasivo y Total Capital Contable
    CONCEPTOS_GRAF_BAL = ['Total Activo', 'Total Pasivo', 'Total Capital']
    graf_bal_x, graf_bal_a, graf_bal_b = [], [], []
    for c, va, vb in zip(graf_conceptos, graf_a, graf_b):
        if c in CONCEPTOS_GRAF_BAL:
            graf_bal_x.append(c)
            graf_bal_a.append(va)
            graf_bal_b.append(vb)
 
    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(
        name=mes_a, x=graf_bal_x, y=graf_bal_a,
        marker_color='#0B2D5B', marker_line_color='#C9A227', marker_line_width=1.5
    ))
    fig_comp.add_trace(go.Bar(
        name=mes_b, x=graf_bal_x, y=graf_bal_b,
        marker_color='#C9A227', marker_line_color='#0B2D5B', marker_line_width=1.5
    ))
    fig_comp.update_layout(
        title={'text': f'Comparación Balance: {mes_a}  vs  {mes_b}',
               'font': {'size': 16, 'color': '#0B2D5B', 'family': 'Segoe UI'}},
        barmode='group',
        plot_bgcolor='#FFFFFF', paper_bgcolor='#FFFFFF',
        xaxis={'gridcolor': '#F1F5F9', 'tickangle': 0},
        yaxis={'gridcolor': '#F1F5F9', 'tickprefix': '$', 'tickformat': ',.0f'},
        legend={'orientation': 'h', 'y': 1.12, 'x': 0.5, 'xanchor': 'center'},
        margin={'t': 70, 'b': 60, 'l': 60, 'r': 20},
        height=400
    )
 
    return html.Div([
        html.Div([
            html.Div(f'{mes_a}  ⚖️  {mes_b}', style={
                'fontWeight': '700', 'color': '#0B2D5B', 'fontSize': '14px',
                'marginBottom': '12px', 'paddingBottom': '8px',
                'borderBottom': '2px solid #C9A227'
            }),
            tabla
        ], style={'marginBottom': '28px'}),
        dcc.Graph(figure=fig_comp, config={'displayModeBar': False})
    ])
 
 
if __name__ == '__main__':
    host = os.environ.get('DASH_HOST', '0.0.0.0')
    port = int(os.environ.get('DASH_PORT', 8050))
    print(f"Arrancando Dash en http://{host}:{port}/")
    app.run(debug=True, port=port, host=host)
