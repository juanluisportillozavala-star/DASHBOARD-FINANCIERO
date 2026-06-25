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


# ---------------------- LÓGICA DE PROCESAMIENTO CONTABLE ----------------------

# --- Lógica 1: Para Reporte Acumulado (Lee saldos finales) ---
def obtener_valor(df, cuenta, columna):
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if valor_cuenta.lower() == cuenta.lower():
            valor = df.iat[i, columna]
            if pd.isna(valor):
                return 0.0
            return float(valor)
    return 0.0

def obtener_704_04(df, columna):
    texto_busqueda = "704.04"
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if texto_busqueda in valor_cuenta:
            valor = df.iat[i, columna]
            if pd.isna(valor):
                return 0.0
            return float(valor)
    return 0.0

# --- Lógica 2: Para Reporte Mensual (Calcula Movimiento Neto del Mes) ---
def obtener_movimiento_neto(df, cuenta, es_acreedora=False):
    """Calcula el movimiento neto mensual restando cargos (col 4) y abonos (col 5)"""
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if valor_cuenta.lower() == cuenta.lower():
            cargo_col4 = df.iat[i, 4] if not pd.isna(df.iat[i, 4]) else 0.0
            abono_col5 = df.iat[i, 5] if not pd.isna(df.iat[i, 5]) else 0.0
            
            if es_acreedora:
                # Ingresos: Abonos menos Cargos (Devoluciones/Descuentos)
                return float(abono_col5) - float(cargo_col4)
            else:
                # Gastos/Costos: Cargos menos Abonos (Cancelaciones/Ajustes)
                return float(cargo_col4) - float(abono_col5)
    return 0.0

def obtener_704_04_neto(df, es_acreedora=False):
    texto_busqueda = "704.04"
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if texto_busqueda in valor_cuenta:
            cargo_col4 = df.iat[i, 4] if not pd.isna(df.iat[i, 4]) else 0.0
            abono_col5 = df.iat[i, 5] if not pd.isna(df.iat[i, 5]) else 0.0
            
            if es_acreedora:
                return float(abono_col5) - float(cargo_col4)
            else:
                return float(cargo_col4) - float(abono_col5)
    return 0.0

# --- Procesador Principal del Excel ---
def procesar_archivo_bytes(content, filename):
    header, encoded = content.split(",", 1)
    data = base64.b64decode(encoded)
    df = pd.read_excel(io.BytesIO(data), header=None)
    
    mes_nombre = os.path.splitext(os.path.basename(filename))[0]

    # ==========================================
    # 1. CÁLCULO ACUMULADO (Saldos Finales: Col 6 y 7)
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
        "Ingresos": ingresos_acum, "Costos": costos_acum, "% Costos": costos_acum/ingresos_acum if ingresos_acum else 0,
        "Utilidad Bruta": utilidad_bruta_acum, "% Utilidad Bruta": utilidad_bruta_acum/ingresos_acum if ingresos_acum else 0,
        "Gastos Generales": gastos_gen_acum, "% Gastos Gen.": gastos_gen_acum/ingresos_acum if ingresos_acum else 0,
        "Utilidad Operación": utilidad_operacion_acum, "% Util. Operación": utilidad_operacion_acum/ingresos_acum if ingresos_acum else 0,
        "Gastos Financieros": gastos_fin_acum, "% Gastos Fin.": gastos_fin_acum/ingresos_acum if ingresos_acum else 0,
        "Productos Financieros": prod_fin_acum, "% Prod. Fin.": prod_fin_acum/ingresos_acum if ingresos_acum else 0,
        "Utilidad Neta": utilidad_neta_acum, "% Utilidad Neta": utilidad_neta_acum/ingresos_acum if ingresos_acum else 0,
        "Mes": mes_nombre,
        "Tipo_Reporte": "Acumulado"
    }

    # ==========================================
    # 2. CÁLCULO MENSUAL (Movimientos Netos: Col 4 y 5)
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
        "Ingresos": ingresos_mes, "Costos": costos_mes, "% Costos": costos_mes/ingresos_mes if ingresos_mes else 0,
        "Utilidad Bruta": utilidad_bruta_mes, "% Utilidad Bruta": utilidad_bruta_mes/ingresos_mes if ingresos_mes else 0,
        "Gastos Generales": gastos_gen_mes, "% Gastos Gen.": gastos_gen_mes/ingresos_mes if ingresos_mes else 0,
        "Utilidad Operación": utilidad_operacion_mes, "% Util. Operación": utilidad_operacion_mes/ingresos_mes if ingresos_mes else 0,
        "Gastos Financieros": gastos_fin_mes, "% Gastos Fin.": gastos_fin_mes/ingresos_mes if ingresos_mes else 0,
        "Productos Financieros": prod_fin_mes, "% Prod. Fin.": prod_fin_mes/ingresos_mes if ingresos_mes else 0,
        "Utilidad Neta": utilidad_neta_mes, "% Utilidad Neta": utilidad_neta_mes/ingresos_mes if ingresos_mes else 0,
        "Mes": mes_nombre,
        "Tipo_Reporte": "Mensual"
    }

    return data_acumulada, data_mensual


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
        html, body, #react-entry-point {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            background-color: #F8FAFC;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        }
        .dash-table-container {
            width: 100% !important;
        }
        .Select-control {
            border: 1px solid #E2E8F0 !important;
            border-radius: 8px !important;
        }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>
"""

# Estilos personalizados para las pestañas
estilo_tab = {
    'borderBottom': '1px solid #E2E8F0',
    'padding': '12px 24px',
    'fontWeight': '600',
    'color': '#64748B',
    'backgroundColor': '#F8FAFC',
    'borderRadius': '8px 8px 0px 0px',
    'marginRight': '4px'
}

estilo_tab_seleccionada = {
    'borderTop': '3px solid #0B2D5B',
    'borderBottom': '3px solid #C9A227',
    'backgroundColor': '#FFFFFF',
    'padding': '11px 24px',
    'color': '#0B2D5B',
    'fontWeight': '700',
    'borderRadius': '8px 8px 0px 0px',
    'marginRight': '4px',
    'boxShadow': '0px -2px 5px rgba(0,0,0,0.02)'
}

app.layout = html.Div([
    
    # HEADER
    html.Div([
        html.Div([
            html.Img(
                src=f"data:image/png;base64,{logo_base64}" if logo_base64 else "",
                style={
                    'height': '60px', 
                    'marginRight': '20px', 
                    'display': 'inline-block' if logo_base64 else 'none',
                    'backgroundColor': 'white',
                    'padding': '5px',
                    'borderRadius': '6px'
                }
            ),
            html.Div([
                html.H2("ESTADO DE RESULTADOS 2026", style={'color': '#FFFFFF', 'margin': '0', 'fontWeight': '700', 'fontSize': '26px', 'letterSpacing': '0.5px'}),
                html.Div("Sistema Interno de Análisis Financiero | Control Mensual y Acumulado", style={'color': '#C9A227', 'fontSize': '13px', 'fontWeight': '5px', 'marginTop': '2px'})
            ], style={'display': 'inline-block', 'verticalAlign': 'middle'})
        ], style={'display': 'flex', 'alignItems': 'center'})
    ], style={
        'background': 'linear-gradient(135deg, #0B2D5B 0%, #1E3A61 100%)',
        'padding': '20px 30px',
        'borderRadius': '0px 0px 15px 15px',
        'boxShadow': '0 4px 6px -1px rgba(0,0,0,0.1)',
        'marginBottom': '25px',
        'borderBottom': '4px solid #C9A227'
    }),

    # ZONA DE CARGA DE ARCHIVOS
    html.Div([
        html.Label('Carga de Datos Operativos', style={'fontWeight': '700', 'color': '#0B2D5B', 'fontSize': '15px', 'display': 'block', 'marginBottom': '8px'}),
        dcc.Upload(
            id='upload-data',
            children=html.Div([
                html.Span('📂 ', style={'fontSize': '20px', 'marginRight': '8px'}),
                'Arrastra o selecciona la carpeta con los archivos mensuales (.xlsx)'
            ]),
            style={
                'width': '100%', 
                'height': '65px',
                'lineHeight': '65px',
                'borderWidth': '2px',
                'borderStyle': 'dashed',
                'borderColor': '#0B2D5B',
                'borderRadius': '10px',
                'textAlign': 'center',
                'background': '#FFFFFF',
                'color': '#0B2D5B',
                'fontWeight': '600',
                'cursor': 'pointer',
                'transition': 'all 0.3s ease'
            },
            multiple=True,
            enable_folder_selection=True,
            accept='.xlsx'
        )
    ], style={'padding': '0 15px', 'marginBottom': '20px'}),

    html.Div(id='upload-status', style={'padding': '0 15px', 'fontWeight': '600', 'color': '#1E293B'}),

    # FILTROS Y CONTROLES GLOBALES
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
    ], style={
        'margin': '15px',
        'padding': '20px',
        'background': '#FFFFFF',
        'borderRadius': '12px',
        'boxShadow': '0 1px 3px rgba(0,0,0,0.05)'
    }),

    # NAVEGACIÓN POR PESTAÑAS (ACUMULADO VS MENSUAL)
    dcc.Tabs(id='report-tab', value='acumulado', children=[
        dcc.Tab(label='Estado de Resultados Acumulado', value='acumulado', style=estilo_tab, selected_style=estilo_tab_seleccionada),
        dcc.Tab(label='Estado de Resultados Mensual', value='mensual', style=estilo_tab, selected_style=estilo_tab_seleccionada)
    ], style={'margin': '0 15px'}),

    # CONTENEDORES DE REPORTES Y GRÁFICOS
    html.Div([
        html.Div(
            style={'width': '100%', 'marginBottom': '25px', 'background': '#FFFFFF', 'borderRadius': '0px 0px 12px 12px', 'padding': '20px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.05)', 'borderTop': '1px solid #E2E8F0'},
            children=[
                dash_table.DataTable(
                    id='main-table',
                    page_size=50,
                    fixed_columns={'headers': True, 'data': 1},
                    style_table={'width':'100%', 'minWidth':'100%', 'overflowX':'auto'},
                    style_cell={
                        'textAlign':'right', 'padding':'12px 15px', 'minWidth':'140px', 
                        'width':'140px', 'maxWidth':'140px', 'fontFamily': 'Segoe UI, sans-serif', 
                        'color': '#334155', 'border': '1px solid #E2E8F0', 'backgroundColor': '#FFFFFF' 
                    },
                    style_cell_conditional=[
                        {'if':{'column_id':'Mes'}, 'textAlign':'center', 'fontWeight':'bold', 'color': '#0B2D5B', 'backgroundColor': '#F8FAFC'},
                    ],
                    style_header={
                        'backgroundColor':'#0B2D5B', 'color':'white', 'fontWeight':'700', 
                        'textAlign':'center', 'border': '1px solid #0B2D5B'
                    },
                    style_data_conditional=[
                        {'if': {'row_index': 'odd'}, 'backgroundColor': '#F8FAFC'}
                    ],
                    sort_action='custom',
                    sort_mode='single',
                    sort_by=[],
                    page_action='native'
                )
            ]
        ),
        html.Div(id='graph-container', style={'width': '100%', 'background': '#FFFFFF', 'borderRadius': '12px', 'padding': '15px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.05)'})
    ], style={'padding': '0 15px'}),

    dcc.Store(id='df-store')
], style={
    'width':'100%',
    'maxWidth':'100%',
    'margin':'0',
    'boxSizing': 'border-box'
})


# ---------------------- CALLBACKS ----------------------
@app.callback(
    Output('df-store', 'data'),
    Output('upload-status', 'children'),
    Output('metric-dropdown', 'options'),
    Output('metric-dropdown', 'value'),
    Output('mes-filter', 'options'),
    Output('columns-filter', 'options'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def update_store(upload_contents, upload_names):
    if not upload_contents or not upload_names:
        return None, '', [], None, [], []

    resultados = []
    valid_files = [(content, name) for content, name in zip(upload_contents, upload_names) if name.lower().endswith('.xlsx')]
    if not valid_files:
        return None, html.Div('No se encontraron archivos .xlsx válidos en la carpeta.', style={'color': '#EF4444'}), [], None, [], []

    for content, name in valid_files:
        try:
            acum, mens = procesar_archivo_bytes(content, name)
            resultados.append(acum)
            resultados.append(mens)
        except Exception as e:
            return None, html.Div(f"Error procesando {name}: {e}", style={'color': '#EF4444'}), [], None, [], []

    df = pd.DataFrame(resultados)
    
    # Reordenamiento de columnas (excluyendo Tipo_Reporte del frontend directo)
    columnas_base = [c for c in df.columns if c not in ['Mes', 'Tipo_Reporte']]
    columnas_ordenadas = ['Tipo_Reporte', 'Mes'] + columnas_base
    df = df[columnas_ordenadas]
    
    metric_options = [{'label': m, 'value': m} for m in columnas_base]
    
    meses_unicos = sorted(df['Mes'].unique(), key=obtener_clave_orden)
    mes_options = [{'label': m, 'value': m} for m in meses_unicos]
    
    col_options = [{'label': c, 'value': c} for c in columnas_base]
    
    status_msg = html.Div(f'✓ {len(df) // 2} archivos procesados con éxito (Se calcularon métricas Acumuladas y Mensuales).', style={'color': '#10B981', 'padding': '10px 0'})
    return df.to_json(date_format='iso', orient='split'), status_msg, metric_options, ('Utilidad Neta' if 'Utilidad Neta' in columnas_base else columnas_base[0]), mes_options, col_options


@app.callback(
    Output('main-table', 'columns'),
    Output('main-table', 'data'),
    Output('graph-container', 'children'),
    Input('df-store', 'data'),
    Input('report-tab', 'value'), # Entrada para saber en qué pestaña estamos
    Input('metric-dropdown', 'value'),
    Input('chart-type', 'value'),
    Input('mes-filter', 'value'),
    Input('columns-filter', 'value'),
    Input('main-table', 'sort_by')
)
def update_views(df_json, tab_seleccionado, metric, chart_type, meses_seleccionados, columnas_seleccionadas, sort_by):
    if not df_json:
        return [], [], html.Div('Esperando carga de archivos...', style={'textAlign': 'center', 'color': '#64748B', 'padding': '20px'})
    
    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except ValueError:
        df = pd.read_json(df_json, orient='split')
    
    # --- APLICACIÓN DE FILTRO POR PESTAÑA ---
    filtro_tipo = "Acumulado" if tab_seleccionado == "acumulado" else "Mensual"
    df = df[df['Tipo_Reporte'] == filtro_tipo]
    df = df.drop('Tipo_Reporte', axis=1)
    
    # Aplicación de filtros de UI
    if meses_seleccionados and len(meses_seleccionados) > 0:
        df = df[df['Mes'].isin(meses_seleccionados)]
    
    if df.empty:
        return [], [], html.Div('Sin datos coincidentes con los filtros aplicados.', style={'color': '#EF4444', 'textAlign': 'center', 'padding': '20px'})
    
    # Ordenamiento
    df['_sort_key'] = df['Mes'].apply(obtener_clave_orden)
    
    if sort_by and len(sort_by) > 0:
        col_id = sort_by[0]['column_id']
        direction = sort_by[0]['direction']
        ascendente = (direction == 'asc')
        
        if col_id == 'Mes':
            df = df.sort_values('_sort_key', ascending=ascendente)
        else:
            df = df.sort_values(col_id, ascending=ascendente)
    else:
        df = df.sort_values('_sort_key', ascending=True)

    df = df.drop('_sort_key', axis=1)

    # Selección de columnas
    display_df = df.copy()
    if columnas_seleccionadas and len(columnas_seleccionadas) > 0:
        columnas_a_mostrar = ['Mes'] + columnas_seleccionadas
        display_df = display_df[columnas_a_mostrar]

    # Formateo de columnas para Dash Table
    columns_table = []
    for c in display_df.columns:
        if c == "Mes":
            columns_table.append({"name": c, "id": c, "type": "text"})
        elif "%" in c:
            columns_table.append({
                "name": c, "id": c, "type": "numeric",
                "format": Format(precision=2, scheme=Scheme.percentage)
            })
        else:
            columns_table.append({
                "name": c, "id": c, "type": "numeric",
                "format": Format(precision=2, scheme=Scheme.fixed, group=Group.yes, symbol=Symbol.yes)
            })

    # Gráfica
    fig = None
    if metric and metric in df.columns and not df.empty:
        df_graph = df.sort_values(by='Mes', key=lambda col: col.apply(obtener_clave_orden))
        x = df_graph['Mes'].tolist()
        y = df_graph[metric].tolist()
        
        if chart_type == 'lines':
            fig = go.Figure(go.Scatter(
                x=x, y=y, 
                mode='lines+markers', 
                marker={'size': 9, 'color': '#C9A227', 'line': {'width': 2, 'color': '#0B2D5B'}}, 
                line={'color':'#0B2D5B', 'width': 3}
            ))
        else:
            fig = go.Figure(go.Bar(
                x=x, y=y, 
                marker_color='#0B2D5B',
                marker_line_color='#C9A227',
                marker_line_width=1.5
            ))

        if '%' in metric:
            fig.update_yaxes(tickformat='.1%')
        else:
            fig.update_yaxes(tickprefix='$', separatethousands=True)

        fig.update_layout(
            title={'text': f"Análisis Histórico ({filtro_tipo}): {metric}", 'font': {'size': 18, 'color': '#0B2D5B', 'family': 'Segoe UI'}},
            margin={'t':50,'b':40, 'l': 60, 'r': 40}, 
            hovermode='x unified',
            plot_bgcolor='#FFFFFF',
            paper_bgcolor='#FFFFFF',
            xaxis={'gridcolor': '#F1F5F9'},
            yaxis={'gridcolor': '#F1F5F9'}
        )

    graph = dcc.Graph(figure=fig, config={'displayModeBar': False}) if fig else html.Div()

    return columns_table, display_df.to_dict('records'), graph


if __name__ == '__main__':
    host = os.environ.get('DASH_HOST', '0.0.0.0')
    port = int(os.environ.get('DASH_PORT', 8050))
    print(f"Arrancando Dash en http://{host}:{port}/")
    app.run(debug=True, port=port, host=host)
