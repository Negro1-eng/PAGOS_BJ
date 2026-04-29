import re
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

st.set_page_config(page_title="Consumo de Contratos", layout="wide")
st.header("Consumo de Contratos")

CONFIG_ANIOS = {
    "2026": {
        "sheet_id": "109Jew5EPHYfwpdWKJYG2N2jRDRU502eVWYTOuM-igdc",
        "folder_id": "1VEFnedYn74acbepMsLu4JILNrLKcstdD"
    }
}

anio = st.selectbox("Ejercicio fiscal", list(CONFIG_ANIOS.keys()))

# ================= FUNCIONES =================
def normalizar_texto(texto):
    texto = str(texto).strip().upper()
    texto = texto.replace("\n", " ").replace("\r", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto

def limpiar_columnas(df):
    df.columns = [normalizar_texto(col) for col in df.columns]
    return df

def limpiar_monto(col):
    return (
        col.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )

def formato_pesos(x):
    try:
        return f"$ {float(x):,.2f}"
    except Exception:
        return "$ 0.00"

def normalizar_clave(col):
    return col.astype(str).str.strip()

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

    df = limpiar_columnas(df)
    df_evolucion = limpiar_columnas(df_evolucion)
    df_clc = limpiar_columnas(df_clc)

    df["PARTIDA"] = normalizar_clave(df["PARTIDA"])
    df_evolucion["PARTIDA"] = normalizar_clave(df_evolucion["PARTIDA"])

    # ================= DRIVE =================
    diccionario_links = {}
    folder_id = CONFIG_ANIOS[anio]["folder_id"]

    files = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/pdf'",
        fields="files(id, name)"
    ).execute().get("files", [])

    for f in files:
        match = re.search(r"\d+", f["name"])
        if match:
            diccionario_links[match.group()] = f"https://drive.google.com/file/d/{f['id']}/view"

    if "CLC" in df_clc.columns:
        df_clc["CLC"] = df_clc["CLC"].astype(str).str.strip()
        df_clc["PDF"] = df_clc["CLC"].map(diccionario_links)
    else:
        df_clc["PDF"] = None

    return df, df_evolucion, df_clc

df, df_evolucion, df_clc = cargar_datos(anio)

# ================= NUMERICOS =================
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

c1, c2, c3 = st.columns(3)

with c1:
    filtro = st.selectbox(
        "PARTIDA",
        ["Todos"] + sorted(df_evolucion["PARTIDA"].dropna().astype(str).unique())
    )

resultado = df.copy()

if filtro != "Todos":
    resultado = resultado[resultado["PARTIDA"] == filtro]

with c2:
    empresas = ["Todas"] + sorted(df["EMPRESA"].dropna().astype(str).unique())
    empresa = st.selectbox("EMPRESA", empresas)

if empresa != "Todas":
    resultado = resultado[resultado["EMPRESA"] == empresa]

with c3:
    contratos = [""] + sorted(resultado["N° CONTRATO"].dropna().astype(str).unique())
    contrato = st.selectbox("CONTRATO", contratos)

# ================= EVOLUCION =================
if filtro != "Todos":
    evo = df_evolucion[df_evolucion["PARTIDA"] == filtro]

    if not evo.empty:
        evo = evo.iloc[0]

        st.subheader("Evolución por partida")

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

agrupado["IMPORTE TOTAL (LC)"] = agrupado["IMPORTE TOTAL (LC)"].apply(formato_pesos)
agrupado["EJERCIDO"] = agrupado["EJERCIDO"].apply(formato_pesos)
agrupado["ABRIR IMPORTE (LC)"] = agrupado["ABRIR IMPORTE (LC)"].apply(formato_pesos)

st.dataframe(agrupado, use_container_width=True)

# ================= CLC =================
if contrato and "CONTRATO" in df_clc.columns:
    clc = df_clc[df_clc["CONTRATO"].astype(str).str.strip() == str(contrato)].copy()

    if not clc.empty:
        if "MONTO" in clc.columns:
            clc["MONTO"] = clc["MONTO"].apply(formato_pesos)

        st.dataframe(
            clc,
            column_config={"PDF": st.column_config.LinkColumn("PDF")},
            use_container_width=True
        )
