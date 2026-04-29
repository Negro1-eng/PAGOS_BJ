import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import re

# ================= CONFIGURACIÓN =================
st.set_page_config(
    page_title="Buscador de Consumo de Contratos",
    layout="wide"
)

# ================= ESTILOS =================
st.markdown("""
<style>
header {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stDecoration"] {display: none !important;}
div[data-testid="stStatusWidget"] {display: none !important;}
</style>
""", unsafe_allow_html=True)

st.header("Consumo de Contratos", anchor=False)

# ================= CONFIGURACIÓN POR AÑO =================
CONFIG_ANIOS = {
    "2025": {
        "sheet_id": "1-xq9SMUmxaDmCEmmMmahJa28wOHsuqoAgyly3HiNMNc",
        "folder_id": "1MQtSIS1l-nL0KLLgL46tmo83FJtq4XZJ"
    },
    "2026": {
        "sheet_id": "1-xq9SMUmxaDmCEmmMmahJa28wOHsuqoAgyly3HiNMNc",
        "folder_id": "1xgK3R9cX0zHllQDcJ1x8z100tKB_9EAu"
    }
}

# ================= SELECTOR DE AÑO =================
st.header("Ejercicio fiscal", anchor=False)

anio = st.selectbox(
    "Selecciona el año",
    list(CONFIG_ANIOS.keys())
)

# ================= BOTÓN ACTUALIZAR =================
col1, col2 = st.columns([1, 6])
with col1:
    if st.button("Actualizar datos"):
        st.cache_data.clear()
        st.success(f"Datos actualizados del ejercicio {anio}")
        st.rerun()

# ================= ESTADO =================
defaults = {
    "proyecto": "Todos",
    "empresa": "Todas",
    "contrato": ""
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ================= NORMALIZACIÓN =================
def normalizar_contrato(col):
    return (
        col.astype(str)
        .str.strip()
        .str.upper()
        .str.replace("/", "-", regex=False)
        .str.replace(r"\s+", "", regex=True)
    )

def normalizar_texto(texto):
    return str(texto).strip()

def normalizar_partida(col):
    return (
        col.astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.replace(r"\s+", "", regex=True)
    )

def cargar_rango_como_df(worksheet, rango):
    values = worksheet.get(rango)

    if not values:
        return pd.DataFrame()

    encabezados = values[0]
    filas = values[1:]

    total_cols = len(encabezados)
    filas_ajustadas = []
    for fila in filas:
        fila = fila[:total_cols] + [""] * max(0, total_cols - len(fila))
        filas_ajustadas.append(fila)

    df = pd.DataFrame(filas_ajustadas, columns=encabezados)
    df.columns = [normalizar_texto(col) for col in df.columns]
    return df

# ================= CARGA DE DATOS =================
@st.cache_data
def cargar_datos(anio):
    sheet_id = CONFIG_ANIOS[anio]["sheet_id"]
    folder_id = CONFIG_ANIOS[anio]["folder_id"]

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly"
    ]

    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=scopes
    )

    client = gspread.authorize(creds)
    service = build("drive", "v3", credentials=creds)

    sh = client.open_by_key(sheet_id)

    ws_contratos = sh.get_worksheet(0)
    ws_evolucion = sh.worksheet("Evolucion")
    ws_clc = sh.worksheet("CLC_CONTRATOS")

    df_contratos = cargar_rango_como_df(ws_contratos, "A:R")
    df_evolucion = pd.DataFrame(ws_evolucion.get_all_records())
    df_clc = pd.DataFrame(ws_clc.get_all_records())

    df_contratos.columns = df_contratos.columns.str.strip()
    df_evolucion.columns = df_evolucion.columns.str.strip()
    df_clc.columns = df_clc.columns.str.strip()

    if "PARTIDA" not in df_contratos.columns:
        df_contratos["PARTIDA"] = ""

    if "DESC PARTIDA" not in df_contratos.columns:
        df_contratos["DESC PARTIDA"] = ""

    df_contratos["PARTIDA"] = normalizar_partida(df_contratos["PARTIDA"])
    df_evolucion["PARTIDA"] = normalizar_partida(df_evolucion["PARTIDA"])

    df_contratos["N° CONTRATO"] = normalizar_contrato(df_contratos["N° CONTRATO"])
    df_clc["CONTRATO"] = normalizar_contrato(df_clc["CONTRATO"])

    diccionario_links = {}
    page_token = None

    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/pdf'",
            fields="nextPageToken, files(id, name)",
            pageSize=1000,
            pageToken=page_token
        ).execute()

        files = response.get("files", [])

        for file in files:
            nombre = file["name"]
            file_id = file["id"]

            match = re.search(r"\d+", nombre)
            if match:
                clc = match.group()
                link = f"https://drive.google.com/file/d/{file_id}/view"
                diccionario_links[clc] = link

        page_token = response.get("nextPageToken", None)
        if page_token is None:
            break

    df_clc["CLC"] = df_clc["CLC"].astype(str).str.strip()
    df_clc["PDF"] = df_clc["CLC"].map(diccionario_links)

    return df_contratos, df_evolucion, df_clc

df, df_evolucion, df_clc = cargar_datos(anio)

# ================= NORMALIZAR NUMÉRICOS =================
def limpiar_monto(col):
    return (
        col.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
    )

for col in ["Importe total (LC)", "EJERCIDO", "Abrir importe (LC)"]:
    df[col] = pd.to_numeric(limpiar_monto(df[col]), errors="coerce").fillna(0)

for col in ["ORIGINAL", "MODIFICADO", "COMPROMETIDO", "EJERCIDO"]:
    if col in df_evolucion.columns:
        df_evolucion[col] = pd.to_numeric(limpiar_monto(df_evolucion[col]), errors="coerce").fillna(0)

df_clc["MONTO"] = pd.to_numeric(limpiar_monto(df_clc["MONTO"]), errors="coerce").fillna(0)

# ================= FUNCIONES =================
def formato_pesos(valor):
    return f"$ {valor:,.2f}"

def limpiar_filtros():
    st.session_state.proyecto = "Todos"
    st.session_state.empresa = "Todas"
    st.session_state.contrato = ""

# ================= FILTROS =================
st.header("Filtros", anchor=False)

c1, c2, c3, c4 = st.columns([3, 3, 3, 1])

with c1:
    proyectos = ["Todos"] + sorted(df["DESC PARTIDA"].dropna().astype(str).unique())
    st.selectbox("DESCRIPCION DE PARTIDA", proyectos, key="proyecto")

with c2:
    empresas = ["Todas"] + sorted(df["EMPRESA"].dropna().astype(str).unique())
    st.selectbox("EMPRESA", empresas, key="empresa")

resultado = df.copy()

if st.session_state.proyecto != "Todos":
    resultado = resultado[resultado["DESC PARTIDA"] == st.session_state.proyecto]

if st.session_state.empresa != "Todas":
    resultado = resultado[resultado["EMPRESA"] == st.session_state.empresa]

contratos = [""] + sorted(resultado["N° CONTRATO"].dropna().astype(str).unique())

if st.session_state.contrato not in contratos:
    st.session_state.contrato = ""

with c3:
    st.selectbox("N° CONTRATO", contratos, key="contrato")

with c4:
    st.button("Limpiar Filtros", on_click=limpiar_filtros)

# ================= EVOLUCIÓN =================
if st.session_state.proyecto != "Todos":
    partidas_seleccionadas = (
        resultado["PARTIDA"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    evo = df_evolucion[
        df_evolucion["PARTIDA"].astype(str).isin(partidas_seleccionadas)
    ].copy()

    if not evo.empty:
        st.header("Evolución de la Partida", anchor=False)

        original = evo["ORIGINAL"].sum() if "ORIGINAL" in evo.columns else 0
        modificado = evo["MODIFICADO"].sum() if "MODIFICADO" in evo.columns else 0
        comprometido = evo["COMPROMETIDO"].sum() if "COMPROMETIDO" in evo.columns else 0
        ejercido_evolucion = evo["EJERCIDO"].sum() if "EJERCIDO" in evo.columns else 0

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Original", formato_pesos(original))
        e2.metric("Modificado", formato_pesos(modificado))
        e3.metric("Comprometido", formato_pesos(comprometido))
        e4.metric("Ejercido", formato_pesos(ejercido_evolucion))

        st.subheader("Validación de cruce")
        validacion = resultado[["PARTIDA", "DESC PARTIDA"]].drop_duplicates().copy()
        st.dataframe(validacion, use_container_width=True)

        st.subheader("Registros encontrados en Evolucion")
        columnas_evo = [col for col in ["PARTIDA", "ORIGINAL", "MODIFICADO", "COMPROMETIDO", "EJERCIDO"] if col in evo.columns]
        st.dataframe(evo[columnas_evo], use_container_width=True)
    else:
        st.warning("No se encontraron valores en la hoja Evolucion para las partidas seleccionadas.")

        st.subheader("Validación de cruce")
        validacion = resultado[["PARTIDA", "DESC PARTIDA"]].drop_duplicates().copy()
        st.dataframe(validacion, use_container_width=True)

        st.subheader("Primeras partidas en hoja Evolucion")
        if "PARTIDA" in df_evolucion.columns:
            muestra_evolucion = df_evolucion[["PARTIDA"]].drop_duplicates().head(20)
            st.dataframe(muestra_evolucion, use_container_width=True)

# ================= AGRUPAR =================
agrupado = resultado.groupby(
    ["N° CONTRATO", "DESCRIPCION", "PARTIDA", "DESC PARTIDA"],
    as_index=False
).agg({
    "Importe total (LC)": "max",
    "EJERCIDO": "sum",
    "Abrir importe (LC)": "sum",
    "% PAGADO": "first",
    "% PENDIENTE POR EJERCER": "first"
})

# ================= CONSUMO =================
st.header("Consumo del Contrato", anchor=False)

if st.session_state.contrato:
    df_contrato = agrupado[
        agrupado["N° CONTRATO"] == st.session_state.contrato
    ]

    monto_contrato = df_contrato["Importe total (LC)"].max()
    monto_ejercido = df_contrato["EJERCIDO"].sum()
    monto_pendiente = df_contrato["Abrir importe (LC)"].sum()

    a, b, c = st.columns(3)
    a.metric("Importe del contrato", formato_pesos(monto_contrato))
    b.metric("Importe ejercido", formato_pesos(monto_ejercido))
    c.metric("Importe pendiente", formato_pesos(monto_pendiente))
else:
    st.info("Selecciona un contrato para ver el consumo")

# ================= TABLA =================
if not agrupado.empty:
    tabla = agrupado[[
        "N° CONTRATO",
        "DESCRIPCION",
        "PARTIDA",
        "DESC PARTIDA",
        "Importe total (LC)",
        "% PAGADO",
        "% PENDIENTE POR EJERCER"
    ]].copy()

    tabla["Importe total (LC)"] = tabla["Importe total (LC)"].apply(formato_pesos)

    if st.session_state.contrato:
        with st.expander("Resultados del proyecto / empresa", expanded=False):
            st.dataframe(tabla, use_container_width=True, height=300)
    else:
        st.subheader("Resultados")
        st.dataframe(tabla, use_container_width=True, height=420)
else:
    st.info("No hay contratos disponibles para los filtros seleccionados.")

# ================= CLC =================
if st.session_state.contrato:
    st.header("CLC DEL CONTRATO", anchor=False)

    clc_contrato = df_clc[
        df_clc["CONTRATO"] == st.session_state.contrato
    ][[
        "CLC",
        "ESTIMACION",
        "Fecha de Compen.",
        "Doc. Compen.",
        "FACTURA",
        "MONTO",
        "PDF"
    ]].copy()

    if clc_contrato.empty:
        st.warning("Este contrato no tiene CLC vinculadas (posible diferencia de formato o captura)")
    else:
        total_clc = clc_contrato["MONTO"].sum()
        clc_contrato["MONTO"] = clc_contrato["MONTO"].apply(formato_pesos)

        st.dataframe(
            clc_contrato,
            use_container_width=True,
            column_config={
                "PDF": st.column_config.LinkColumn(
                    "PDF",
                    display_text="Ver PDF"
                )
            }
        )

        st.markdown(f"### **Total CLC:** {formato_pesos(total_clc)}")
