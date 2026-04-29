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

def normalizar_texto(texto):
    texto = str(texto).strip().upper()
    texto = texto.replace("\n", " ").replace("\r", " ")
    texto = texto.replace("N°", "NO").replace("Nº", "NO")
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
    return limpiar_columnas(df)

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

    # Fuerza lectura hasta la columna R
    df = cargar_rango_como_df(sh.get_worksheet(0), "A:R")
    df_evolucion = cargar_rango_como_df(sh.worksheet("Evolucion"), "A:F")
    df_clc = pd.DataFrame(sh.worksheet("CLC_CONTRATOS").get_all_records())
    df_clc = limpiar_columnas(df_clc)

    st.write("Columnas hoja 1:", list(df.columns))
    st.write("Columnas evolucion:", list(df_evolucion.columns))

    col_partida_df = "PARTIDA"
    col_desc_partida_df = "DESC PARTIDA"
    col_partida_evo = "PARTIDA"
    col_empresa = "EMPRESA"
    col_contrato = "NO CONTRATO"
    col_descripcion = "DESCRIPCION"
    col_importe_total = "IMPORTE TOTAL (LC)"
    col_abrir_importe = "ABRIR IMPORTE (LC)"
    col_ejercido_df = "EJERCIDO"

    if col_partida_df not in df.columns:
        st.error(f"No se encontró '{col_partida_df}' en hoja 1")
        st.stop()

    if col_desc_partida_df not in df.columns:
        st.error(f"No se encontró '{col_desc_partida_df}' en hoja 1")
        st.stop()

    if col_partida_evo not in df_evolucion.columns:
        st.error(f"No se encontró '{col_partida_evo}' en hoja Evolucion")
        st.stop()

    df[col_partida_df] = normalizar_clave(df[col_partida_df])
    df_evolucion[col_partida_evo] = normalizar_clave(df_evolucion[col_partida_evo])

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

    return (
        df,
        df_evolucion,
        df_clc,
        col_partida_df,
        col_desc_partida_df,
        col_partida_evo,
        col_empresa,
        col_contrato,
        col_descripcion,
        col_importe_total,
        col_abrir_importe,
        col_ejercido_df,
    )

(
    df,
    df_evolucion,
    df_clc,
    col_partida_df,
    col_desc_partida_df,
    col_partida_evo,
    col_empresa,
    col_contrato,
    col_descripcion,
    col_importe_total,
    col_abrir_importe,
    col_ejercido_df,
) = cargar_datos(anio)

for col in [col_importe_total, col_ejercido_df, col_abrir_importe]:
    df[col] = pd.to_numeric(limpiar_monto(df[col]), errors="coerce").fillna(0)

for col in ["ORIGINAL", "MODIFICADO", "COMPROMETIDO", "EJERCIDO"]:
    if col in df_evolucion.columns:
        df_evolucion[col] = pd.to_numeric(limpiar_monto(df_evolucion[col]), errors="coerce").fillna(0)

if "MONTO" in df_clc.columns:
    df_clc["MONTO"] = pd.to_numeric(limpiar_monto(df_clc["MONTO"]), errors="coerce").fillna(0)

st.header("Filtros")

c1, c2, c3 = st.columns(3)

with c1:
    filtro = st.selectbox(
        "PARTIDA",
        ["Todos"] + sorted(df_evolucion[col_partida_evo].dropna().astype(str).unique())
    )

resultado = df.copy()

if filtro != "Todos":
    resultado = resultado[resultado[col_partida_df] == filtro]

with c2:
    empresas = ["Todas"] + sorted(resultado[col_empresa].dropna().astype(str).unique())
    empresa = st.selectbox("EMPRESA", empresas)

if empresa != "Todas":
    resultado = resultado[resultado[col_empresa] == empresa]

with c3:
    contratos = [""] + sorted(resultado[col_contrato].dropna().astype(str).unique())
    contrato = st.selectbox("CONTRATO", contratos)

if filtro != "Todos":
    evo = df_evolucion[df_evolucion[col_partida_evo] == filtro]

    if not evo.empty:
        evo = evo.iloc[0]
        st.subheader("Evolución por partida")

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Original", formato_pesos(evo.get("ORIGINAL", 0)))
        e2.metric("Modificado", formato_pesos(evo.get("MODIFICADO", 0)))
        e3.metric("Comprometido", formato_pesos(evo.get("COMPROMETIDO", 0)))
        e4.metric("Ejercido", formato_pesos(evo.get("EJERCIDO", 0)))

agrupado = resultado.groupby(
    [col_contrato, col_descripcion, col_partida_df, col_desc_partida_df],
    as_index=False
).agg({
    col_importe_total: "max",
    col_ejercido_df: "sum",
    col_abrir_importe: "sum"
})

agrupado["IMPORTE TOTAL (LC)"] = agrupado[col_importe_total].apply(formato_pesos)
agrupado["EJERCIDO"] = agrupado[col_ejercido_df].apply(formato_pesos)
agrupado["ABRIR IMPORTE (LC)"] = agrupado[col_abrir_importe].apply(formato_pesos)

st.dataframe(
    agrupado[
        [col_contrato, col_descripcion, col_partida_df, col_desc_partida_df,
         "IMPORTE TOTAL (LC)", "EJERCIDO", "ABRIR IMPORTE (LC)"]
    ],
    use_container_width=True
)

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
