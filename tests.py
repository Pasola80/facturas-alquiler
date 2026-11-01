# -*- coding: utf-8 -*-
"""Comprobaciones básicas de la lógica (se ejecutan en GitHub antes de compilar)."""
import tempfile
from pathlib import Path

import core

tmp = Path(tempfile.mkdtemp())
core.SALIDA = tmp / "facturas"
core.RUTA_ESTADO = tmp / "estado.json"
core.guardar_json(core.RUTA_ESTADO, {"base_tanda": {"2026": 10}})
cfg = core.cargar_config(core.BASE / "config.ejemplo.json")
cfg["cuenta_outlook"] = "prueba@outlook.com"

# Importes: base + IVA - IRPF, al céntimo
assert core.calcular(3087, 21, 19) == (308700, 64827, 58653, 314874)
assert core.calcular(2500, 21, 19)[3] == 255000
assert core.calcular(1029, 21, 19)[3] == 104958
assert core.calcular(675, 21, 19)[3] == 68850
assert core.euros(314874) == "3.148,74 €"

# Numeración
assert core.tanda_sugerida(2026) == 11
assert core.tanda_sugerida(2027) == 1

# Preparar
filas = core.importes_previstos(cfg, 2026, 11)
assert len(filas) == 3
tanda = core.preparar_tanda(cfg, 2026, 11, 11, {f["id"]: f["base"] for f in filas})
assert tanda["numero"] == "2026/L11"
for inv in tanda["facturas"]:
    pdf = core.carpeta_mes(2026, 11) / inv["pdf"]
    assert pdf.exists() and pdf.stat().st_size > 1500, pdf
assert core.tanda_sugerida(2026) == 12
# Repetir 'preparar' o borrar la carpeta y rehacerla no cambia el número
core.preparar_tanda(cfg, 2026, 11, 99, {f["id"]: f["base"] for f in filas})
assert core.cargar_tanda(2026, 11)["numero"] == "2026/L11"
import shutil
shutil.rmtree(core.carpeta_mes(2026, 11))
assert core.tanda_sugerida(2026) == 11
tanda = core.preparar_tanda(cfg, 2026, 11, 11, {f["id"]: f["base"] for f in filas})
assert tanda["numero"] == "2026/L11" and core.tanda_sugerida(2026) == 12

# Correos: 2 a arrendatarios (el tercero no recibe) + 3 copias
tanda, pend = core.correos_pendientes(cfg, 2026, 11)
tipos = [t for _, t, _ in pend]
assert tipos.count("arrendatario") == 2 and tipos.count("copia") == 3, tipos
for inv, tipo, msg in pend:
    adj = list(msg.iter_attachments())
    assert len(adj) == 1 and adj[0].get_content_type() == "application/pdf"
    if tipo == "copia":
        assert inv["nombre"] in msg["Subject"] and "noviembre 2026" in msg["Subject"]

# Marcar enviados y no repetir
for inv, tipo, _ in pend:
    core.marcar_enviado(2026, 11, inv["id"], tipo)
assert core.correos_pendientes(cfg, 2026, 11)[1] == []

print("todas las comprobaciones correctas")
