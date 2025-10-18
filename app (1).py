import os
import datetime as dt
from bson import ObjectId
import streamlit as st
import pymongo
import pandas as pd

# =======================
# CONFIGURACIÓN
# =======================
MONGODB_URI = st.secrets["app"]["MONGODB_URI"]
if not MONGODB_URI:
    st.error("❌ Falta MONGODB_URI en st.secrets['app']['MONGODB_URI']")
    st.stop()

client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
client.admin.command("ping")
db = client["empresa_db"]

trabajadores = db["trabajadores"]
departamentos = db["departamentos"]
cargos = db["cargos"]
sedes = db["sedes"]

st.set_page_config(page_title="CRUD Trabajadores", page_icon="🧑‍💼", layout="wide")
st.title("🧑‍💼 CRUD de Trabajadores — MongoDB Atlas (empresa_db)")

# =======================
# UTILIDADES / CACHÉS
# =======================
@st.cache_data(ttl=60)
def get_catalogos():
    deps = list(departamentos.find({}, {"_id": 1, "nombre": 1, "codigo": 1}).sort("nombre", 1))
    crgs = list(cargos.find({}, {"_id": 1, "nombre": 1, "nivel": 1}).sort("nombre", 1))
    sds = list(sedes.find({}, {"_id": 1, "nombre": 1, "ciudad": 1}).sort("nombre", 1))
    dep_map = {str(d["_id"]): f'{d.get("nombre")} ({d.get("codigo")})' for d in deps}
    cargo_map = {str(c["_id"]): c.get("nombre") for c in crgs}
    sede_map = {str(s["_id"]): f'{s.get("nombre")} {("— " + s.get("ciudad")) if s.get("ciudad") else ""}' for s in sds}
    return deps, crgs, sds, dep_map, cargo_map, sede_map

def _date_input_to_dt(d):
    if not d:
        return None
    return dt.datetime(d.year, d.month, d.day)

def validar_trabajador(data: dict) -> tuple[bool, str]:
    obligatorios = ["doc_tipo", "doc_num", "nombres", "apellidos",
                    "id_departamento", "id_cargo", "id_sede",
                    "fecha_ingreso", "tipo_contrato", "estado"]
    for f in obligatorios:
        if data.get(f) in (None, "", []):
            return False, f"El campo obligatorio '{f}' está vacío."
    if data.get("doc_tipo") not in ["DNI", "CE", "PAS"]:
        return False, "doc_tipo debe ser uno de: DNI, CE, PAS."
    if data.get("tipo_contrato") not in ["Indeterminado", "Plazo Fijo", "Prácticas", "Outsourcing"]:
        return False, "tipo_contrato inválido."
    if data.get("estado") not in ["Activo", "Cesado", "Suspendido", "Vacaciones"]:
        return False, "estado inválido."
    if data.get("sueldo_mensual") is not None:
        try:
            if float(data["sueldo_mensual"]) < 0:
                return False, "sueldo_mensual no puede ser negativo."
        except Exception:
            return False, "sueldo_mensual debe ser numérico."
    return True, ""

def buscar_trabajadores(texto=None, estado=None, dep_id=None, page=1, per_page=10):
    from pymongo import ASCENDING
    filtro = {}
    if texto:
        filtro["$or"] = [
            {"nombres": {"$regex": texto, "$options": "i"}},
            {"apellidos": {"$regex": texto, "$options": "i"}},
            {"doc_num": {"$regex": texto, "$options": "i"}},
            {"correo": {"$regex": texto, "$options": "i"}},
            {"telefono": {"$regex": texto, "$options": "i"}},
        ]
    if estado and estado != "— Todos —":
        filtro["estado"] = estado
    if dep_id and dep_id != "— Todos —":
        from bson import ObjectId
        filtro["id_departamento"] = ObjectId(dep_id)

    total = trabajadores.count_documents(filtro)
    skip = max(0, (page - 1) * per_page)
    rows = list(
        trabajadores.find(filtro)
        .sort([("apellidos", 1), ("nombres", 1)])
        .skip(skip)
        .limit(per_page)
    )
    return rows, total

# =======================
# UI: TABS CRUD
# =======================
tabs = st.tabs(["👀 Listar/Buscar", "➕ Crear", "✏️ Actualizar", "🗑️ Eliminar"])

deps, crgs, sds, dep_map, cargo_map, sede_map = get_catalogos()

# Mapeos para selects
dep_options = {"— Selecciona —": None}
dep_options.update({dep_map[str(d["_id"])]: str(d["_id"]) for d in deps})
cargo_options = {"— Selecciona —": None}
cargo_options.update({cargo_map[str(c["_id"])]: str(c["_id"]) for c in crgs})
sede_options = {"— Selecciona —": None}
sede_options.update({sede_map[str(s["_id"])]: str(s["_id"]) for s in sds})

# -----------------------
# TAB LISTAR / BUSCAR
# -----------------------
with tabs[0]:
    st.subheader("Listado de trabajadores")
    colf1, colf2, colf3, colf4 = st.columns([2, 1.2, 1.5, 1])
    with colf1:
        txt = st.text_input("🔎 Buscar (nombre, apellidos, doc, correo, teléfono)", "", key="list_buscar")
    with colf2:
        estado_f = st.selectbox("Estado", ["— Todos —", "Activo", "Cesado", "Suspendido", "Vacaciones"], key="list_estado")
    with colf3:
        dep_f = st.selectbox("Departamento", ["— Todos —"] + [dep_map[str(d["_id"])] for d in deps], key="list_depto")
        dep_f_val = None
        if dep_f != "— Todos —":
            dep_f_val = [k for k, v in dep_map.items() if v == dep_f][0]
    with colf4:
        per_page = st.selectbox("Por página", [5, 10, 20, 50], index=1, key="list_per_page")

    page = st.number_input("Página", min_value=1, value=1, step=1, key="list_page")
    resultados, total = buscar_trabajadores(texto=txt, estado=estado_f, dep_id=dep_f_val, page=page, per_page=per_page)
    st.caption(f"Total: {total} — Página {page}")

    if resultados:
        def row_to_view(r):
            return {
                "ID": str(r["_id"]),
                "Doc": f'{r.get("doc_tipo","")}-{r.get("doc_num","")}',
                "Nombres": r.get("nombres",""),
                "Apellidos": r.get("apellidos",""),
                "Correo": r.get("correo",""),
                "Teléfono": r.get("telefono",""),
                "Depto": dep_map.get(str(r.get("id_departamento")),""),
                "Cargo": cargo_map.get(str(r.get("id_cargo")),""),
                "Sede": sede_map.get(str(r.get("id_sede")),""),
                "Ingreso": r.get("fecha_ingreso").date().isoformat() if r.get("fecha_ingreso") else "",
                "Estado": r.get("estado",""),
                "Sueldo": r.get("sueldo_mensual","")
            }
        df = pd.DataFrame([row_to_view(r) for r in resultados])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay resultados con los filtros actuales.")

# -----------------------
# TAB CREAR
# -----------------------
with tabs[1]:
    st.subheader("Crear trabajador")
    with st.form("form_crear", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            doc_tipo = st.selectbox("Tipo de documento", ["DNI", "CE", "PAS"], key="crear_doc_tipo")
            doc_num = st.text_input("Número de documento", key="crear_doc_num")
            nombres = st.text_input("Nombres", key="crear_nombres")
        with c2:
            apellidos = st.text_input("Apellidos", key="crear_apellidos")
            correo = st.text_input("Correo", value="", key="crear_correo")
            telefono = st.text_input("Teléfono", value="", key="crear_telefono")
        with c3:
            genero = st.selectbox("Género", ["M", "F", "X", "—"], index=3, key="crear_genero")
            f_nac = st.date_input("Fecha de nacimiento", value=None, format="YYYY-MM-DD", key="crear_fnac")
            sueldo = st.text_input("Sueldo mensual (opcional)", value="", key="crear_sueldo")

        c4, c5, c6 = st.columns(3)
        with c4:
            dep = st.selectbox("Departamento", list(dep_options.keys()), key="crear_dep")
            dep_val = dep_options.get(dep)
        with c5:
            cargo = st.selectbox("Cargo", list(cargo_options.keys()), key="crear_cargo")
            cargo_val = cargo_options.get(cargo)
        with c6:
            sede = st.selectbox("Sede", list(sede_options.keys()), key="crear_sede")
            sede_val = sede_options.get(sede)

        c7, c8, c9 = st.columns(3)
        with c7:
            f_ing = st.date_input("Fecha de ingreso", value=dt.date.today(), format="YYYY-MM-DD", key="crear_fing")
        with c8:
            tipo_contrato = st.selectbox("Tipo de contrato", ["Indeterminado", "Plazo Fijo", "Prácticas", "Outsourcing"], key="crear_tipo_contrato")
        with c9:
            estado = st.selectbox("Estado", ["Activo", "Cesado", "Suspendido", "Vacaciones"], index=0, key="crear_estado")

        submitted = st.form_submit_button("Crear", use_container_width=True)
        if submitted:
            data = {
                "doc_tipo": doc_tipo,
                "doc_num": doc_num.strip(),
                "nombres": nombres.strip(),
                "apellidos": apellidos.strip(),
                "correo": correo.strip() or None,
                "telefono": telefono.strip() or None,
                "fecha_nacimiento": _date_input_to_dt(f_nac) if f_nac else None,
                "genero": None if genero == "—" else genero,
                "id_departamento": ObjectId(dep_val) if dep_val else None,
                "id_cargo": ObjectId(cargo_val) if cargo_val else None,
                "id_sede": ObjectId(sede_val) if sede_val else None,
                "fecha_ingreso": _date_input_to_dt(f_ing),
                "tipo_contrato": tipo_contrato,
                "sueldo_mensual": float(sueldo) if sueldo else None,
                "estado": estado
            }
            ok, msg = validar_trabajador(data)
            if not ok:
                st.error(f"❌ {msg}")
            else:
                try:
                    trabajadores.insert_one(data)
                    st.success("✅ Trabajador creado.")
                    st.cache_data.clear()
                except pymongo.errors.DuplicateKeyError:
                    st.error("❌ Ya existe un trabajador con ese documento.")
                except Exception as e:
                    st.error(f"❌ Error al crear: {e}")

# -----------------------
# TAB ACTUALIZAR
# -----------------------
with tabs[2]:
    st.subheader("Actualizar trabajador")
    q = st.text_input("Buscar por nombre/apellidos/doc", "", key="upd_buscar")
    candidatos, _ = buscar_trabajadores(texto=q, per_page=20)
    if candidatos:
        opciones = {f'{c.get("apellidos","")}, {c.get("nombres","")} — {c.get("doc_tipo")}-{c.get("doc_num")}': str(c["_id"]) for c in candidatos}
        sel = st.selectbox("Selecciona un trabajador", ["— Selecciona —"] + list(opciones.keys()), key="upd_sel_trab")
        if sel != "— Selecciona —":
            _id = ObjectId(opciones[sel])
            t = trabajadores.find_one({"_id": _id})

            with st.form("form_update"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    doc_tipo_u = st.selectbox("Tipo de documento", ["DNI", "CE", "PAS"], index=["DNI","CE","PAS"].index(t.get("doc_tipo","DNI")), key="upd_doc_tipo")
                    doc_num_u = st.text_input("Número de documento", value=t.get("doc_num",""), key="upd_doc_num")
                    nombres_u = st.text_input("Nombres", value=t.get("nombres",""), key="upd_nombres")
                with c2:
                    apellidos_u = st.text_input("Apellidos", value=t.get("apellidos",""), key="upd_apellidos")
                    correo_u = st.text_input("Correo", value=t.get("correo","") or "", key="upd_correo")
                    telefono_u = st.text_input("Teléfono", value=t.get("telefono","") or "", key="upd_telefono")
                with c3:
                    gen_val = t.get("genero") if t.get("genero") in ["M","F","X"] else "—"
                    genero_u = st.selectbox("Género", ["M", "F", "X", "—"], index=["M","F","X","—"].index(gen_val), key="upd_genero")
                    fn = t.get("fecha_nacimiento")
                    f_nac_u = st.date_input("Fecha de nacimiento", value=(fn.date() if fn else None), format="YYYY-MM-DD", key="upd_fnac")
                    sueldo_u = st.text_input("Sueldo mensual (opcional)", value=str(t.get("sueldo_mensual","") or ""), key="upd_sueldo")

                c4, c5, c6 = st.columns(3)
                with c4:
                    dep_label = dep_map.get(str(t.get("id_departamento")), "— Selecciona —")
                    dep_u = st.selectbox("Departamento", list(dep_options.keys()), index=list(dep_options.keys()).index(dep_label) if dep_label in dep_options else 0, key="upd_dep")
                    dep_val_u = dep_options.get(dep_u)
                with c5:
                    cargo_label = cargo_map.get(str(t.get("id_cargo")), "— Selecciona —")
                    cargo_u = st.selectbox("Cargo", list(cargo_options.keys()), index=list(cargo_options.keys()).index(cargo_label) if cargo_label in cargo_options else 0, key="upd_cargo")
                    cargo_val_u = cargo_options.get(cargo_u)
                with c6:
                    sede_label = sede_map.get(str(t.get("id_sede")), "— Selecciona —")
                    sede_u = st.selectbox("Sede", list(sede_options.keys()), index=list(sede_options.keys()).index(sede_label) if sede_label in sede_options else 0, key="upd_sede")
                    sede_val_u = sede_options.get(sede_u)

                c7, c8, c9 = st.columns(3)
                with c7:
                    fi = t.get("fecha_ingreso")
                    f_ing_u = st.date_input("Fecha de ingreso", value=(fi.date() if fi else dt.date.today()), format="YYYY-MM-DD", key="upd_fing")
                with c8:
                    tipo_contrato_u = st.selectbox("Tipo de contrato", ["Indeterminado", "Plazo Fijo", "Prácticas", "Outsourcing"],
                                                   index=["Indeterminado","Plazo Fijo","Prácticas","Outsourcing"].index(t.get("tipo_contrato","Indeterminado")),
                                                   key="upd_tipo_contrato")
                with c9:
                    estado_u = st.selectbox("Estado", ["Activo", "Cesado", "Suspendido", "Vacaciones"],
                                            index=["Activo","Cesado","Suspendido","Vacaciones"].index(t.get("estado","Activo")),
                                            key="upd_estado")

                submitted_u = st.form_submit_button("Guardar cambios", use_container_width=True)
                if submitted_u:
                    data_u = {
                        "doc_tipo": doc_tipo_u,
                        "doc_num": doc_num_u.strip(),
                        "nombres": nombres_u.strip(),
                        "apellidos": apellidos_u.strip(),
                        "correo": correo_u.strip() or None,
                        "telefono": telefono_u.strip() or None,
                        "fecha_nacimiento": _date_input_to_dt(f_nac_u) if f_nac_u else None,
                        "genero": None if genero_u == "—" else genero_u,
                        "id_departamento": ObjectId(dep_val_u) if dep_val_u else None,
                        "id_cargo": ObjectId(cargo_val_u) if cargo_val_u else None,
                        "id_sede": ObjectId(sede_val_u) if sede_val_u else None,
                        "fecha_ingreso": _date_input_to_dt(f_ing_u),
                        "tipo_contrato": tipo_contrato_u,
                        "sueldo_mensual": float(sueldo_u) if sueldo_u else None,
                        "estado": estado_u
                    }
                    ok, msg = validar_trabajador(data_u)
                    if not ok:
                        st.error(f"❌ {msg}")
                    else:
                        try:
                            trabajadores.update_one({"_id": _id}, {"$set": data_u})
                            st.success("✅ Cambios guardados.")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"❌ Error al actualizar: {e}")
    else:
        st.info("Escribe algo en la búsqueda para listar candidatos a editar.")

# -----------------------
# TAB ELIMINAR
# -----------------------
with tabs[3]:
    st.subheader("Eliminar trabajador")
    qd = st.text_input("Buscar por nombre/apellidos/doc para eliminar", "", key="del_buscar")
    candidatos_d, _ = buscar_trabajadores(texto=qd, per_page=20)
    if candidatos_d:
        opciones_d = {f'{c.get("apellidos","")}, {c.get("nombres","")} — {c.get("doc_tipo")}-{c.get("doc_num")}': str(c["_id"]) for c in candidatos_d}
        sel_d = st.selectbox("Selecciona un trabajador", ["— Selecciona —"] + list(opciones_d.keys()), key="del_sel_trab")
        if sel_d != "— Selecciona —":
            _id_d = ObjectId(opciones_d[sel_d])
            st.warning("Esta acción eliminará el registro de forma permanente.")
            if st.button("🗑️ Confirmar eliminación", key="del_btn"):
                try:
                    trabajadores.delete_one({"_id": _id_d})
                    st.success("✅ Trabajador eliminado.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"❌ Error al eliminar: {e}")
    else:
        st.info("Escribe un término para listar candidatos a eliminar.")
