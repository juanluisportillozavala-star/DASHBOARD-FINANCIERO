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
    
    'Proveedores': ['201.01.001', '201.03.001'],
    'Impuestos_por_Pagar': [
        '208.01.001', '209.01.001', '209.01.002', '213.01.001', 
        '213.03.001', '216.01.001', '216.04.001', '216.05.001', 
        '216.10.001', '216.10.002', '216.11.001', '216.12.001', '216.12.002'
    ],
    'Otros_Pasivos': ['205.02.001', '205.06.002', '206.01.001', '210.01.001'],
    
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

def calcular_resultados_acumulados(df, grupos):
    """
    Para cuentas 304.01 y 304.02: Suma columna H (Crédito) y resta columna G (Débito).
    Adicionalmente, resta la columna H donde el nombre diga 'GANACIAS/PERDIDAS NO DISTRIBUIDAS'.
    """
    total = 0.0
    
    # 1. Suma H y resta G para las cuentas 304.xx
    for i in range(len(df)):
        codigo = str(df.iat[i, 0]).strip()
        if pd.notna(df.iat[i, 0]) and codigo != 'nan' and codigo != '':
            if any(codigo.startswith(grupo) for grupo in grupos):
                g_debito = df.iat[i, 6]
                h_credito = df.iat[i, 7]
                
                g_val = float(g_debito) if pd.notna(g_debito) and isinstance(g_debito, (int, float)) else 0.0
                h_val = float(h_credito) if pd.notna(h_credito) and isinstance(h_credito, (int, float)) else 0.0
                
                # Fórmula solicitada: Suma H, Resta G (+ H - G)
                total += (h_val - g_val)
                
    # 2. Restar columna H para 'GANACIAS/PERDIDAS NO DISTRIBUIDAS'
    for i in range(len(df)):
        nombre_cuenta = str(df.iat[i, 1]).strip().upper()
        # Buscamos variaciones del texto como "GANACIAS" o "GANANCIAS"
        if "NO DISTRIBUIDAS" in nombre_cuenta and ("GANANCIA" in nombre_cuenta or "GANACIA" in nombre_cuenta or "PERDIDA" in nombre_cuenta):
            h_credito = df.iat[i, 7]
            h_val = float(h_credito) if pd.notna(h_credito) and isinstance(h_credito, (int, float)) else 0.0
            
            # Fórmula solicitada: Restar H
            total -= h_val
            
    return total


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
    imp_pagar = obtener_saldo_exacto(df, CATALOGO_BALANCE['Impuestos_por_Pagar'], es_acreedora=True)
    otros_pasivos = obtener_saldo_exacto(df, CATALOGO_BALANCE['Otros_Pasivos'], es_acreedora=True)
    pasivo_circulante = proveedores + imp_pagar + otros_pasivos
    
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
                    style_cell_conditional=[
                        {'if':{'column_id':'Concepto'}, 'textAlign':'left', 'fontWeight':'bold', 'color': '#0B2D5B', 'backgroundColor': '#F8FAFC', 'minWidth':'200px', 'width':'200px', 'maxWidth':'200px'},
                        {'if':{'filter_query':'{Concepto} contains "%"'}, 'color': '#64748B', 'fontStyle': 'italic'}
                    ],
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
    
    # REORDENAMIENTO MAESTRO: Forzamos a que 'Mes' siempre quede al inicio de todo el DataFrame globalmente
    cols = df.columns.tolist()
    if 'Mes' in cols:
        cols.insert(0, cols.pop(cols.index('Mes')))
    if 'Tipo_Reporte' in cols:
        cols.insert(0, cols.pop(cols.index('Tipo_Reporte'))) 
    df = df[cols]
    
    meses_unicos = sorted(df['Mes'].unique(), key=obtener_clave_orden)
    mes_options = [{'label': m, 'value': m} for m in meses_unicos]
    
    status_msg = html.Div(f'✓ {len(valid_files)} archivos procesados con éxito. Balance calculado con reglas actualizadas.', style={'color': '#10B981', 'padding': '10px 0'})
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
    # En la vista transpuesta, "columnas visibles" filtra por conceptos (filas)
    col_options = [{'label': c, 'value': c} for c in columnas_disponibles]
    
    default_metric = "Total Activo" if tab == "balance" else ("Utilidad Neta" if "Utilidad Neta" in columnas_disponibles else columnas_disponibles[0])
    
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

    # TRANSPONER: Meses como columnas (arriba), conceptos como filas (izquierda)
    display_df = df.copy()
    if cols_seleccionadas:
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

    # Columnas dinámicas: primera es "Concepto", el resto son los meses
    columns_table = []
    for c in display_df.columns:
        if c == 'Concepto':
            columns_table.append({"name": "Concepto", "id": "Concepto", "type": "text"})
        else:
            columns_table.append({"name": c, "id": c, "type": "numeric",
                                   "format": Format(precision=2, scheme=Scheme.fixed, group=Group.yes, symbol=Symbol.yes)})

    # Formatear porcentajes: multiplicar x100 las filas que tengan "%" en el nombre del concepto
    pct_rows = [r for r in display_df['Concepto'].tolist() if '%' in str(r)]
    for col in display_df.columns:
        if col == 'Concepto':
            continue
        for idx, row_val in enumerate(display_df['Concepto']):
            if '%' in str(row_val):
                v = display_df.at[idx, col]
                if pd.notna(v):
                    try:
                        display_df.at[idx, col] = round(float(v) * 100, 2)
                    except:
                        pass

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
