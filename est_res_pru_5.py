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
PATH_DEL_LOGO = os.path.join(BASE_DIR,"logo.png")

def encode_image(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""

logo_base64 = encode_image(PATH_DEL_LOGO)


# ---------------------- LÓGICA DE PROCESAMIENTO ----------------------
def obtener_valor(df, cuenta, columna):
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if valor_cuenta.lower() == cuenta.lower():
            valor = df.iat[i, columna]
            if pd.isna(valor):
                return 0.0
            return float(valor)
    return 0.0

def obtener_704_04(df):
    texto_busqueda = "704.04"
    for i in range(len(df)):
        valor_cuenta = str(df.iat[i, 1]).strip()
        if texto_busqueda in valor_cuenta:
            valor = df.iat[i, 7]
            if pd.isna(valor):
                return 0.0
            return float(valor)
    return 0.0

def procesar_archivo_bytes(content, filename):
    header, encoded = content.split(",", 1)
    data = base64.b64decode(encoded)
    df = pd.read_excel(io.BytesIO(data), header=None)

    ingresos = obtener_valor(df, "4 Ingresos", 7) + obtener_704_04(df)
    costos = obtener_valor(df, "5 Costos", 6)
    gastos_generales = (
        obtener_valor(df, "6 Gastos generales", 6)
        + obtener_valor(df, "701.10 Comisiones bancarias", 6)
    )
    utilidad_bruta = ingresos - costos
    utilidad_operacion = utilidad_bruta - gastos_generales
    gastos_financieros = (
        obtener_valor(df, "701.01 Pérdida cambiaria", 6)
        + obtener_valor(df, "701.04 Intereses a cargo bancario nacional", 6)
    )
    productos_financieros = obtener_valor(df, "702.01 Utilidad cambiaria", 7)
    utilidad_neta = utilidad_operacion - gastos_financieros + productos_financieros

    if ingresos > 0:
        p_costos = costos / ingresos
        p_ubruta = utilidad_bruta / ingresos
        p_ggen = gastos_generales / ingresos
        p_uoper = utilidad_operacion / ingresos
        p_gfin = gastos_financieros / ingresos
        p_pfin = productos_financieros / ingresos
        p_uneta = utilidad_neta / ingresos
    else:
        p_costos = p_ubruta = p_ggen = p_uoper = p_gfin = p_pfin = p_uneta = 0.0

    return {
        "Ingresos": ingresos,
        "Costos": costos,
        "% Costos": p_costos,
        "Utilidad Bruta": utilidad_bruta,
        "% Utilidad Bruta": p_ubruta,
        "Gastos Generales": gastos_generales,
        "% Gastos Gen.": p_ggen,
        "Utilidad Operación": utilidad_operacion,
        "% Util. Operación": p_uoper,
        "Gastos Financieros": gastos_financieros,
        "% Gastos Fin.": p_gfin,
        "Productos Financieros": productos_financieros,
        "% Prod. Fin.": p_pfin,
        "Utilidad Neta": utilidad_neta,
        "% Utilidad Neta": p_uneta,
        "Mes": os.path.splitext(os.path.basename(filename))[0]
    }


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
                html.Div("Sistema Interno de Análisis Financiero | Control Mensual", style={'color': '#C9A227', 'fontSize': '13px', 'fontWeight': '5px', 'marginTop': '2px'})
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
    ], style={
        'margin': '15px',
        'padding': '20px',
        'background': '#FFFFFF',
        'borderRadius': '12px',
        'boxShadow': '0 1px 3px rgba(0,0,0,0.05)'
    }),

    # CONTENEDORES DE REPORTES Y GRÁFICOS
    html.Div([
        html.Div(id='table-container', style={'width': '100%', 'marginBottom': '25px', 'background': '#FFFFFF', 'borderRadius': '12px', 'padding': '15px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.05)'}),
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
            datos = procesar_archivo_bytes(content, name)
            resultados.append(datos)
        except Exception as e:
            return None, html.Div(f"Error procesando {name}: {e}", style={'color': '#EF4444'}), [], None, [], []

    df = pd.DataFrame(resultados)
    columnas = ['Mes'] + [c for c in df.columns if c != 'Mes']
    df = df[columnas]
    metricas = [c for c in df.columns if c != 'Mes']
    metric_options = [{'label': m, 'value': m} for m in metricas]
    
    meses_unicos = sorted(df['Mes'].unique())
    mes_options = [{'label': m, 'value': m} for m in meses_unicos]
    col_options = [{'label': c, 'value': c} for c in columnas if c != 'Mes']
    
    status_msg = html.Div(f'✓ {len(df)} archivos mensuales procesados exitosamente.', style={'color': '#10B981', 'padding': '10px 0'})
    return df.to_json(date_format='iso', orient='split'), status_msg, metric_options, ('Utilidad Neta' if 'Utilidad Neta' in metricas else metricas[0]), mes_options, col_options


@app.callback(
    Output('table-container', 'children'),
    Output('graph-container', 'children'),
    Input('df-store', 'data'),
    Input('metric-dropdown', 'value'),
    Input('chart-type', 'value'),
    Input('mes-filter', 'value'),
    Input('columns-filter', 'value')
)
def update_views(df_json, metric, chart_type, meses_seleccionados, columnas_seleccionadas):
    if not df_json:
        return html.Div('Esperando carga de archivos...', style={'textAlign': 'center', 'color': '#64748B', 'padding': '20px'}), html.Div()
    
    try:
        df = pd.read_json(io.StringIO(df_json), orient='split')
    except ValueError:
        df = pd.read_json(df_json, orient='split')
    
    if meses_seleccionados and len(meses_seleccionados) > 0:
        df = df[df['Mes'].isin(meses_seleccionados)]
    
    if df.empty:
        return html.Div('Sin datos coincidentes con los filtros aplicados.', style={'color': '#EF4444'}), html.Div()
    
    mes_map = {
        'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6,
        'JULIO': 7, 'AGOSTO': 8, 'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12
    }
    
    def sort_key(mes_str):
        parts = mes_str.split()
        if len(parts) == 2:
            mes_name, año = parts
            return (int(año), mes_map.get(mes_name.upper(), 0))
        return (0, 0)
    
    df['_sort_key'] = df['Mes'].apply(sort_key)
    df = df.sort_values('_sort_key').drop('_sort_key', axis=1)

    display_df = df.copy()
    if columnas_seleccionadas and len(columnas_seleccionadas) > 0:
        columnas_a_mostrar = ['Mes'] + columnas_seleccionadas
        display_df = display_df[columnas_a_mostrar]

    columns_table = []

    for c in display_df.columns:

        if c == "Mes":
            columns_table.append({
                "name": c,
                "id": c,
                "type": "text"
            })

        elif "%" in c:
            columns_table.append({
                "name": c,
                "id": c,
                "type": "numeric",
                "format": Format(
                    precision=2,
                    scheme=Scheme.percentage
                )
            })

        else:
            # CAMBIO AQUÍ: Se añade symbol=Symbol.yes para agregar el signo de pesos automáticamente
            columns_table.append({
                "name": c,
                "id": c,
                "type": "numeric",
                "format": Format(
                    precision=2, 
                    scheme=Scheme.fixed, 
                    group=Group.yes,
                    symbol=Symbol.yes
                )
            })

    # TABLA CON ESTILO EJECUTIVO Y COLUMNA "MES" FIJADA
    table = dash_table.DataTable(
        id='main-table',
        columns=columns_table,
        data=display_df.to_dict('records'),
        page_size=50,
        
        fixed_columns={'headers': True, 'data': 1},
        
        style_table={
            'width':'100%', 
            'minWidth':'100%', 
            'overflowX':'auto'
        },
        style_cell={
            'textAlign':'right',
            'padding':'12px 15px',
            'minWidth':'140px',
            'width':'140px',
            'maxWidth':'140px',
            'fontFamily': 'Segoe UI, sans-serif',
            'color': '#334155',
            'border': '1px solid #E2E8F0',
            'backgroundColor': '#FFFFFF' 
        },
        style_cell_conditional=[
            {'if':{'column_id':'Mes'}, 'textAlign':'center', 'fontWeight':'bold', 'color': '#0B2D5B', 'backgroundColor': '#F8FAFC'},
        ],
        style_header={
            'backgroundColor':'#0B2D5B', 
            'color':'white', 
            'fontWeight':'700', 
            'textAlign':'center',
            'border': '1px solid #0B2D5B'
        },
        style_data_conditional=[
            {'if': {'row_index': 'odd'}, 'backgroundColor': '#F8FAFC'}
        ],
        sort_action='native',
        sort_mode='single',
        page_action='native'
    )

    # GRÁFICA 
    fig = None
    if metric and metric in df.columns and not df.empty:
        x = df['Mes'].tolist()
        y = df[metric].tolist()
        
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
            title={'text': f"Análisis Histórico: {metric}", 'font': {'size': 18, 'color': '#0B2D5B', 'family': 'Segoe UI'}},
            margin={'t':50,'b':40, 'l': 60, 'r': 40}, 
            hovermode='x unified',
            plot_bgcolor='#FFFFFF',
            paper_bgcolor='#FFFFFF',
            xaxis={'gridcolor': '#F1F5F9'},
            yaxis={'gridcolor': '#F1F5F9'}
        )

    graph = dcc.Graph(figure=fig, config={'displayModeBar': False}) if fig else html.Div()

    return table, graph


if __name__ == '__main__':
    host = os.environ.get('DASH_HOST', '0.0.0.0')
    port = int(os.environ.get('DASH_PORT', 8050))
    print(f"Arrancando Dash en http://{host}:{port}/")
    app.run(debug=True, port=port, host=host)
