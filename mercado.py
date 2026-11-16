# -*- coding: utf-8 -*-
"""
POE 2 Builder Check - buscador de mejoras en el mercado oficial de PoE 2.

Ventana:   pythonw mercado.py
Consola:   python mercado.py anillo 100            (slot y presupuesto en divines)
           python mercado.py anillo 500 exalted

Busca items del slot dentro del presupuesto, los puntua con las mismas reglas
que poe2_checker.py (pesos.json) y muestra los mejores que superan a la pieza
que llevas puesta (carpeta equipo/). Solo usa la libreria estandar.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import poe2_checker as motor

BASE = motor.BASE
API = "https://www.pathofexile.com/api/trade2"
WEB = "https://www.pathofexile.com/trade2/search/poe2"
CONFIG = os.path.join(BASE, "config.json")
MERCADO = os.path.join(BASE, "mercado.json")
CACHE_STATS = os.path.join(BASE, "cache_stats.json")

CONFIG_DEFECTO = {
    "liga": "Forbidden Rites",
    "poesessid": "",
    "estado": "any",
    "pausa_segundos": 2.5,
    "items_a_revisar": 30,
    "mostrar": 5,
    "user_agent": "poe2-builder-check/0.1 (github.com/ogonzalezf/poe2-builder-check)"
}


class ErrorMercado(Exception):
    pass


# ---------------------------------------------------------------- configuracion
def cargar_config():
    cfg = dict(CONFIG_DEFECTO)
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    else:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    return cfg


def cargar_mercado():
    with open(MERCADO, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- red
_ultima = [0.0]


def http(cfg, metodo, ruta, cuerpo=None, reintento=True):
    espera = cfg["pausa_segundos"] - (time.time() - _ultima[0])
    if espera > 0:
        time.sleep(espera)
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(API + ruta, data=datos, method=metodo)
    req.add_header("User-Agent", cfg["user_agent"])
    req.add_header("Accept", "application/json")
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    if cfg.get("poesessid"):
        req.add_header("Cookie", "POESESSID=" + cfg["poesessid"])
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _ultima[0] = time.time()
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        _ultima[0] = time.time()
        texto = e.read().decode("utf-8", "replace")[:400]
        if e.code == 429 and reintento:
            seg = min(int(e.headers.get("Retry-After", "10") or 10), 90)
            time.sleep(seg + 1)
            return http(cfg, metodo, ruta, cuerpo, reintento=False)
        if e.code in (401, 403):
            raise ErrorMercado("El mercado rechazo la consulta (HTTP %d). Puede que pida iniciar sesion: "
                               "pon tu cookie POESESSID en config.json.\n%s" % (e.code, texto))
        if e.code == 429:
            raise ErrorMercado("Demasiadas consultas seguidas. Espera un minuto y vuelve a intentar.")
        raise ErrorMercado("Error del mercado (HTTP %d) en %s:\n%s" % (e.code, ruta, texto))
    except urllib.error.URLError as e:
        raise ErrorMercado("No se pudo conectar con el mercado: %s" % e.reason)


def liga_id(cfg):
    """Busca en la lista oficial la liga cuyo nombre contiene el de config.json."""
    quiero = cfg["liga"].lower()
    try:
        ligas = http(cfg, "GET", "/data/leagues").get("result", [])
    except ErrorMercado:
        return cfg["liga"]
    poe2 = [l for l in ligas if l.get("realm", "poe2") == "poe2"]
    for l in poe2:
        if l["id"].lower() == quiero:
            return l["id"]
    hc = ("hc" in quiero.split()) or ("hardcore" in quiero)
    for l in poe2:
        nombre = l["id"].lower()
        es_hc = "hc " in nombre + " " or "hardcore" in nombre
        if quiero in nombre and es_hc == hc:
            return l["id"]
    return cfg["liga"]


# ---------------------------------------------------------------- stats del mercado
def quitar_marcas(t):
    """'[Resistances|Fire Resistance]' -> 'Fire Resistance'."""
    return re.sub(r"\[(?:[^\]|]*\|)?([^\]]*)\]", r"\1", t)


def norm(t):
    t = quitar_marcas(t).lower()
    t = re.sub(r"[+#%]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def cargar_stats(cfg):
    datos = None
    if os.path.exists(CACHE_STATS) and time.time() - os.path.getmtime(CACHE_STATS) < 7 * 86400:
        with open(CACHE_STATS, encoding="utf-8") as f:
            datos = json.load(f)
    if datos is None:
        datos = http(cfg, "GET", "/data/stats")
        with open(CACHE_STATS, "w", encoding="utf-8") as f:
            json.dump(datos, f)
    indice = {}
    for grupo in datos.get("result", []):
        for e in grupo.get("entries", []):
            tipo = e.get("type") or e["id"].split(".")[0]
            indice.setdefault(norm(e["text"]), {})[tipo] = e["id"]
    return indice


def id_stat(indice, texto):
    tipos = indice.get(norm(texto))
    if not tipos:
        return None
    for t in ("pseudo", "explicit"):
        if t in tipos:
            return tipos[t]
    return None


# ---------------------------------------------------------------- consulta
def construir_consulta(grupo_id, precio_max, moneda, cfg, mer, pesos, indice, max_filtros=99):
    gm = mer["grupos"][grupo_id]
    grupo = pesos["grupos"][grupo_id]
    avisos = []
    filtros_peso = []
    por_stat = []
    for sid, regla in grupo["pesos"].items():
        stat = pesos["stats"][sid]
        peso = regla[0] if isinstance(regla, list) else regla
        bueno = regla[1] if isinstance(regla, list) and len(regla) > 1 else stat["bueno"]
        opciones = mer["stats"].get(sid)
        if not opciones:
            continue                      # stat que solo se evalua al puntuar (base, evasion, etc.)
        hecho = False
        for opcion in opciones:
            ids = [(id_stat(indice, texto), mult) for texto, mult in opcion]
            ids = [(i, m) for i, m in ids if i]
            if ids:
                por_stat.append((peso, stat["nombre"], [
                    {"id": i, "value": {"weight": round(peso * m / float(bueno), 4)}} for i, m in ids]))
                hecho = True
                break
        if not hecho:
            avisos.append("El mercado no reconoce el stat '%s'; no se uso para ordenar." % stat["nombre"])

    # el mercado limita cuantos filtros admite: entran primero los stats de mas peso
    por_stat.sort(key=lambda t: -t[0])
    fuera = []
    for peso, nombre, filtros in por_stat:
        if len(filtros_peso) + len(filtros) <= max_filtros:
            filtros_peso += filtros
        else:
            fuera.append(nombre)
    if fuera:
        avisos.append("Por el limite del mercado, la busqueda no ordeno por: %s (si cuentan en la nota)."
                      % ", ".join(fuera))

    q = {"status": {"option": cfg["estado"]}, "filters": {}}
    q["filters"]["trade_filters"] = {"filters": {"price": {"max": precio_max, "option": moneda}}}
    if gm.get("nombre_unico"):
        q["name"] = gm["nombre_unico"]
    else:
        q["filters"]["type_filters"] = {"filters": {"category": {"option": gm["categoria"]}}}
    if gm.get("ev_min"):
        q["filters"]["equipment_filters"] = {"filters": {"ev": {"min": gm["ev_min"]}}}
    cuerpo = {"query": q, "sort": {"price": "asc"}}
    if filtros_peso:
        q["stats"] = [{"type": "weight", "filters": filtros_peso, "value": {"min": 0.01}}]
        cuerpo["sort"] = {"statgroup.0": "desc"}
    return cuerpo, avisos


# ---------------------------------------------------------------- resultados
def item_a_texto(it, clase):
    """Convierte un item del mercado al mismo formato de texto que copia el juego."""
    L = ["Item Class: " + clase, "Rarity: " + it.get("rarity", "Rare")]
    if it.get("name"):
        L.append(it["name"])
    L.append(it.get("typeLine") or it.get("baseType") or "?")
    props = []
    for p in it.get("properties", []) or []:
        vals = p.get("values") or []
        if vals:
            props.append("%s: %s" % (quitar_marcas(p["name"]), vals[0][0]))
    if props:
        L += [motor.SEP] + props
    for campo, marca in (("enchantMods", " (enchant)"), ("implicitMods", " (implicit)"), ("runeMods", " (rune)")):
        mods = it.get(campo) or []
        if mods:
            L += [motor.SEP] + [quitar_marcas(m) + marca for m in mods]
    explicitos = []
    for campo in ("explicitMods", "fracturedMods", "desecratedMods", "craftedMods"):
        explicitos += [quitar_marcas(m) for m in (it.get(campo) or [])]
    if explicitos:
        L += [motor.SEP] + explicitos
    if it.get("corrupted"):
        L += [motor.SEP, "Corrupted"]
    return "\n".join(L)


def equipo_actual(grupo_id, mer, pesos):
    """Puntua lo que llevas puesto en ese slot. Devuelve lista de (nombre, nota, puntos)."""
    actual = []
    for archivo in mer["grupos"][grupo_id].get("equipo", []):
        ruta = os.path.join(BASE, "equipo", archivo)
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as f:
            item = motor.parse_item(f.read())
        if item:
            res = motor.puntuar(item, pesos)
            actual.append((item["nombre"], res["nota"], res["puntos"]))
    return actual


def buscar(grupo_id, precio_max, moneda="divine", log=lambda m: None):
    cfg = cargar_config()
    mer = cargar_mercado()
    pesos = motor.cargar_pesos()
    if grupo_id not in mer["grupos"]:
        raise ErrorMercado("Slot desconocido: %s. Opciones: %s" % (grupo_id, ", ".join(mer["grupos"])))
    grupo = pesos["grupos"][grupo_id]
    clase = (grupo.get("clases") or ["?"])[0]

    log("Leyendo la lista de stats del mercado...")
    indice = cargar_stats(cfg)
    liga = liga_id(cfg)
    log("Buscando en la liga '%s'..." % liga)
    r = None
    for max_filtros in (cfg.get("max_filtros", 8), 6, 4, 3, 2, 1):
        cuerpo, avisos = construir_consulta(grupo_id, precio_max, moneda, cfg, mer, pesos, indice, max_filtros)
        try:
            r = http(cfg, "POST", "/search/poe2/" + urllib.parse.quote(liga), cuerpo)
            break
        except ErrorMercado as e:
            if "too complex" not in str(e).lower():
                raise
            log("El mercado pide una busqueda mas simple; reintento con menos filtros (%d)..." % max_filtros)
    if r is None:
        raise ErrorMercado("El mercado rechaza la busqueda por compleja incluso con un solo filtro. "
                           "Iniciar sesion sube ese limite: pon tu cookie POESESSID en config.json.")
    ids = r.get("result", [])[:cfg["items_a_revisar"]]
    out = {"liga": liga, "total": r.get("total", len(ids)), "avisos": avisos, "resultados": [],
           "url": "%s/%s/%s" % (WEB, urllib.parse.quote(liga), r.get("id", "")),
           "actual": equipo_actual(grupo_id, mer, pesos), "consejo": grupo.get("consejo", "")}

    for i in range(0, len(ids), 10):
        log("Descargando items %d-%d de %d..." % (i + 1, min(i + 10, len(ids)), len(ids)))
        lote = http(cfg, "GET", "/fetch/%s?query=%s&realm=poe2" % (",".join(ids[i:i + 10]), r.get("id", "")))
        for x in lote.get("result", []):
            if not x or not x.get("item"):
                continue
            item = motor.parse_item(item_a_texto(x["item"], clase))
            if not item:
                continue
            res = motor.puntuar(item, pesos)
            precio = (x.get("listing") or {}).get("price") or {}
            out["resultados"].append({
                "nombre": item["nombre"], "nota": res["nota"], "puntos": res["puntos"],
                "aportes": res["aportes"], "sobran": res["sobran"], "avisos": res["avisos"],
                "precio": precio.get("amount"), "moneda": precio.get("currency", ""),
                "vendedor": ((x.get("listing") or {}).get("account") or {}).get("name", "?"),
            })
    out["resultados"].sort(key=lambda d: (-d["puntos"], d["precio"] if d["precio"] is not None else 1e18))
    return out


def informe(out, mostrar=5):
    L = []
    if out["actual"]:
        L.append("LO QUE LLEVAS PUESTO")
        for nombre, nota, _ in out["actual"]:
            L.append("  %s/10  %s" % (nota, nombre))
    base = min([p for _, _, p in out["actual"]], default=0.0)
    mejores = [d for d in out["resultados"] if d["puntos"] > base + 0.005]
    L.append("")
    L.append("Liga: %s - %d items encontrados, %d revisados, %d mejoran tu pieza%s"
             % (out["liga"], out["total"], len(out["resultados"]), len(mejores),
                " mas floja" if len(out["actual"]) > 1 else ""))
    for a in out["avisos"]:
        L.append("  ! " + a)
    if not mejores:
        L.append("")
        L.append("Ninguno de los revisados mejora lo que llevas con ese presupuesto.")
    for n, d in enumerate(mejores[:mostrar], 1):
        precio = "%s %s" % (("%g" % d["precio"]) if d["precio"] is not None else "?", d["moneda"])
        L.append("")
        L.append("%d. %s/10  %s  -  %s  (vendedor: %s)" % (n, d["nota"], d["nombre"], precio, d["vendedor"]))
        for a in d["avisos"]:
            L.append("     ! " + a)
        for aporte, nombre, valor, frac in d["aportes"]:
            L.append("     + %s: %.0f (%d%%)" % (nombre, valor, frac * 100))
        for s in d["sobran"][:4]:
            L.append("     - " + s)
    L.append("")
    L.append("Guia: " + out["consejo"])
    L.append("Ver y comprar en el navegador: " + out["url"])
    return "\n".join(L)


# ---------------------------------------------------------------- ventana
def main_ventana():
    import threading
    import tkinter as tk
    import webbrowser
    from tkinter import ttk

    mer = cargar_mercado()
    slots = list(mer["grupos"].keys())
    nombres = [mer["grupos"][s]["nombre"] for s in slots]

    root = tk.Tk()
    root.title("POE 2 Builder Check - Mercado")
    root.geometry("760x560")
    barra = tk.Frame(root, padx=8, pady=8)
    barra.pack(fill="x")
    tk.Label(barra, text="Slot").pack(side="left")
    slot = ttk.Combobox(barra, values=nombres, state="readonly", width=16)
    slot.current(0)
    slot.pack(side="left", padx=6)
    tk.Label(barra, text="Presupuesto").pack(side="left")
    precio = tk.Entry(barra, width=7)
    precio.insert(0, "100")
    precio.pack(side="left", padx=6)
    moneda = ttk.Combobox(barra, values=["divine", "exalted", "chaos"], state="readonly", width=9)
    moneda.current(0)
    moneda.pack(side="left")
    boton = tk.Button(barra, text="Buscar")
    boton.pack(side="left", padx=10)
    abrir = tk.Button(barra, text="Abrir en el navegador", state="disabled")
    abrir.pack(side="left")
    texto = tk.Text(root, wrap="word", font=("Consolas", 10), bg="#15151c", fg="#e5e5e5")
    texto.pack(fill="both", expand=True)
    estado = {"url": None}

    def escribir(msg, limpiar=False):
        def f():
            if limpiar:
                texto.delete("1.0", "end")
            texto.insert("end", msg + "\n")
            texto.see("end")
        root.after(0, f)

    def trabajo(gid, p, m):
        try:
            out = buscar(gid, p, m, log=escribir)
            estado["url"] = out["url"]
            escribir(informe(out, cargar_config()["mostrar"]), limpiar=True)
            root.after(0, lambda: abrir.config(state="normal"))
        except ErrorMercado as e:
            escribir("\nERROR: %s" % e)
        except Exception as e:                      # que la ventana no muera en silencio
            escribir("\nERROR inesperado: %r" % e)
        finally:
            root.after(0, lambda: boton.config(state="normal"))

    def al_buscar():
        try:
            p = float(precio.get().replace(",", "."))
        except ValueError:
            escribir("Escribe un numero en el presupuesto.", limpiar=True)
            return
        boton.config(state="disabled")
        abrir.config(state="disabled")
        escribir("Buscando...", limpiar=True)
        threading.Thread(target=trabajo, args=(slots[slot.current()], p, moneda.get()), daemon=True).start()

    boton.config(command=al_buscar)
    abrir.config(command=lambda: estado["url"] and webbrowser.open(estado["url"]))
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        try:
            resultado = buscar(sys.argv[1], float(sys.argv[2]),
                               sys.argv[3] if len(sys.argv) > 3 else "divine", log=print)
            print()
            print(informe(resultado, cargar_config()["mostrar"]))
        except ErrorMercado as e:
            print("ERROR:", e)
    else:
        main_ventana()
