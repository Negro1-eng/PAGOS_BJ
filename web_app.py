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

# ================= LECTOR SEGURO DE SHEETS =================
def leer_hoja_segura(ws):
    data = ws.get_all_values()

    if not data or len(data) < 2:
        return pd.DataFrame()

    headers = data[0]
    rows = data[1:]

    headers_limpios = []
    contador = {}

    for h in headers:
        h = h.strip() if h else "SIN_NOMBRE"

        if h in contador:
            contador[h] += 1
            h = f"{h}_{contador[h]}"
        else:
            contador[h] = 0

        headers_limpios.append(h)

    return pd.DataFrame(rows, columns=headers_limpios)

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
    ws_clc = sh.worksheet("CLC_CONTRATOS")
    ws_evolucion = sh.worksheet("EVOLUCION")

    df_contratos = leer_hoja_segura(ws_contratos)
    df_clc = leer_hoja_segura(ws_clc)
    df_evolucion = leer_hoja_segura(ws_evolucion)

    # Normalizar columnas
    df_contratos.columns = df_contratos.columns.str.strip()
    df_clc.columns = df_clc.columns.str.strip()
    df_evolucion.columns = df_evolucion.columns.str.strip()

    # Normalizar contratos
    if "N° CONTRATO" in df_contratos.columns:
        df_contratos["N° CONTRATO"] = normalizar_contrato(df_contratos["N° CONTRATO"])

    if "CONTRATO" in df_clc.columns:
        df_clc["CONTRATO"] = normalizar_contrato(df_clc["CONTRATO"])

    # ================= DRIVE =================
    diccionario_links = {}
    page_token = None

    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/pdf'",
            fields="nextPageToken, files(id, name)",
            pageSize=1000,
            pageToken=page_token
        ).execute()

        for file in response.get("files", []):
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

    if "CLC" in df_clc.columns:
        df_clc["CLC"] = df_clc["CLC"].astype(str).str.strip()
        df_clc["PDF"] = df_clc["CLC"].map(diccionario_links)

    return df_contratos, df_clc, df_evolucion


df, df_clc, df_evolucion = cargar_datos(anio)

# ================= LIMPIAR NUMÉRICOS =================
def limpiar_monto(col):
    return (
        col.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
    )

for col in ["Importe total (LC)", "EJERCIDO", "Abrir importe (LC)"]:
    if col in df.columns:
        df[col] = pd.to_numeric(limpiar_monto(df[col]), errors="coerce").fillna(0)

if "MONTO" in df_clc.columns:
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
    if "PARTIDA" in df_evolucion.columns and "DESCRIPCION" in df_evolucion.columns:
        df_evolucion["FILTRO"] = (
            df_evolucion["PARTIDA"].astype(str) + " - " +
            df_evolucion["DESCRIPCION"].astype(str)
        )
        proyectos = ["Todos"] + sorted(df_evolucion["FILTRO"].dropna().unique())
    else:
        proyectos = ["Todos"]

    st.selectbox("PARTIDA / DESCRIPCION", proyectos, key="proyecto")

with c2:
    empresas = ["Todas"] + sorted(df["EMPRESA"].dropna().unique()) if "EMPRESA" in df.columns else ["Todas"]
    st.selectbox("EMPRESA", empresas, key="empresa")

resultado = df.copy()

# Filtro PARTIDA
if st.session_state.proyecto != "Todos" and "PARTIDA" in df.columns:
    partida_sel = st.session_state.proyecto.split(" - ")[0]
    resultado = resultado[resultado["PARTIDA"].astype(str) == partida_sel]

# Filtro empresa
if st.session_state.empresa != "Todas" and "EMPRESA" in df.columns:
    resultado = resultado[resultado["EMPRESA"] == st.session_state.empresa]

contratos = [""] + sorted(resultado["N° CONTRATO"].dropna().unique()) if "N° CONTRATO" in df.columns else [""]

if st.session_state.contrato not in contratos:
    st.session_state.contrato = ""

with c3:
    st.selectbox("N° CONTRATO", contratos, key="contrato")

with c4:
    st.button("Limpiar Filtros", on_click=limpiar_filtros)

# ================= AGRUPAR =================
if not resultado.empty:
    agrupado = resultado.groupby(
        ["N° CONTRATO", "DESCRIPCION"],
        as_index=False
    ).agg({
        "Importe total (LC)": "max",
        "EJERCIDO": "sum",
        "Abrir importe (LC)": "sum",
        "% PAGADO": "first",
        "% PENDIENTE POR EJERCER": "first"
    })
else:
    agrupado = pd.DataFrame()

# ================= CONSUMO =================
st.header("Consumo del Contrato", anchor=False)

if st.session_state.contrato and not agrupado.empty:
    df_contrato = agrupado[agrupado["N° CONTRATO"] == st.session_state.contrato]

    if not df_contrato.empty:
        monto_contrato = df_contrato["Importe total (LC)"].iloc[0]
        monto_ejercido = df_contrato["EJERCIDO"].iloc[0]
        monto_pendiente = df_contrato["Abrir importe (LC)"].iloc[0]

        a, b, c = st.columns(3)
        a.metric("Importe del contrato", formato_pesos(monto_contrato))
        b.metric("Importe ejercido", formato_pesos(monto_ejercido))
        c.metric("Importe pendiente", formato_pesos(monto_pendiente))
else:
    st.info("Selecciona un contrato para ver el consumo")

# ================= TABLA =================
if not agrupado.empty:
    tabla = agrupado.copy()
    tabla["Importe total (LC)"] = tabla["Importe total (LC)"].apply(formato_pesos)

    st.dataframe(tabla, use_container_width=True)

# ================= CLC =================
if st.session_state.contrato and not df_clc.empty:
    st.header("CLC DEL CONTRATO", anchor=False)

    clc_contrato = df_clc[df_clc["CONTRATO"] == st.session_state.contrato].copy()

    if clc_contrato.empty:
        st.warning("⚠️ Este contrato no tiene CLC vinculadas")
    else:
        total_clc = clc_contrato["MONTO"].sum()
        clc_contrato["MONTO"] = clc_contrato["MONTO"].apply(formato_pesos)

        st.dataframe(
            clc_contrato,
            use_container_width=True,
            column_config={
                "PDF": st.column_config.LinkColumn("PDF", display_text="Ver PDF")
            }
        )

        st.markdown(f"### **Total CLC:** {formato_pesos(total_clc)}")
