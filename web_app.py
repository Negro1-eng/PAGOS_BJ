import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import re

# ================= CONFIG =================
st.set_page_config(page_title="Consumo de Contratos", layout="wide")

st.header("Consumo de Contratos", anchor=False)

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

anio = st.selectbox("Ejercicio fiscal", list(CONFIG_ANIOS.keys()))

if st.button("Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

# ================= FUNCIONES =================
def normalizar_contrato(col):
    return col.astype(str).str.strip().str.upper().str.replace("/", "-", regex=False).str.replace(r"\s+", "", regex=True)

def leer_hoja_segura(ws):
    data = ws.get_all_values()
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

def limpiar_monto(col):
    return col.astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)

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

    df = leer_hoja_segura(sh.get_worksheet(0))
    df_clc = leer_hoja_segura(sh.worksheet("CLC_CONTRATOS"))
    df_evolucion = leer_hoja_segura(sh.worksheet("EVOLUCION"))

    # NORMALIZAR
    if "N° CONTRATO" in df.columns:
        df["N° CONTRATO"] = normalizar_contrato(df["N° CONTRATO"])
    if "CONTRATO" in df_clc.columns:
        df_clc["CONTRATO"] = normalizar_contrato(df_clc["CONTRATO"])

    # ================= MERGE =================
    if "PARTIDA" in df.columns and "PARTIDA" in df_evolucion.columns:
        df["PARTIDA"] = df["PARTIDA"].astype(str).str.strip()
        df_evolucion["PARTIDA"] = df_evolucion["PARTIDA"].astype(str).str.strip()

        df = df.merge(
            df_evolucion,
            on="PARTIDA",
            how="left",
            suffixes=("", "_EVOL")
        )

    # DESCRIPCION FINAL
    if "DESCRIPCION_EVOL" in df.columns:
        df["DESCRIPCION_FINAL"] = df["DESCRIPCION_EVOL"].fillna(df.get("DESCRIPCION"))
    else:
        df["DESCRIPCION_FINAL"] = df.get("DESCRIPCION")

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
        df_clc["CLC"] = df_clc["CLC"].astype(str)
        df_clc["PDF"] = df_clc["CLC"].map(diccionario_links)

    return df, df_clc, df_evolucion


df, df_clc, df_evolucion = cargar_datos(anio)

# ================= NUMÉRICOS =================
for col in ["Importe total (LC)", "EJERCIDO", "Abrir importe (LC)"]:
    if col in df.columns:
        df[col] = pd.to_numeric(limpiar_monto(df[col]), errors="coerce").fillna(0)

if "MONTO" in df_clc.columns:
    df_clc["MONTO"] = pd.to_numeric(limpiar_monto(df_clc["MONTO"]), errors="coerce").fillna(0)

# ================= FILTROS =================
c1, c2, c3 = st.columns(3)

with c1:
    if "PARTIDA" in df_evolucion.columns:
        df_evolucion["FILTRO"] = df_evolucion["PARTIDA"] + " - " + df_evolucion["DESCRIPCION"]
        opciones = ["Todos"] + sorted(df_evolucion["FILTRO"].unique())
    else:
        opciones = ["Todos"]

    filtro_partida = st.selectbox("PARTIDA / DESCRIPCION", opciones)

with c2:
    empresas = ["Todas"] + sorted(df["EMPRESA"].dropna().unique()) if "EMPRESA" in df.columns else ["Todas"]
    empresa_sel = st.selectbox("EMPRESA", empresas)

with c3:
    contratos = [""] + sorted(df["N° CONTRATO"].dropna().unique())
    contrato_sel = st.selectbox("CONTRATO", contratos)

# ================= FILTRADO =================
resultado = df.copy()

if filtro_partida != "Todos" and "PARTIDA" in df.columns:
    partida = filtro_partida.split(" - ")[0]
    resultado = resultado[resultado["PARTIDA"] == partida]

if empresa_sel != "Todas":
    resultado = resultado[resultado["EMPRESA"] == empresa_sel]

# ================= AGRUPAR =================
agrupado = resultado.groupby(
    ["N° CONTRATO", "DESCRIPCION_FINAL"],
    as_index=False
).agg({
    "Importe total (LC)": "max",
    "EJERCIDO": "sum",
    "Abrir importe (LC)": "sum"
})

# ================= MÉTRICAS =================
if contrato_sel:
    d = agrupado[agrupado["N° CONTRATO"] == contrato_sel]

    if not d.empty:
        a, b, c = st.columns(3)
        a.metric("Contrato", formato_pesos(d["Importe total (LC)"].iloc[0]))
        b.metric("Ejercido", formato_pesos(d["EJERCIDO"].iloc[0]))
        c.metric("Pendiente", formato_pesos(d["Abrir importe (LC)"].iloc[0]))

# ================= TABLA =================
st.dataframe(agrupado, use_container_width=True)

# ================= CLC =================
if contrato_sel:
    clc = df_clc[df_clc["CONTRATO"] == contrato_sel]

    if not clc.empty:
        clc["MONTO"] = clc["MONTO"].apply(formato_pesos)

        st.dataframe(
            clc,
            column_config={
                "PDF": st.column_config.LinkColumn("PDF", display_text="Ver PDF")
            },
            use_container_width=True
        )
