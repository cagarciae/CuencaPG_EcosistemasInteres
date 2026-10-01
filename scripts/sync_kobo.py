import os, io, json, re, unicodedata, requests
from pathlib import Path
from PIL import Image, ImageOps

SERVER = os.environ.get("KOBO_SERVER", "https://kf.kobotoolbox.org")
UID = os.environ["KOBO_ASSET_UID"]
HEADERS = {"Authorization": f"Token {os.environ['KOBO_TOKEN']}"}

FOTOS = Path("fotos"); FOTOS.mkdir(exist_ok=True)
DATA = Path("data"); DATA.mkdir(exist_ok=True)

CAMPO_NOMBRE = "Nombre"   # nombre de datos del campo en Kobo

def envios():
    url = f"{SERVER}/api/v2/assets/{UID}/data/?format=json&limit=300"
    while url:
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        j = r.json()
        yield from j["results"]
        url = j.get("next")

def obtener(e, campo):
    # busca el campo exacto; si no, ignora mayúsculas y prefijos de grupo (grupo/Nombre)
    if campo in e:
        return e[campo]
    for k, v in e.items():
        if k.split("/")[-1].lower() == campo.lower():
            return v
    return ""

def limpiar(texto):
    # quita tildes, espacios y símbolos para que sea un nombre de archivo válido
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^A-Za-z0-9]+", "-", texto).strip("-").lower()
    return texto[:60] or "sin-nombre"

def guardar_limpia(contenido, destino):
    img = Image.open(io.BytesIO(contenido))
    img = ImageOps.exif_transpose(img).convert("RGB")  # corrige rotación
    img.thumbnail((1200, 1200))
    img.save(destino, "JPEG", quality=80)  # sin exif => no se guardan metadatos

resultado, vigentes = [], set()

# orden por _id para que, si hay nombres repetidos, el más antiguo conserve el nombre limpio
for e in sorted(envios(), key=lambda x: x["_id"]):
    adj = next((a for a in e.get("_attachments", [])
                if a.get("mimetype", "").startswith("image/")
                and not a.get("is_deleted")), None)
    if not adj:
        continue

    valor_nombre = obtener(e, CAMPO_NOMBRE)
    base = limpiar(valor_nombre)
    nombre = f"{base}.jpg"
    if nombre in vigentes:                      # nombre repetido: agrega el _id
        nombre = f"{base}_{e['_id']}.jpg"
    vigentes.add(nombre)
    destino = FOTOS / nombre

    if not destino.exists():
        r = requests.get(adj["download_url"], headers=HEADERS, timeout=120)
        r.raise_for_status()
        guardar_limpia(r.content, destino)

    geo = e.get("_geolocation") or [None, None]
    lat = round(geo[0], 3) if geo[0] is not None else None  # ~110 m de precisión
    lon = round(geo[1], 3) if geo[1] is not None else None

    resultado.append({
        "id": e["_id"],
        "nombre": str(valor_nombre),
        "foto": f"fotos/{nombre}",
        "descripcion": e.get("descripcion", ""),
        "fecha": e.get("_submission_time"),
        "lat": lat, "lon": lon,
    })

# borrar fotos que ya no existen en Kobo o cambiaron de nombre
for f in FOTOS.glob("*.jpg"):
    if f.name not in vigentes:
        f.unlink()

resultado.sort(key=lambda d: d["fecha"] or "", reverse=True)
(DATA / "datos.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1))
print(f"{len(resultado)} fotos publicadas")
