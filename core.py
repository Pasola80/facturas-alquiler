# -*- coding: utf-8 -*-
"""Lógica del programa de facturas de alquiler (PDF, correos, envío). Sin interfaz."""
import base64
import json
import smtplib
import ssl
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
SERVICIO_CLAVE = "facturas-alquiler"


class ErrorEnvio(Exception):
    """Error que se puede mostrar tal cual al usuario."""


def carpeta_base():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE = carpeta_base()
RUTA_CONFIG = BASE / "config.json"
RUTA_ESTADO = BASE / "estado.json"
SALIDA = BASE / "facturas"


# ---------------------------------------------------------------- utilidades
def leer_json(ruta, defecto=None):
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return defecto


def guardar_json(ruta, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_config(ruta=None):
    cfg = leer_json(ruta or RUTA_CONFIG)
    if cfg is None:
        raise ErrorEnvio("No encuentro el archivo config.json junto al programa.")
    return cfg


def centimos(importe):
    return int((Decimal(str(importe)) * 100).to_integral_value(ROUND_HALF_UP))


def calcular(base, iva, irpf):
    b = centimos(base)
    i = int((Decimal(b) * Decimal(str(iva)) / 100).to_integral_value(ROUND_HALF_UP))
    r = int((Decimal(b) * Decimal(str(irpf)) / 100).to_integral_value(ROUND_HALF_UP))
    return b, i, r, b + i - r


def euros(c):
    return f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d} €"


def sin_tildes(texto):
    t = unicodedata.normalize("NFD", texto)
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


def nombre_seguro(texto):
    s = "".join(ch if ch.isalnum() else "_" for ch in sin_tildes(texto))
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:30]


def fecha_texto(inv):
    y, m, d = inv["fecha"].split("-")
    lugar = (inv.get("lugar") or "").strip()
    return (f"{lugar} a " if lugar else "") + f"{d} de {MESES[int(m) - 1].upper()} de {y}"


def rellenar(plantilla, inv, cfg):
    return (plantilla.replace("{numero}", inv["numero"])
            .replace("{mes}", MESES[inv["mes"] - 1])
            .replace("{anio}", str(inv["anio"]))
            .replace("{arrendatario}", inv["nombre"])
            .replace("{emisor}", cfg.get("firma_correo", "")))


def lista_correos(texto):
    return [x.strip() for x in str(texto or "").replace(";", ",").split(",") if x.strip()]


def total_factura(inv):
    return calcular(inv["base"], inv["iva"], inv["irpf"])[3]


# ---------------------------------------------------------------------- PDF
def registrar_fuentes():
    candidatos = [("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
                  ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")]
    for n, b in candidatos:
        if Path(n).exists() and Path(b).exists():
            try:
                pdfmetrics.registerFont(TTFont("FacN", n))
                pdfmetrics.registerFont(TTFont("FacB", b))
                return "FacN", "FacB"
            except Exception:
                pass
    return "Helvetica", "Helvetica-Bold"


def hacer_pdf(inv, cfg, ruta):
    fn, fb = registrar_fuentes()
    W, H = A4
    L, R = 20 * mm, W - 20 * mm
    c = canvas.Canvas(str(ruta), pagesize=A4)
    c.setTitle(f"Factura {inv['numero']} - {inv['nombre']}")
    em = cfg["emisor"]
    y = H - 24 * mm

    c.setFont(fb, 12)
    c.drawString(L, y, em["nombre"].upper())
    c.setFont(fn, 10)
    ly = y - 6 * mm
    lineas = []
    if em.get("dni"):
        lineas.append("D.N.I.: " + em["dni"])
    if em.get("direccion"):
        lineas.append(em["direccion"] + ("   Tel.: " + em["telefono"] if em.get("telefono") else ""))
    if em.get("poblacion"):
        lineas.append(em["poblacion"])
    for t in lineas:
        for sub in simpleSplit(t, fn, 10, 80 * mm):
            c.drawString(L, ly, sub)
            ly -= 5 * mm

    rx, ry = 112 * mm, y
    c.setFont(fb, 10.5)
    for sub in simpleSplit(inv["nombre"].upper(), fb, 10.5, 78 * mm):
        c.drawString(rx, ry, sub)
        ry -= 5 * mm
    ry -= 1 * mm
    c.setFont(fn, 10)
    for parte in str(inv.get("direccion", "")).split("\n"):
        for sub in simpleSplit(parte, fn, 10, 78 * mm):
            c.drawString(rx, ry, sub)
            ry -= 5 * mm
    c.drawString(rx, ry, f"{inv['tipo_doc']}: {inv['num_doc']}")
    ry -= 5 * mm

    y = min(ly, ry) - 12 * mm
    c.setFont(fb, 11)
    c.drawString(L, y, "Nº Factura  " + inv["numero"])
    y -= 10 * mm
    c.setFont(fb, 10)
    if inv.get("concepto"):
        for sub in simpleSplit(inv["concepto"].upper(), fb, 10, R - L):
            c.drawString(L, y, sub)
            y -= 5 * mm
    c.setFont(fn, 10)
    for parte in str(inv.get("referencias", "")).split("\n"):
        if parte.strip():
            for sub in simpleSplit(parte.strip(), fn, 10, R - L):
                c.drawString(L, y, sub)
                y -= 5 * mm
    y -= 3 * mm
    c.setFont(fb, 10)
    c.drawString(L, y, "CORRESPONDIENTE AL MES: " + MESES[inv["mes"] - 1].upper())
    y -= 14 * mm

    b, i, r, total = calcular(inv["base"], inv["iva"], inv["irpf"])

    def linea(etiqueta, importe, negrita=False):
        nonlocal y
        c.setFont(fb if negrita else fn, 10.5)
        c.drawString(L, y, etiqueta)
        c.drawRightString(R, y, importe)
        if not negrita:
            x1 = L + c.stringWidth(etiqueta, fn, 10.5) + 2 * mm
            x2 = R - c.stringWidth(importe, fn, 10.5) - 2 * mm
            c.setDash(0.8, 2.6)
            c.setLineWidth(0.8)
            c.line(x1, y + 0.6 * mm, x2, y + 0.6 * mm)
            c.setDash()
        y -= 8 * mm

    linea("BASE IMPONIBLE", euros(b))
    linea(f"{inv['iva']:g}% I.V.A.", euros(i))
    linea(f"{inv['irpf']:g}% RETENCIÓN I.R.P.F.", euros(r))
    c.setLineWidth(0.8)
    c.line(L, y + 4 * mm, R, y + 4 * mm)
    y -= 2 * mm
    linea("TOTAL FACTURA", euros(total), True)

    y -= 8 * mm
    c.setFont(fb, 10)
    c.drawString(L, y, "FORMA DE PAGO:")
    y -= 6 * mm
    c.setFont(fn, 10)
    for sub in simpleSplit(inv.get("forma_pago", ""), fn, 10, R - L):
        c.drawString(L, y, sub)
        y -= 5 * mm
    y -= 10 * mm
    c.drawString(L, y, "Recibí:")
    y -= 22 * mm
    c.drawString(L, y, "Fdo.: " + em.get("firma", em["nombre"]))
    y -= 12 * mm
    c.drawString(L, y, fecha_texto(inv))
    c.showPage()
    c.save()


# ------------------------------------------------------------------ preparar
def carpeta_mes(y, m):
    return SALIDA / f"{y}-{m:02d}"


def cargar_tanda(y, m):
    return leer_json(carpeta_mes(y, m) / "tanda.json")


def tanda_sugerida(y):
    """Siguiente número: el mayor de las facturas que existen este año (o el inicial) más uno."""
    estado = leer_json(RUTA_ESTADO, {})
    base = int(estado.get("base_tanda", {}).get(str(y), 0))
    existentes = []
    if SALIDA.exists():
        for ruta in SALIDA.glob(f"{y}-*/tanda.json"):
            t = leer_json(ruta)
            if t:
                existentes.append(int(t["seq"]))
    return max([base] + existentes) + 1


def arrendatarios_activos(cfg):
    return [t for t in cfg["arrendatarios"] if t.get("activo", True)]


def importes_previstos(cfg, y, m):
    """Importes que se proponen para el mes (los de la tanda si ya existe)."""
    tanda = cargar_tanda(y, m)
    previas = {f["id"]: f for f in tanda["facturas"]} if tanda else {}
    res = []
    for t in arrendatarios_activos(cfg):
        inv = previas.get(t["id"])
        enviada = bool(inv and (inv.get("enviado_arrendatario") or inv.get("enviado_copia")))
        res.append({"id": t["id"], "nombre": t["nombre"],
                    "base": inv["base"] if inv else t["base"], "bloqueada": enviada})
    return res


def preparar_tanda(cfg, y, m, seq, importes):
    """Crea (o regenera) los PDF del mes. `importes` = {id_arrendatario: base}."""
    carpeta = carpeta_mes(y, m)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_tanda = carpeta / "tanda.json"
    tanda = leer_json(ruta_tanda) or {"anio": y, "mes": m, "seq": seq,
                                       "numero": f"{y}/L{seq}", "facturas": []}
    seq = tanda["seq"]
    previas = {f["id"]: f for f in tanda["facturas"]}
    iso = f"{y}-{m:02d}-{min(28, max(1, int(cfg.get('dia_emision', 1)))):02d}"
    nuevas = []
    for t in arrendatarios_activos(cfg):
        inv = previas.get(t["id"])
        if inv and (inv.get("enviado_arrendatario") or inv.get("enviado_copia")):
            nuevas.append(inv)
            continue
        inv = {
            "id": t["id"], "anio": y, "mes": m, "seq": seq, "numero": tanda["numero"],
            "nombre": t["nombre"], "tipo_doc": t["tipo_doc"], "num_doc": t["num_doc"],
            "direccion": t["direccion"], "concepto": t.get("concepto", ""),
            "referencias": t.get("referencias", ""),
            "base": float(importes.get(t["id"], t["base"])),
            "iva": cfg.get("iva", 21), "irpf": cfg.get("irpf", 19),
            "forma_pago": t.get("forma_pago", ""), "lugar": t.get("lugar", ""), "fecha": iso,
            "correos": t.get("correos", ""), "enviar_correo": t.get("enviar_correo", True),
            "pdf": f"{y}-L{seq}_{nombre_seguro(t['nombre'])}.pdf",
            "enviado_arrendatario": False, "enviado_copia": False,
        }
        hacer_pdf(inv, cfg, carpeta / inv["pdf"])
        nuevas.append(inv)
    tanda["facturas"] = nuevas
    guardar_json(ruta_tanda, tanda)
    return tanda


# -------------------------------------------------------------------- correo
def montar(cfg, inv, tipo, carpeta):
    if tipo == "arrendatario":
        para = lista_correos(inv.get("correos"))
        asunto = rellenar(cfg["correo"]["asunto"], inv, cfg)
        cuerpo = rellenar(cfg["correo"]["mensaje"], inv, cfg)
    else:
        para = lista_correos(cfg["correo_copia"]["para"])
        asunto = rellenar(cfg["correo_copia"]["asunto"], inv, cfg)
        cuerpo = rellenar(cfg["correo_copia"]["mensaje"], inv, cfg)
    msg = EmailMessage()
    msg["From"] = formataddr((cfg["remitente_nombre"], cfg["cuenta_outlook"] or "pendiente@outlook.com"))
    msg["To"] = ", ".join(para)
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    pdf = carpeta / inv["pdf"]
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)
    return msg


def correos_pendientes(cfg, y, m):
    """Lista de (inv, tipo, mensaje) que faltan por enviar de la tanda del mes."""
    tanda = cargar_tanda(y, m)
    if not tanda:
        return None, []
    carpeta = carpeta_mes(y, m)
    res = []
    for inv in tanda["facturas"]:
        if inv.get("enviar_correo", True) and lista_correos(inv.get("correos")) and not inv.get("enviado_arrendatario"):
            res.append((inv, "arrendatario", montar(cfg, inv, "arrendatario", carpeta)))
        if lista_correos(cfg["correo_copia"]["para"]) and not inv.get("enviado_copia"):
            res.append((inv, "copia", montar(cfg, inv, "copia", carpeta)))
    return tanda, res


def marcar_enviado(y, m, id_inv, tipo):
    tanda = cargar_tanda(y, m)
    for inv in tanda["facturas"]:
        if inv["id"] == id_inv:
            inv["enviado_arrendatario" if tipo == "arrendatario" else "enviado_copia"] = True
    guardar_json(carpeta_mes(y, m) / "tanda.json", tanda)


def clave_guardada(cuenta):
    try:
        import keyring
        return keyring.get_password(SERVICIO_CLAVE, cuenta)
    except Exception:
        return None


def guardar_clave(cuenta, clave):
    try:
        import keyring
        keyring.set_password(SERVICIO_CLAVE, cuenta, clave)
        return True
    except Exception:
        return False


def borrar_clave(cuenta):
    try:
        import keyring
        keyring.delete_password(SERVICIO_CLAVE, cuenta)
    except Exception:
        pass


def conectar(cfg, clave):
    cuenta = cfg.get("cuenta_outlook", "")
    if "@" not in cuenta:
        raise ErrorEnvio("Falta indicar la dirección de Outlook desde la que se envía (en Ajustes).")
    try:
        s = smtplib.SMTP(cfg.get("smtp_servidor", "smtp-mail.outlook.com"),
                         int(cfg.get("smtp_puerto", 587)), timeout=40)
        s.ehlo()
        s.starttls(context=ssl.create_default_context())
        s.ehlo()
        s.login(cuenta, clave)
        return s
    except smtplib.SMTPAuthenticationError as e:
        raise ErrorEnvio(
            "Outlook ha rechazado el inicio de sesión.\n\n"
            "Revisa que la contraseña de aplicación esté bien copiada y que la cuenta tenga "
            "la verificación en dos pasos activada. Puede que Microsoft ya no permita este "
            f"tipo de acceso en la cuenta.\n\nDetalle: {e}")
    except (smtplib.SMTPException, OSError) as e:
        raise ErrorEnvio(f"No se pudo conectar con el servidor de correo.\n\nDetalle: {e}")


# ---------------------------------------------------------------- Microsoft Graph
GRAPH_ENVIAR = "https://graph.microsoft.com/v1.0/me/sendMail"
GRAPH_AUTORIDAD = "https://login.microsoftonline.com/consumers"
GRAPH_PERMISOS = ["Mail.Send"]


def usa_graph(cfg):
    return bool(str(cfg.get("microsoft_client_id", "")).strip())


class EnvioGraph:
    """Envía correos con la cuenta Microsoft (inicio de sesión normal, sin contraseñas de aplicación).

    Tiene la misma interfaz mínima que smtplib.SMTP (send_message, quit)."""

    def __init__(self, cfg, ruta_cache=None):
        self.client_id = str(cfg["microsoft_client_id"]).strip()
        self.ruta_cache = Path(ruta_cache) if ruta_cache else BASE / "sesion_microsoft.json"
        self._app = None
        self._cache = None

    def _msal(self):
        if self._app is None:
            import msal
            self._cache = msal.SerializableTokenCache()
            if self.ruta_cache.exists():
                try:
                    self._cache.deserialize(self.ruta_cache.read_text(encoding="utf-8"))
                except Exception:
                    pass
            self._app = msal.PublicClientApplication(
                self.client_id, authority=GRAPH_AUTORIDAD, token_cache=self._cache)
        return self._app

    def _guardar_cache(self):
        if self._cache is not None and self._cache.has_state_changed:
            self.ruta_cache.write_text(self._cache.serialize(), encoding="utf-8")

    def _silencioso(self):
        app = self._msal()
        for cuenta in app.get_accounts():
            r = app.acquire_token_silent(GRAPH_PERMISOS, account=cuenta)
            if r and "access_token" in r:
                self._guardar_cache()
                return r
        return None

    def sesion_iniciada(self):
        try:
            return self._silencioso() is not None
        except Exception:
            return False

    def iniciar_sesion(self):
        """Abre el navegador para que la persona inicie sesión en Microsoft (solo la primera vez)."""
        try:
            if self._silencioso():
                return
            r = self._msal().acquire_token_interactive(
                GRAPH_PERMISOS, prompt="select_account", timeout=300)
        except Exception as e:
            raise ErrorEnvio(f"No se pudo iniciar sesión en Microsoft.\n\nDetalle: {e}")
        if not r or "access_token" not in r:
            detalle = (r or {}).get("error_description") or (r or {}).get("error") or "sin respuesta"
            raise ErrorEnvio(f"Microsoft no ha completado el inicio de sesión.\n\nDetalle: {detalle}")
        self._guardar_cache()

    def olvidar(self):
        try:
            self.ruta_cache.unlink()
        except OSError:
            pass

    def _token(self):
        r = self._silencioso()
        if not r:
            raise ErrorEnvio("La sesión con Microsoft ha caducado. Vuelve a intentarlo para iniciar sesión.")
        return r["access_token"]

    def _post(self, url, cabeceras, datos):
        req = urllib.request.Request(url, data=datos, headers=cabeceras, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace")[:500]
            raise ErrorEnvio(f"Microsoft rechazó el envío (código {e.code}).\n\nDetalle: {cuerpo}")
        except OSError as e:
            raise ErrorEnvio(f"No se pudo conectar con Microsoft.\n\nDetalle: {e}")

    def send_message(self, msg):
        datos = base64.b64encode(msg.as_bytes())
        self._post(GRAPH_ENVIAR, {"Authorization": f"Bearer {self._token()}",
                                  "Content-Type": "text/plain"}, datos)

    def quit(self):
        pass


# ------------------------------------------------------------- Outlook de escritorio
def usa_outlook(cfg):
    return str(cfg.get("metodo_envio", "")).strip().lower() == "outlook"


class EnvioOutlook:
    """Envía con el Outlook clásico instalado en el ordenador (ya tiene la sesión iniciada).

    Misma interfaz mínima que smtplib.SMTP (send_message, quit)."""

    def __init__(self, cfg, aplicacion=None):
        self.cuenta = str(cfg.get("cuenta_outlook", "")).strip()
        self._app = aplicacion

    def abrir(self):
        """Conecta con Outlook (lo abre si está cerrado) y localiza la cuenta de envío."""
        try:
            if self._app is None:
                import win32com.client
                self._app = win32com.client.Dispatch("Outlook.Application")
            self._cuenta_envio = self._buscar_cuenta()
        except ErrorEnvio:
            raise
        except Exception as e:
            raise ErrorEnvio(
                "No se pudo abrir Outlook.\n\nComprueba que tienes instalado el Outlook clásico "
                "(el de Office, con el icono azul) y que has entrado en él al menos una vez con tu cuenta."
                f"\n\nDetalle: {e}")

    def _buscar_cuenta(self):
        cuentas = list(self._app.Session.Accounts)
        direcciones = [str(getattr(c, "SmtpAddress", "")) for c in cuentas]
        if not self.cuenta:
            return None
        for c, d in zip(cuentas, direcciones):
            if d.lower() == self.cuenta.lower():
                return c
        raise ErrorEnvio(
            f"En Outlook no hay ninguna cuenta con la dirección {self.cuenta}.\n\n"
            "Cuentas que tiene Outlook: " + (", ".join(direcciones) or "ninguna") +
            "\n\nCorrige «cuenta_outlook» en Ajustes para que coincida con una de ellas.")

    def send_message(self, msg):
        if self._app is None:
            self.abrir()
        try:
            item = self._app.CreateItem(0)  # 0 = correo
            item.To = "; ".join(a.strip() for a in str(msg["To"]).split(",") if a.strip())
            if msg["Cc"]:
                item.CC = "; ".join(a.strip() for a in str(msg["Cc"]).split(",") if a.strip())
            item.Subject = str(msg["Subject"])
            cuerpo = msg.get_body(preferencelist=("plain",))
            item.Body = cuerpo.get_content() if cuerpo is not None else ""
            if self._cuenta_envio is not None:
                item.SendUsingAccount = self._cuenta_envio
            carpeta = Path(tempfile.mkdtemp())
            for adj in msg.iter_attachments():
                ruta = carpeta / adj.get_filename()
                ruta.write_bytes(adj.get_payload(decode=True))
                item.Attachments.Add(str(ruta))
            item.Send()
        except ErrorEnvio:
            raise
        except Exception as e:
            raise ErrorEnvio(f"Outlook no pudo enviar el correo.\n\nDetalle: {e}")

    def quit(self):
        pass


def mensaje_de_prueba(cfg):
    t = arrendatarios_activos(cfg)[0]
    hoy = date.today()
    inv = {"id": "prueba", "anio": hoy.year, "mes": hoy.month, "seq": 0, "numero": f"{hoy.year}/PRUEBA",
           "nombre": t["nombre"], "tipo_doc": t["tipo_doc"], "num_doc": t["num_doc"], "direccion": t["direccion"],
           "concepto": t.get("concepto", ""), "referencias": t.get("referencias", ""), "base": t["base"],
           "iva": cfg.get("iva", 21), "irpf": cfg.get("irpf", 19), "forma_pago": t.get("forma_pago", ""),
           "lugar": t.get("lugar", ""), "fecha": hoy.isoformat(), "pdf": "prueba.pdf"}
    carpeta = SALIDA / "prueba"
    carpeta.mkdir(parents=True, exist_ok=True)
    hacer_pdf(inv, cfg, carpeta / inv["pdf"])
    msg = EmailMessage()
    msg["From"] = formataddr((cfg["remitente_nombre"], cfg["cuenta_outlook"]))
    msg["To"] = cfg["cuenta_outlook"]
    msg["Subject"] = "Prueba del programa de facturas"
    msg.set_content("Si recibes este correo con el PDF adjunto, el envío funciona.\n\n"
                    "(Es una factura de ejemplo; no se envía a ningún arrendatario.)")
    msg.add_attachment((carpeta / inv["pdf"]).read_bytes(), maintype="application", subtype="pdf", filename="prueba.pdf")
    return msg
