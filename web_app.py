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
        "folder_id": "1VEFnedYn74acbepMsLu4JILNrLKcstdD",
    }
}

anio = st.selectbox("Ejercicio fiscal", list(CONFIG_ANIOS.keys()))

# ================= FUNCIONES =================
def normalizar_texto(texto):
    texto = str(texto).strip().upper()
    texto = texto.replace("N°", "NO")
    texto = texto.replace("Nº", "NO")
    texto = texto.replace("\n", " ")
    texto = texto.replace("\r", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto

def limpiar_columnas(df):
    df.columns = [normalizar_texto(col) for col in df.columns]
    return df

def buscar_columna(df, nombres_posibles=None, contiene=None, requerida=True):
    columnas = list(df.columns)
    columnas_norm = {normalizar_texto(col): col for col in columnas}

    if nombres_posibles:
        for nombre in nombres_posibles:
            nombre_norm = normalizar_texto(nombre)
            if nombre_norm in columnas_norm:
                return columnas_norm[nombre_norm]

    if contiene:
        contiene_norm = [normalizar_texto(x) for x in contiene]
        for col in columnas:
            col_norm = normalizar_texto(col)
            if all(fragmento in col_norm for fragmento in contiene_norm):
                return col

    if requerida:
        st.error("No se encontró una columna requerida.")
        st.write("Columnas disponibles:", columnas)
        st.stop()

    return None

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
            "https://www.googleapis.com/auth/drive.readonly",
        ],
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

    # Si necesitas depurar, descomenta estas líneas
    # st.write("Columnas hoja principal:", list(df.columns))
    # st.write("Columnas hoja evolucion:", list(df_evolucion.columns))
    # st.write("Columnas hoja clc:", list(df_clc.columns))

    col_partida_df = buscar_columna(
        df,
        nombres_posibles=["NO PARTIDA", "PARTIDA"],
        contiene=["PARTIDA"],
    )

    col_partida_evo = buscar_columna(
        df_evolucion,
        nombres_posibles=["NO PARTIDA", "PARTIDA"],
        contiene=["PARTIDA"],
    )

    col_contrato_df = buscar_columna(
        df,
        nombres_posibles=["NO CONTRATO", "CONTRATO"],
        contiene=["CONTRATO"],
    )

    col_descripcion_df = buscar_columna(
        df,
        nombres_posibles=["DESCRIPCION"],
        contiene=["DESCRIPCION"],
    )

    col_empresa_df = buscar_columna(
        df,
        nombres_posibles=["EMPRESA"],
        contiene=["EMPRESA"],
    )

    col_importe_total_df = buscar_columna(
        df,
        nombres_posibles=["IMPORTE TOTAL (LC)", "IMPORTE TOTAL"],
        contiene=["IMPORTE", "TOTAL"],
    )

    col_abrir_importe_df = buscar_columna(
        df,
        nombres_posibles=["ABRIR IMPORTE (LC)", "ABRIR IMPORTE"],
        contiene=["ABRIR", "IMPORTE"],
    )

    col_ejercido_df = buscar_columna(
        df,
        nombres_posibles=["EJERCIDO"],
        contiene=["EJERCIDO"],
    )

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

    col_clc = buscar_columna(
        df_clc,
        nombres_posibles=["CLC"],
        contiene=["CLC"],
        requerida=False,
    )

    col_contrato_clc = buscar_columna(
        df_clc,
        nombres_posibles=["CONTRATO", "NO CONTRATO"],
        contiene=["CONTRATO"],
        requerida=False,
    )

    col_monto_clc = buscar_columna(
        df_clc,
        nombres_posibles=["MONTO"],
        contiene=["MONTO"],
        requerida=False,
    )

    if col_clc:
        df_clc[col_clc] = df_clc[col_clc].astype(str).str.strip()
        df_clc["PDF"] = df_clc[col_clc].map(diccionario_links)
    else:
        df_clc["PDF"] = None

    return {
        "df": df,
        "df_evolucion": df_evolucion,
        "df_clc": df_clc,
        "col_partida_df": col_partida_df,
        "col_partida_evo": col_partida_evo,
        "col_contrato_df": col_contrato_df,
        "col_descripcion_df": col_descripcion_df,
        "col_empresa_df": col_empresa_df,
        "col_importe_total_df": col_importe_total_df,
        "col_abrir_importe_df": col_abrir_importe_df,
        "col_ejercido_df": col_ejercido_df,
        "col_contrato_clc": col_contrato_clc,
        "col_monto_clc": col_monto_clc,
    }

datos = cargar_datos(anio)

df = datos["df"]
df_evolucion = datos["df_evolucion"]
df_clc = datos["df_clc"]
col_partida_df = datos["col_partida_df"]
col_partida_evo = datos["col_partida_evo"]
col_contrato_df = datos["col_contrato_df"]
col_descripcion_df = datos["col_descripcion_df"]
col_empresa_df = datos["col_empresa_df"]
col_importe_total_df = datos["col_importe_total_df"]
col_abrir_importe_df = datos["col_abrir_importe_df"]
col_ejercido_df = datos["col_ejercido_df"]
col_contrato_clc = datos["col_contrato_clc"]
col_monto_clc = datos["col_monto_clc"]

# ================= NUMERICOS =================
for col in [col_importe_total_df, col_ejercido_df, col_abrir_importe_df]:
    df[col] = pd.to_numeric(limpiar_monto(df[col]), errors="coerce").fillna(0)

for col in ["ORIGINAL", "MODIFICADO", "COMPROMETIDO", "EJERCIDO"]:
    if col in df_evolucion.columns:
        df_evolucion[col] = pd.to_numeric(limpiar_monto(df_evolucion[col]), errors="coerce").fillna(0)

if col_monto_clc and col_monto_clc in df_clc.columns:
    df_clc[col_monto_clc] = pd.to_numeric(limpiar_monto(df_clc[col_monto_clc]), errors="coerce").fillna(0)

# ================= FILTROS =================
st.header("Filtros")

c1, c2, c3 = st.columns(3)

with c1:
    partidas = ["Todos"] + sorted(df_evolucion[col_partida_evo].dropna().astype(str).unique())
    filtro = st.selectbox("PARTIDA", partidas)

resultado = df.copy()

if filtro != "Todos":
    resultado = resultado[resultado[col_partida_df] == filtro]

with c2:
    empresas = ["Todas"] + sorted(resultado[col_empresa_df].dropna().astype(str).unique())
    empresa = st.selectbox("EMPRESA", empresas)

if empresa != "Todas":
    resultado = resultado[resultado[col_empresa_df] == empresa]

with c3:
    contratos = [""] + sorted(resultado[col_contrato_df].dropna().astype(str).unique())
    contrato = st.selectbox("CONTRATO", contratos)

# ================= EVOLUCION =================
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

# ================= AGRUPADO =================
agrupado = resultado.groupby(
    [col_contrato_df, col_descripcion_df],
    as_index=False
).agg({
    col_importe_total_df: "max",
    col_ejercido_df: "sum",
    col_abrir_importe_df: "sum"
})

agrupado = agrupado.rename(columns={
    col_contrato_df: "N° CONTRATO",
    col_descripcion_df: "DESCRIPCION",
    col_importe_total_df: "IMPORTE TOTAL (LC)",
    col_ejercido_df: "EJERCIDO",
    col_abrir_importe_df: "ABRIR IMPORTE (LC)"
})

st.dataframe(agrupado, use_container_width=True)

# ================= CLC =================
if contrato and col_contrato_clc:
    clc = df_clc[df_clc[col_contrato_clc].astype(str).str.strip() == str(contrato)].copy()

    if not clc.empty:
        if col_monto_clc and col_monto_clc in clc.columns:
            clc[col_monto_clc] = clc[col_monto_clc].apply(formato_pesos)

        if "PDF" in clc.columns:
            st.dataframe(
                clc,
                column_config={"PDF": st.column_config.LinkColumn("PDF")},
                use_container_width=True
            )
        else:
            st.dataframe(clc, use_container_width=True)
