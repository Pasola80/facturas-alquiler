# -*- coding: utf-8 -*-
"""Ventana principal del programa de facturas de alquiler."""
import os
import sys
import time
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

import core

F_NORMAL = ("Segoe UI", 12)
F_GRANDE = ("Segoe UI", 15, "bold")
F_TITULO = ("Segoe UI", 22, "bold")
VERDE = "#1d5c47"
VERDE_OSC = "#154435"
GRIS = "#e9eeeb"


def parse_importe(texto):
    t = str(texto).replace("€", "").replace(" ", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def abrir(ruta):
    try:
        os.startfile(str(ruta))  # solo Windows
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self, ruta_cfg=None):
        super().__init__()
        self.ruta_cfg = ruta_cfg or core.RUTA_CONFIG
        self.title("Facturas de alquiler")
        self.geometry("760x660")
        self.minsize(680, 600)
        self.configure(bg="white")
        hoy = date.today()

        tk.Label(self, text="Facturas de alquiler", font=F_TITULO, bg="white", fg=VERDE).pack(pady=(18, 4))
        tk.Label(self, text="Elige el mes y sigue los pasos 1 y 2.", font=F_NORMAL, bg="white").pack()

        fila = tk.Frame(self, bg="white")
        fila.pack(pady=14)
        tk.Label(fila, text="Mes:", font=F_NORMAL, bg="white").pack(side="left", padx=(0, 6))
        self.mes = ttk.Combobox(fila, values=[m.capitalize() for m in core.MESES], state="readonly",
                                width=12, font=F_NORMAL)
        self.mes.current(hoy.month - 1)
        self.mes.pack(side="left")
        tk.Label(fila, text="Año:", font=F_NORMAL, bg="white").pack(side="left", padx=(16, 6))
        self.anio = tk.Spinbox(fila, from_=2024, to=2100, width=6, font=F_NORMAL)
        self.anio.delete(0, "end")
        self.anio.insert(0, str(hoy.year))
        self.anio.pack(side="left")

        self.boton("1   Preparar las facturas", self.preparar)
        self.boton("2   Enviar los correos", self.enviar)

        pie = tk.Frame(self, bg="white")
        pie.pack(pady=(4, 6))
        for texto, cmd in (("Abrir carpeta de facturas", self.abrir_carpeta),
                           ("Probar el envío", self.prueba),
                           ("Ajustes", self.ajustes)):
            tk.Button(pie, text=texto, font=F_NORMAL, command=cmd, bg=GRIS, relief="flat",
                      padx=12, pady=6).pack(side="left", padx=5)

        marco = tk.Frame(self, bg="white")
        marco.pack(fill="both", expand=True, padx=18, pady=(4, 16))
        self.registro = tk.Text(marco, height=10, font=("Segoe UI", 11), bg="#f7f9f8", relief="flat",
                                wrap="word", state="disabled")
        barra = ttk.Scrollbar(marco, command=self.registro.yview)
        self.registro.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.registro.pack(side="left", fill="both", expand=True)
        self.log("Programa listo. Primero pulsa «1 Preparar las facturas».")

    # ----------------------------------------------------------------- utilidades
    def boton(self, texto, cmd):
        tk.Button(self, text=texto, font=F_GRANDE, command=cmd, bg=VERDE, fg="white",
                  activebackground=VERDE_OSC, activeforeground="white", relief="flat",
                  pady=14, cursor="hand2").pack(fill="x", padx=60, pady=7)

    def log(self, texto):
        self.registro.configure(state="normal")
        self.registro.insert("end", texto + "\n")
        self.registro.see("end")
        self.registro.configure(state="disabled")
        self.update_idletasks()

    def cfg(self):
        return core.cargar_config(self.ruta_cfg)

    def mes_sel(self):
        try:
            return int(self.anio.get()), self.mes.current() + 1
        except ValueError:
            messagebox.showerror("Año no válido", "Escribe el año con números, por ejemplo 2026.")
            return None

    def dialogo(self, titulo, ancho=640, alto=480):
        d = tk.Toplevel(self)
        d.title(titulo)
        d.geometry(f"{ancho}x{alto}")
        d.configure(bg="white")
        d.transient(self)
        d.grab_set()
        return d

    def abrir_carpeta(self):
        sel = self.mes_sel()
        if not sel:
            return
        carpeta = core.carpeta_mes(*sel)
        if carpeta.exists():
            abrir(carpeta)
        else:
            messagebox.showinfo("Todavía no hay facturas", "Este mes aún no tiene facturas preparadas.")

    # ------------------------------------------------------------------ preparar
    def preparar(self):
        sel = self.mes_sel()
        if not sel:
            return
        y, m = sel
        try:
            cfg = self.cfg()
            filas = core.importes_previstos(cfg, y, m)
        except Exception as e:
            messagebox.showerror("No se puede continuar", str(e))
            return
        tanda = core.cargar_tanda(y, m)
        d = self.dialogo(f"Facturas de {core.MESES[m - 1]} {y}", 680, 460)
        tk.Label(d, text=f"Facturas de {core.MESES[m - 1]} de {y}", font=("Segoe UI", 16, "bold"),
                 bg="white").pack(pady=(14, 6))

        cab = tk.Frame(d, bg="white")
        cab.pack(pady=4)
        tk.Label(cab, text="Número de factura:", font=F_NORMAL, bg="white").pack(side="left")
        tk.Label(cab, text=f"{y}/L", font=F_NORMAL, bg="white").pack(side="left", padx=(8, 0))
        seq_var = tk.StringVar(value=str(tanda["seq"] if tanda else core.tanda_sugerida(y)))
        e_seq = tk.Entry(cab, textvariable=seq_var, width=5, font=F_NORMAL,
                         state="disabled" if tanda else "normal")
        e_seq.pack(side="left")

        tk.Label(d, text="Importe (base imponible) de cada arrendatario. Cámbialo solo si este mes es distinto.",
                 font=("Segoe UI", 10), bg="white", wraplength=600).pack(pady=(10, 4))
        tabla = tk.Frame(d, bg="white")
        tabla.pack(pady=4, padx=24, fill="x")
        variables = {}
        for f in filas:
            r = tk.Frame(tabla, bg="white")
            r.pack(fill="x", pady=3)
            nombre = f["nombre"] + ("  (ya enviada)" if f["bloqueada"] else "")
            tk.Label(r, text=nombre, font=F_NORMAL, bg="white", anchor="w").pack(side="left")
            v = tk.StringVar(value=f"{f['base']:.2f}".replace(".", ","))
            variables[f["id"]] = v
            tk.Entry(r, textvariable=v, width=12, font=F_NORMAL, justify="right",
                     state="disabled" if f["bloqueada"] else "normal").pack(side="right")
            tk.Label(r, text="€", font=F_NORMAL, bg="white").pack(side="right", padx=(0, 4))

        def crear():
            try:
                seq = int(seq_var.get())
                importes = {k: parse_importe(v.get()) for k, v in variables.items()}
            except ValueError:
                messagebox.showerror("Dato no válido", "Revisa el número y los importes: deben ser números.", parent=d)
                return
            try:
                t = core.preparar_tanda(cfg, y, m, seq, importes)
            except Exception as e:
                messagebox.showerror("No se pudieron crear las facturas", str(e), parent=d)
                return
            d.destroy()
            self.log(f"\nFacturas {t['numero']} de {core.MESES[m - 1]} {y}:")
            suma = 0
            for inv in t["facturas"]:
                tot = core.total_factura(inv)
                suma += tot
                self.log(f"  {inv['nombre']}: {core.euros(tot)}")
            self.log(f"  Total del mes: {core.euros(suma)}")
            self.log("Revisa los PDF y, si están bien, pulsa «2 Enviar los correos».")
            abrir(core.carpeta_mes(y, m))
            messagebox.showinfo("Facturas creadas",
                                "Ya están las facturas.\n\nSe ha abierto la carpeta con los PDF para que los revises.\n"
                                "Si están bien, pulsa el botón «2 Enviar los correos».")

        bt = tk.Frame(d, bg="white")
        bt.pack(side="bottom", pady=16)
        tk.Button(bt, text="Crear las facturas", font=F_GRANDE, bg=VERDE, fg="white", relief="flat",
                  padx=18, pady=8, command=crear).pack(side="left", padx=8)
        tk.Button(bt, text="Cancelar", font=F_NORMAL, bg=GRIS, relief="flat", padx=14, pady=8,
                  command=d.destroy).pack(side="left", padx=8)

    # ------------------------------------------------------------------- cuenta
    def asegurar_cuenta(self):
        cfg = self.cfg()
        if "@" in cfg.get("cuenta_outlook", ""):
            return cfg["cuenta_outlook"]
        d = self.dialogo("Cuenta de Outlook", 560, 240)
        tk.Label(d, text="¿Desde qué dirección de Outlook se envían los correos?", font=F_NORMAL,
                 bg="white", wraplength=500).pack(pady=(20, 8))
        var = tk.StringVar()
        e = tk.Entry(d, textvariable=var, width=36, font=F_NORMAL)
        e.pack(pady=6)
        e.focus_set()
        res = {"v": None}

        def ok():
            v = var.get().strip()
            if "@" not in v:
                messagebox.showerror("Dirección no válida", "Escribe la dirección completa, por ejemplo nombre@outlook.com", parent=d)
                return
            res["v"] = v
            d.destroy()

        tk.Button(d, text="Guardar", font=F_GRANDE, bg=VERDE, fg="white", relief="flat", padx=20,
                  pady=6, command=ok).pack(pady=14)
        self.wait_window(d)
        if res["v"]:
            cfg["cuenta_outlook"] = res["v"]
            core.guardar_json(self.ruta_cfg, cfg)
        return res["v"]

    def pedir_clave(self, cuenta):
        guardada = core.clave_guardada(cuenta)
        if guardada:
            return guardada, False
        d = self.dialogo("Contraseña de aplicación", 600, 320)
        tk.Label(d, text=f"Escribe la contraseña de aplicación de\n{cuenta}", font=F_NORMAL, bg="white").pack(pady=(20, 8))
        var = tk.StringVar()
        e = tk.Entry(d, textvariable=var, show="•", width=34, font=F_NORMAL)
        e.pack(pady=6)
        e.focus_set()
        rec = tk.BooleanVar(value=True)
        tk.Checkbutton(d, text="Recordarla en este ordenador", variable=rec, font=F_NORMAL, bg="white").pack(pady=4)
        res = {"v": None}

        def ok():
            res["v"] = var.get().strip().replace(" ", "")
            d.destroy()

        tk.Button(d, text="Continuar", font=F_GRANDE, bg=VERDE, fg="white", relief="flat", padx=20,
                  pady=6, command=ok).pack(pady=14)
        self.wait_window(d)
        return res["v"], bool(res["v"]) and rec.get()

    def iniciar_sesion(self):
        """Devuelve el servidor de envío o None si se cancela o falla."""
        cuenta = self.asegurar_cuenta()
        if not cuenta:
            return None
        cfg = self.cfg()
        if core.usa_outlook(cfg):
            srv = core.EnvioOutlook(cfg)
            self.log("Conectando con Outlook…")
            self.update()
            try:
                srv.abrir()
            except core.ErrorEnvio as e:
                self.log("No se pudo abrir Outlook.")
                messagebox.showerror("No se pudo enviar", str(e))
                return None
            return srv
        if core.usa_graph(cfg):
            return self.iniciar_sesion_microsoft(cfg)
        clave, recordar = self.pedir_clave(cuenta)
        if not clave:
            return None
        self.log("Conectando con Outlook…")
        try:
            srv = core.conectar(cfg, clave)
        except core.ErrorEnvio as e:
            core.borrar_clave(cuenta)
            self.log("No se pudo iniciar sesión.")
            messagebox.showerror("No se pudo enviar", str(e))
            return None
        if recordar:
            core.guardar_clave(cuenta, clave)
        return srv

    def iniciar_sesion_microsoft(self, cfg):
        srv = core.EnvioGraph(cfg)
        if not srv.sesion_iniciada():
            messagebox.showinfo(
                "Iniciar sesión en Microsoft",
                "Ahora se abrirá el navegador con la página de Microsoft.\n\n"
                "Inicia sesión con tu cuenta de Outlook y pulsa «Sí» o «Aceptar» cuando te pida permiso "
                "para enviar correos.\n\nSolo hace falta la primera vez.")
            self.log("Esperando el inicio de sesión en el navegador…")
            self.update()
            try:
                srv.iniciar_sesion()
            except core.ErrorEnvio as e:
                self.log("No se pudo iniciar sesión.")
                messagebox.showerror("No se pudo enviar", str(e))
                return None
        self.log("Sesión de Microsoft lista.")
        return srv

    # -------------------------------------------------------------------- enviar
    def enviar(self):
        sel = self.mes_sel()
        if not sel:
            return
        y, m = sel
        try:
            if not self.asegurar_cuenta():
                return
            cfg = self.cfg()
            tanda, pend = core.correos_pendientes(cfg, y, m)
        except Exception as e:
            messagebox.showerror("No se puede continuar", str(e))
            return
        if tanda is None:
            messagebox.showinfo("Primero prepara las facturas",
                                f"Todavía no hay facturas de {core.MESES[m - 1]} {y}.\nPulsa antes «1 Preparar las facturas».")
            return
        if not pend:
            messagebox.showinfo("Todo enviado", "No queda ningún correo por enviar de este mes.")
            return
        d = self.dialogo("Correos que se van a enviar", 760, 560)
        tk.Label(d, text=f"Se van a enviar {len(pend)} correos", font=("Segoe UI", 16, "bold"), bg="white").pack(pady=(14, 4))
        tk.Label(d, text="Cada uno lleva su factura en PDF adjunta.", font=F_NORMAL, bg="white").pack()
        txt = tk.Text(d, font=("Segoe UI", 11), height=16, wrap="word", bg="#f7f9f8", relief="flat")
        for n, (inv, tipo, msg) in enumerate(pend, 1):
            etiqueta = "Al arrendatario" if tipo == "arrendatario" else "Copia para tu suegro"
            txt.insert("end", f"{n}. {etiqueta}\n   Para: {msg['To']}\n   Asunto: {msg['Subject']}\n\n")
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=18, pady=10)

        def confirmar():
            d.destroy()
            self.hacer_envio(y, m, pend)

        bt = tk.Frame(d, bg="white")
        bt.pack(pady=12)
        tk.Button(bt, text=f"Enviar los {len(pend)} correos", font=F_GRANDE, bg=VERDE, fg="white", relief="flat",
                  padx=18, pady=8, command=confirmar).pack(side="left", padx=8)
        tk.Button(bt, text="Cancelar", font=F_NORMAL, bg=GRIS, relief="flat", padx=14, pady=8,
                  command=d.destroy).pack(side="left", padx=8)

    def hacer_envio(self, y, m, pend):
        srv = self.iniciar_sesion()
        if not srv:
            return
        enviados, fallos = 0, []
        for inv, tipo, msg in pend:
            try:
                srv.send_message(msg)
                core.marcar_enviado(y, m, inv["id"], tipo)
                enviados += 1
                self.log(f"  Enviado: {msg['Subject']}  →  {msg['To']}")
            except Exception as e:
                fallos.append(f"{msg['Subject']}: {e}")
                self.log(f"  ERROR: {msg['Subject']}")
            self.update()
            time.sleep(1)
        try:
            srv.quit()
        except Exception:
            pass
        if fallos:
            messagebox.showwarning("Algunos correos no se enviaron",
                                   f"Se enviaron {enviados} de {len(pend)}.\n\nNo salieron:\n" + "\n".join(fallos) +
                                   "\n\nVuelve a pulsar «2 Enviar los correos» para reintentar solo los que faltan.")
        else:
            messagebox.showinfo("Hecho", f"Se enviaron los {enviados} correos.")

    # -------------------------------------------------------------------- prueba
    def prueba(self):
        try:
            if not self.asegurar_cuenta():
                return
            cfg = self.cfg()
            msg = core.mensaje_de_prueba(cfg)
        except Exception as e:
            messagebox.showerror("No se puede continuar", str(e))
            return
        srv = self.iniciar_sesion()
        if not srv:
            return
        try:
            srv.send_message(msg)
            srv.quit()
        except Exception as e:
            messagebox.showerror("No se pudo enviar", str(e))
            return
        self.log(f"Correo de prueba enviado a {cfg['cuenta_outlook']}.")
        messagebox.showinfo("Prueba enviada",
                            f"Se ha enviado un correo de prueba a {cfg['cuenta_outlook']}.\n"
                            "Mira la bandeja de entrada (y el correo no deseado). Si llega con el PDF, todo funciona.")

    # ------------------------------------------------------------------- ajustes
    def ajustes(self):
        d = self.dialogo("Ajustes", 600, 330)
        tk.Label(d, text="Ajustes", font=("Segoe UI", 16, "bold"), bg="white").pack(pady=(16, 10))

        def editar():
            abrir(self.ruta_cfg)
            messagebox.showinfo("Archivo abierto",
                                "Se ha abierto config.json en el Bloc de notas.\n"
                                "Cambia lo que necesites, guarda y ciérralo. No hace falta reiniciar el programa.", parent=d)

        def olvidar():
            cuenta = self.cfg().get("cuenta_outlook", "")
            core.borrar_clave(cuenta)
            if core.usa_graph(self.cfg()):
                core.EnvioGraph(self.cfg()).olvidar()
            messagebox.showinfo("Hecho", "La sesión y la contraseña guardadas se han borrado de este ordenador.", parent=d)

        tk.Button(d, text="Editar arrendatarios, importes y correos", font=F_NORMAL, bg=GRIS, relief="flat",
                  padx=14, pady=8, command=editar).pack(pady=6)
        tk.Button(d, text="Cerrar la sesión guardada", font=F_NORMAL, bg=GRIS, relief="flat",
                  padx=14, pady=8, command=olvidar).pack(pady=6)
        tk.Button(d, text="Cerrar", font=F_NORMAL, bg=GRIS, relief="flat", padx=14, pady=8,
                  command=d.destroy).pack(pady=14)


def main():
    humo = os.environ.get("FACTURAS_SMOKE")
    ruta = core.BASE / "config.ejemplo.json" if humo else core.RUTA_CONFIG
    if not ruta.exists():
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror("Falta el archivo config.json",
                             "No encuentro config.json.\n\nCópialo en la misma carpeta que este programa y ábrelo de nuevo.")
        return 1
    app = App(ruta)
    if humo:
        app.update()
        app.destroy()
        print("humo ok")
        return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
