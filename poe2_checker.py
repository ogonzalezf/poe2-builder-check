# -*- coding: utf-8 -*-
"""
POE 2 Builder Check - puntua de 1 a 10 los items que copias en el juego (Ctrl+C).

Uso normal:   pythonw poe2_checker.py        (abre la ventanita flotante)
Modo prueba:  python poe2_checker.py item.txt (puntua un item guardado en un .txt)

Solo usa la libreria estandar de Python. Los pesos del build estan en pesos.json.
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PESOS = os.path.join(BASE, "pesos.json")
SEP = "--------"
NUM = r"(\d+(?:\.\d+)?)"


# ---------------------------------------------------------------- lectura
def es_item(texto):
    return bool(texto) and "Rarity:" in texto and SEP in texto


def limpiar(linea):
    """Quita marcas como (implicit), (rune), (augmented) para mostrar."""
    return re.sub(r"\s*\((implicit|rune|augmented|enchant|fractured|desecrated|unmet)\)", "", linea).strip()


CLASES_POR_BASE = [
    ("Spears", ["Spear"]), ("Sceptres", ["Sceptre"]), ("Rings", ["Ring"]), ("Amulets", ["Amulet"]),
    ("Belts", ["Belt", "Sash"]),
    ("Gloves", ["Gloves", "Gauntlets", "Mitts", "Bracers", "Wraps"]),
    ("Boots", ["Boots", "Greaves", "Sandals", "Shoes", "Slippers", "Sabatons", "Leggings"]),
    ("Helmets", ["Helm", "Greathelm", "Hood", "Cap", "Crown", "Circlet", "Mask", "Tiara", "Visage", "Coif"]),
    ("Body Armours", ["Vest", "Robe", "Coat", "Armour", "Jacket", "Garb", "Plate", "Mail", "Raiment",
                      "Cuirass", "Hauberk", "Brigandine", "Wyrmscale"]),
]


def clase_por_base(base):
    """Si el texto no trae 'Item Class:', deduce la clase por el nombre de la base."""
    palabras = base.split()
    for clase, claves in CLASES_POR_BASE:
        if any(c in palabras for c in claves):
            return clase
    return "?"


def parse_item(texto):
    texto = texto.replace("\r", "")
    secciones = []
    for bloque in texto.split(SEP):
        lineas = [l.strip() for l in bloque.strip().split("\n") if l.strip()]
        if lineas:
            secciones.append(lineas)
    if not secciones:
        return None

    item = {"clase": None, "rareza": None, "nombre": "", "req": {}, "lineas": [], "mods": []}
    nombre = []
    for l in secciones[0]:
        if l.startswith("Item Class:"):
            item["clase"] = l.split(":", 1)[1].strip()
        elif l.startswith("Rarity:"):
            item["rareza"] = l.split(":", 1)[1].strip()
        else:
            nombre.append(l)
    if not item["rareza"]:
        return None
    item["nombre"] = " / ".join(nombre)
    if not item["clase"]:
        item["clase"] = clase_por_base(nombre[-1] if nombre else "")
    item["lineas"].append("Base: " + item["nombre"])

    for sec in secciones[1:]:
        if sec[0].startswith(("Requirements", "Requires")):
            bloque = " ".join(sec)
            m = re.search(r"Level:? (\d+)", bloque)
            if m:
                item["req"]["Level"] = int(m.group(1))
            for attr in ("Str", "Dex", "Int"):
                m = re.search(r"(\d+)(?: \(\w+\))? %s|%s: (\d+)" % (attr, attr), bloque)
                if m:
                    item["req"][attr] = int(m.group(1) or m.group(2))
            continue
        for l in sec:
            item["lineas"].append(l)
            if not re.match(r"^[A-Za-z' ]+:", l):  # las propiedades llevan "Clave: valor"
                item["mods"].append(l)

    item["derivados"] = derivados(item["lineas"])
    return item


def derivados(lineas):
    """Valores calculados: DPS fisico, DPS elemental y resistencia elemental total."""
    aps = 0.0
    fisico = elemental = 0.0
    res = 0.0
    for l in lineas:
        m = re.match(r"Attacks per Second: " + NUM, l)
        if m:
            aps = float(m.group(1))
        m = re.match(r"(Physical|Fire|Cold|Lightning|Chaos|Elemental) Damage: (.*)", l)
        if m:
            total = sum((float(a) + float(b)) / 2 for a, b in re.findall(NUM + "-" + NUM, m.group(2)))
            if m.group(1) == "Physical":
                fisico += total
            else:
                elemental += total
        m = re.search(r"\+" + NUM + r"% to (Fire|Cold|Lightning) Resistance", l)
        if m:
            res += float(m.group(1))
        m = re.search(r"\+" + NUM + r"% to all Elemental Resistances", l)
        if m:
            res += 3 * float(m.group(1))
    return {"pdps": fisico * aps, "edps": elemental * aps, "res_total": res}


# ---------------------------------------------------------------- puntuacion
def cargar_pesos():
    with open(PESOS, encoding="utf-8") as f:
        return json.load(f)


def valor_stat(stat, item):
    """Devuelve (valor, lineas que coincidieron) de un stat en el item."""
    if "derivado" in stat:
        return item["derivados"].get(stat["derivado"], 0.0), []
    patron = re.compile(stat["patron"], re.IGNORECASE)
    total, usadas = 0.0, []
    for l in item["lineas"]:
        m = patron.search(l)
        if not m:
            continue
        nums = [float(g) for g in m.groups() if g is not None]
        total += sum(nums) / len(nums) if nums else 1.0
        usadas.append(l)
    return total, usadas


def buscar_grupo(item, cfg):
    """Primero los grupos que piden un nombre concreto (unicos), luego por clase."""
    for g in cfg["grupos"].values():
        if any(n.lower() in item["nombre"].lower() for n in g.get("nombres", [])):
            return g
    for g in cfg["grupos"].values():
        if not g.get("nombres") and item["clase"] in g.get("clases", []):
            return g
    return None


def puntuar(item, cfg):
    grupo = buscar_grupo(item, cfg)
    res = {"nota": None, "aportes": [], "sobran": [], "avisos": [], "consejo": ""}

    # requisitos contra el personaje
    pj = cfg.get("personaje", {})
    for clave, etiqueta in (("Level", "nivel"), ("Str", "Fue"), ("Dex", "Des"), ("Int", "Int")):
        if clave in item["req"] and clave in pj and item["req"][clave] > pj[clave]:
            res["avisos"].append("Requiere %s %d (tienes %d)" % (etiqueta, item["req"][clave], pj[clave]))

    if grupo is None:
        res["avisos"].append("El build no tiene reglas para '%s'" % item["clase"])
        return res
    res["consejo"] = grupo.get("consejo", "")

    usadas = set()
    suma = 0.0
    pesos = []
    valores = {}
    for sid, regla in grupo["pesos"].items():
        # regla: peso  |  [peso, bueno]  |  [peso, bueno, minimo]
        stat = cfg["stats"][sid]
        if isinstance(regla, list):
            peso = regla[0]
            bueno = regla[1] if len(regla) > 1 else stat["bueno"]
            minimo = regla[2] if len(regla) > 2 else 0
        else:
            peso, bueno, minimo = regla, stat["bueno"], 0
        pesos.append(peso)
        valor, lineas = valor_stat(stat, item)
        valores[sid] = valor
        usadas.update(lineas)
        if valor <= 0:
            continue
        frac = max(0.0, min((valor - minimo) / float(bueno - minimo), 1.0))
        aporte = peso * frac
        suma += aporte
        res["aportes"].append((aporte, stat["nombre"], valor, frac))
    res["aportes"].sort(reverse=True)

    n = grupo.get("mods_para_10", cfg.get("mods_para_10", 4))
    ideal = sum(sorted(pesos, reverse=True)[:n]) or 1.0
    nota = int(round(1 + 9 * min(1.0, suma / ideal)))

    # stats imprescindibles: si faltan, la nota no pasa de 4
    for sid in grupo.get("obligatorios", []):
        if valores.get(sid, 0) <= 0:
            res["avisos"].append("Falta imprescindible: " + cfg["stats"][sid]["nombre"])
            nota = min(nota, 4)
    res["nota"] = nota

    # lineas ya contadas dentro de un valor calculado (resistencias, dano del arma)
    cubiertas = []
    derivs = {cfg["stats"][s].get("derivado") for s in grupo["pesos"]}
    if "res_total" in derivs:
        cubiertas.append(r"% to (Fire|Cold|Lightning) Resistance|% to all Elemental Resistances")
    if derivs & {"pdps", "edps"}:
        cubiertas.append(r"^Adds \d+ to \d+ \w+ Damage|increased Physical Damage|increased Attack Speed")
    res["sobran"] = [limpiar(l) for l in item["mods"]
                     if l not in usadas and not any(re.search(c, l) for c in cubiertas)]
    if grupo.get("nombres"):      # en un unico los demas mods son fijos: no son "sobrantes"
        res["sobran"] = []
    return res


def veredicto(nota):
    if nota is None:
        return "?"
    if nota >= 9:
        return "Idoneo"
    if nota >= 7:
        return "Muy bueno"
    if nota >= 5:
        return "Usable"
    if nota >= 3:
        return "Flojo"
    return "Malo"


def como_texto(item, res):
    out = ["%s  [%s]" % (item["nombre"], item["clase"]),
           "NOTA: %s/10 - %s" % (res["nota"] if res["nota"] is not None else "?", veredicto(res["nota"]))]
    for a in res["avisos"]:
        out.append("  ! " + a)
    for aporte, nombre, valor, frac in res["aportes"]:
        out.append("  + %-28s %7.0f  (%3d%% de lo bueno)" % (nombre, valor, frac * 100))
    for l in res["sobran"][:6]:
        out.append("  - " + l)
    if res["consejo"]:
        out.append("  Build: " + res["consejo"])
    return "\n".join(out)


# ---------------------------------------------------------------- ventana
def color_nota(nota):
    if nota is None:
        return "#888888"
    if nota >= 8:
        return "#4ade80"
    if nota >= 5:
        return "#facc15"
    return "#f87171"


def main_ventana():
    import tkinter as tk

    FONDO = "#15151c"
    root = tk.Tk()
    root.title("POE 2 Builder Check")
    root.overrideredirect(True)          # sin bordes
    root.attributes("-topmost", True)    # siempre encima
    root.attributes("-alpha", 0.92)
    root.configure(bg=FONDO)
    root.geometry("+40+40")

    marco = tk.Frame(root, bg=FONDO, padx=10, pady=8)
    marco.pack()

    def pintar(filas):
        """filas: lista de (texto, color, tamano, negrita)"""
        for w in marco.winfo_children():
            w.destroy()
        for texto, color, tam, negrita in filas:
            tk.Label(marco, text=texto, fg=color, bg=FONDO, justify="left", anchor="w",
                     wraplength=330, font=("Segoe UI", tam, "bold" if negrita else "normal")
                     ).pack(fill="x", anchor="w")

    pintar([("POE 2 Builder Check", "#e5e5e5", 11, True),
            ("Copia un item en el juego con Ctrl+C.", "#9ca3af", 9, False),
            ("Arrastra para mover - clic derecho para cerrar.", "#6b7280", 8, False)])

    # arrastrar / cerrar
    pos = {}
    def inicio(e):
        pos["x"], pos["y"] = e.x_root - root.winfo_x(), e.y_root - root.winfo_y()
    def mover(e):
        root.geometry("+%d+%d" % (e.x_root - pos["x"], e.y_root - pos["y"]))
    root.bind("<Button-1>", inicio)
    root.bind("<B1-Motion>", mover)
    root.bind("<Button-3>", lambda e: root.destroy())

    estado = {"ultimo": None}

    def revisar():
        try:
            texto = root.clipboard_get()
        except Exception:
            texto = None
        if texto and texto != estado["ultimo"]:
            estado["ultimo"] = texto
            if es_item(texto):
                try:
                    item = parse_item(texto)
                    res = puntuar(item, cargar_pesos())   # recarga pesos.json en cada item
                    c = color_nota(res["nota"])
                    filas = [("%s/10  %s" % (res["nota"] if res["nota"] is not None else "?",
                                             veredicto(res["nota"])), c, 20, True),
                             (item["nombre"], "#e5e5e5", 10, True),
                             (item["clase"], "#6b7280", 8, False)]
                    for a in res["avisos"]:
                        filas.append(("! " + a, "#fb923c", 9, True))
                    for aporte, nombre, valor, frac in res["aportes"]:
                        filas.append(("+ %s: %.0f  (%d%%)" % (nombre, valor, frac * 100), "#86efac", 9, False))
                    for l in res["sobran"][:6]:
                        filas.append(("- " + l, "#6b7280", 9, False))
                    if res["consejo"]:
                        filas.append(("Build: " + res["consejo"], "#93c5fd", 8, False))
                    pintar(filas)
                except Exception as e:
                    pintar([("Error", "#f87171", 12, True), (str(e), "#e5e5e5", 9, False)])
        root.after(300, revisar)

    revisar()
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            it = parse_item(f.read())
        if it is None:
            print("El archivo no parece un item copiado del juego.")
        else:
            print(como_texto(it, puntuar(it, cargar_pesos())))
    else:
        main_ventana()
