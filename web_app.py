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

st.header("Consumo de Contratos", anchor=False)

# ================= CONFIG =================
CONFIG_ANIOS = {
    "2025": {
        "sheet_id": "1q2cvx9FD1CW8XP_kZpsFvfKtu4QdrJPqKAZuueHRIW4",
        "folder_id": "1MQtSIS1l-nL0KLLgL46tmo83FJtq4XZJ"
    },
    "2026": {
        "sheet_id": "109Jew5EPHYfwpdWKJYG2N2jRDRU502eVWYTOuM-igdc",
        "folder_id": "1VEFnedYn74acbepMsLu4JILNrLKcstdD"
    }
}

anio = st.selectbox("Ejercicio fiscal", list(CONFIG_ANIOS.keys()))

if st.button("Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

# ================= FUNCIONES =================
def limpiar_columnas(df):
    df.columns = df.columns.str.strip().str.upper()
    return df

def limpiar_monto(col):
    return col.astype(str).str.replace("$", "").str.replace(",", "")

def formato_pesos(x):
    return f"$ {x:,.2f}"

# ================= CARGA =================
@st.cache_data
def cargar_datos(anio):

    creds = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly"
        ]
    )

    client = gspread.authorize(creds)
    service = build("drive", "v3", credentials=creds)

    sh = client.open_by_key(CONFIG_ANIOS[anio]["sheet_id"])

    df = pd.DataFrame(sh.get_worksheet(0).get_all_records())
    df_evolucion = pd.DataFrame(sh.worksheet("Evolucion").get_all_records())
    df_clc = pd.DataFrame(sh.worksheet("CLC_CONTRATOS").get_all_records())

    # 🔥 LIMPIAR COLUMNAS (SOLUCIONA TU ERROR)
    df = limpiar_columnas(df)
    df_evolucion = limpiar_columnas(df_evolucion)
    df_clc = limpiar_columnas(df_clc)

    # ================= DRIVE =================
    folder_id = CONFIG_ANIOS[anio]["folder_id"]
    diccionario_links = {}
    page_token = None

    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/pdf'",
            fields="nextPageToken, files(id, name)",
            pageSize=1000,
            pageToken=page_token
        ).execute()

        for f in response.get("files", []):
            match = re.search(r"\d+", f["name"])
            if match:
                diccionario_links[match.group()] = f"https://drive.google.com/file/d/{f['id']}/view"

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    if "CLC" in df_clc.columns:
        df_clc["CLC"] = df_clc["CLC"].astype(str).str.strip()
        df_clc["PDF"] = df_clc["CLC"].map(diccionario_links)

    return df, df_evolucion, df_clc


df, df_evolucion, df_clc = cargar_datos(anio)

# ================= NUMÉRICOS =================
for col in ["IMPORTE TOTAL (LC)", "EJERCIDO", "ABRIR IMPORTE (LC)"]:
    if col in df.columns:
        df[col] = pd.to_numeric(limpiar_monto(df[col]), errors="coerce").fillna(0)

for col in ["ORIGINAL", "MODIFICADO", "COMPROMETIDO", "EJERCIDO"]:
    if col in df_evolucion.columns:
        df_evolucion[col] = pd.to_numeric(limpiar_monto(df_evolucion[col]), errors="coerce").fillna(0)

if "MONTO" in df_clc.columns:
    df_clc["MONTO"] = pd.to_numeric(limpiar_monto(df_clc["MONTO"]), errors="coerce").fillna(0)

# ================= FILTROS =================
st.header("Filtros")

c1, c2, c3, c4 = st.columns([3,3,3,1])

with c1:
    df_evolucion["FILTRO"] = df_evolucion["PARTIDA"].astype(str) + " - " + df_evolucion["DESCRIPCION"].astype(str)
    opciones = ["Todos"] + sorted(df_evolucion["FILTRO"].unique())
    filtro = st.selectbox("PARTIDA / DESCRIPCION", opciones)

with c2:
    empresas = ["Todas"] + sorted(df["EMPRESA"].dropna().unique())
    empresa = st.selectbox("EMPRESA", empresas)

resultado = df.copy()

if filtro != "Todos":
    partida = filtro.split(" - ")[0]
    resultado = resultado[resultado["PARTIDA"].astype(str) == partida]

if empresa != "Todas":
    resultado = resultado[resultado["EMPRESA"] == empresa]

contratos = [""] + sorted(resultado["N° CONTRATO"].dropna().astype(str).unique())

with c3:
    contrato = st.selectbox("CONTRATO", contratos)

with c4:
    if st.button("Limpiar"):
        st.rerun()

# ================= EVOLUCIÓN =================
if filtro != "Todos":
    partida = filtro.split(" - ")[0]
    evo = df_evolucion[df_evolucion["PARTIDA"].astype(str) == partida]

    if not evo.empty:
        evo = evo.iloc[0]

        st.subheader("Evolución presupuestal")

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Original", formato_pesos(evo["ORIGINAL"]))
        e2.metric("Modificado", formato_pesos(evo["MODIFICADO"]))
        e3.metric("Comprometido", formato_pesos(evo["COMPROMETIDO"]))
        e4.metric("Ejercido", formato_pesos(evo["EJERCIDO"]))

# ================= AGRUPADO =================
agrupado = resultado.groupby(
    ["N° CONTRATO", "DESCRIPCION"],
    as_index=False
).agg({
    "IMPORTE TOTAL (LC)": "max",
    "EJERCIDO": "sum",
    "ABRIR IMPORTE (LC)": "sum"
})

# ================= CONSUMO =================
st.header("Consumo del contrato")

if contrato:
    d = agrupado[agrupado["N° CONTRATO"].astype(str) == contrato]

    if not d.empty:
        a,b,c = st.columns(3)
        a.metric("Contrato", formato_pesos(d["IMPORTE TOTAL (LC)"].iloc[0]))
        b.metric("Ejercido", formato_pesos(d["EJERCIDO"].iloc[0]))
        c.metric("Pendiente", formato_pesos(d["ABRIR IMPORTE (LC)"].iloc[0]))

# ================= TABLA =================
st.dataframe(agrupado, use_container_width=True)

# ================= CLC =================
if contrato:
    st.subheader("CLC")

    clc = df_clc[df_clc["CONTRATO"].astype(str) == contrato]

    if not clc.empty:
        clc["MONTO"] = clc["MONTO"].apply(formato_pesos)

        st.dataframe(
            clc,
            column_config={
                "PDF": st.column_config.LinkColumn("PDF", display_text="Ver PDF")
            },
            use_container_width=True
        )
