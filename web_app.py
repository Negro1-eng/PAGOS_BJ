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
        "sheet_id": "1q2cvx9FD1CW8XP_kZpsFvfKtu4QdrJPqKAZuueHRIW4",
        "folder_id": "1MQtSIS1l-nL0KLLgL46tmo83FJtq4XZJ"
    },
    "2026": {
        "sheet_id": "1-xq9SMUmxaDmCEmmMmahJa28wOHsuqoAgyly3HiNMNc/edit?gid=0#gid=0",
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

    # -------- SHEETS --------
    ws_contratos = client.open_by_key(sheet_id).get_worksheet(0)
    ws_evolucion = client.open_by_key(sheet_id).worksheet("Evolucion")
    ws_clc = client.open_by_key(sheet_id).worksheet("CLC_CONTRATOS")

    df_contratos = pd.DataFrame(ws_contratos.get_all_records())
    df_evolucion = pd.DataFrame(ws_evolucion.get_all_records())
    df_clc = pd.DataFrame(ws_clc.get_all_records())

    df_contratos.columns = df_contratos.columns.str.strip()
    df_evolucion.columns = df_evolucion.columns.str.strip()
    df_clc.columns = df_clc.columns.str.strip()

    # -------- DRIVE --------
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
    proyectos = ["Todos"] + sorted(df["DESC PROYECTO"].dropna().unique())
    st.selectbox("DESCRIPCION DE PROGRAMA", proyectos, key="proyecto")

with c2:
    empresas = ["Todas"] + sorted(df["EMPRESA"].dropna().unique())
    st.selectbox("EMPRESA", empresas, key="empresa")

resultado = df.copy()

if st.session_state.proyecto != "Todos":
    resultado = resultado[resultado["DESC PROYECTO"] == st.session_state.proyecto]

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

    evo = df_evolucion[df_evolucion["PROYECTO"] == st.session_state.proyecto]

    if not evo.empty:
        evo = evo.iloc[0]

        st.subheader("Evolución presupuestal del proyecto")

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Original", formato_pesos(evo["ORIGINAL"]))
        e2.metric("Modificado", formato_pesos(evo["MODIFICADO"]))
        e3.metric("Comprometido", formato_pesos(evo["COMPROMETIDO"]))
        e4.metric("Ejercido", formato_pesos(evo["EJERCIDO"]))

# ================= AGRUPAR =================

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

# ================= CONSUMO =================

st.header("Consumo del Contrato", anchor=False)

if st.session_state.contrato:

    df_contrato = agrupado[
        agrupado["N° CONTRATO"].astype(str) == st.session_state.contrato
    ]

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

    tabla = agrupado[[
        "N° CONTRATO",
        "DESCRIPCION",
        "Importe total (LC)",
        "% PAGADO",
        "% PENDIENTE POR EJERCER"
    ]].copy()

    tabla["Importe total (LC)"] = tabla["Importe total (LC)"].apply(formato_pesos)

    # 🔹 Si hay contrato seleccionado → mostrar colapsada
    if st.session_state.contrato:
        with st.expander("Resultados del proyecto / empresa", expanded=False):
            st.dataframe(tabla, use_container_width=True, height=300)

    # 🔹 Si NO hay contrato seleccionado → mostrar normal
    else:
        st.subheader("Resultados")
        st.dataframe(tabla, use_container_width=True, height=420)

else:
    st.info("No hay contratos disponibles para los filtros seleccionados.")

# ================= CLC =================

if st.session_state.contrato:

    st.header("CLC DEL CONTRATO", anchor=False)

    clc_contrato = df_clc[
        df_clc["CONTRATO"].astype(str) == st.session_state.contrato
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
        st.info("Este contrato no tiene CLC registrados")
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
