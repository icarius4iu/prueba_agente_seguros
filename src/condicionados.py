"""
Motor de indexación y búsqueda sobre los documentos de condicionados (.md).

Decisiones de diseño:
1. Segmentación estructural por Artículo (`## Artículo X...`): en documentos normativos de seguros,
   las reglas y sus excepciones viven dentro del mismo artículo (por ejemplo, carencias de salud
   en el Artículo 4 o deducibles vehiculares en el Artículo 2). Dividir por artículo completo
   garantiza contexto legal íntegro y trazabilidad exacta (Documento + Artículo, Regla 6).
2. Búsqueda híbrida sin dependencias externas pesadas: combina coincidencia léxica normalizada
   (BM25/TF simplificado), expansión de sinónimos del dominio asegurador y detección directa de
   referencias a cláusulas (ej. 'Vehicular 5.2', 'Condiciones Generales 6.3', 'Salud 6.1').
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import CONDICIONADOS_DIR

# Mapa de archivos a metadatos legibles
DOCUMENTOS_META: dict[str, dict[str, str]] = {
    "condiciones_generales.md": {
        "nombre": "Condiciones Generales de los Contratos de Seguro",
        "ramo": "general",
        "alias": "condiciones generales",
    },
    "vehicular.md": {
        "nombre": "Condicionado Particular: Seguro Vehicular",
        "ramo": "vehicular",
        "alias": "vehicular auto total auto esencial",
    },
    "salud.md": {
        "nombre": "Condicionado Particular: Seguro de Salud",
        "ramo": "salud",
        "alias": "salud integral clinica plus",
    },
    "vida.md": {
        "nombre": "Condicionado Particular: Seguro de Vida",
        "ramo": "vida",
        "alias": "vida proteccion ahorro plus",
    },
}

# Expansión de sinónimos del dominio de seguros para enriquecer la búsqueda
SINONIMOS_DOMINIO: dict[str, list[str]] = {
    "choque": ["choque", "colision", "daño propio", "poste", "terceros", "procedimiento", "aviso", "72 horas"],
    "choque_poste": ["daño propio", "propiedad publica", "intervencion policial", "dosaje etilico", "72 horas"],
    "poste": ["propiedad publica", "intervencion policial", "dosaje etilico", "daño propio", "choque"],
    "robaron": ["robo total", "denuncia policial", "24 horas", "30 dias", "indemniza", "vigencia", "vencida"],
    "robo": ["robo total", "robo parcial", "accesorios", "denuncia policial", "24 horas", "30 dias", "deducible"],
    "vesicula": ["cirugias programadas", "colecistectomia", "carencia", "6 meses", "emergencia"],
    "operan": ["cirugias", "cirugias programadas", "carencia", "6 meses", "hospitalizacion"],
    "cirugia": ["cirugias", "cirugias programadas", "carencia", "6 meses", "colecistectomia", "hernias"],
    "esposo": ["proteccion de datos personales", "titular", "parentesco", "vinculo conyugal", "autorizacion"],
    "conyuge": ["proteccion de datos personales", "titular", "parentesco", "vinculo conyugal"],
    "ahorrados": ["componente de ahorro", "vida ahorro plus", "rendimiento", "asesor comercial", "inversion"],
    "fondo": ["componente de ahorro", "inversion", "asesor comercial", "recomendaciones"],
    "conviene": ["asesor comercial", "recomendaciones de inversion", "componente de ahorro"],
    "aprueba": ["estados de un siniestro", "evaluacion de siniestros", "aprobar", "rechazar", "modificar"],
    "supervisor": ["evaluacion de siniestros", "canales de atencion", "aprobar", "rechazar"],
    "rechazaron": ["exclusiones", "rechazado", "estados de un siniestro", "motivo"],
    "ebriedad": ["estado de ebriedad", "dosaje etilico", "0.5 g/l", "exclusiones"],
    "cubre": ["cobertura", "productos", "suma asegurada", "deducible", "vigencia"],
    "pagar": ["indemnizacion", "30 dias", "estados de un siniestro", "aprobado", "en_evaluacion"],
}

STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en",
    "con", "por", "para", "sin", "sobre", "mi", "mis", "tu", "su", "sus", "me", "te", "se",
    "lo", "le", "que", "como", "cuando", "donde", "cual", "cuales", "quien", "es", "son",
    "esta", "estan", "fue", "ha", "han", "hay", "si", "no", "mas", "muy", "ya", "o", "u",
    "y", "e", "pero", "porque", "hola", "ayer", "anoche", "hoy", "semana", "proxima",
}


def normalizar_texto(texto: str) -> str:
    """Convierte a minúsculas y elimina tildes/diacríticos."""
    texto_lower = texto.lower()
    nfkd = unicodedata.normalize("NFKD", texto_lower)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokenizar(texto: str) -> list[str]:
    """Extrae tokens alfanuméricos y numerales de cláusulas (ej. 5.2, 6.3), filtrando stopwords."""
    norm = normalizar_texto(texto)
    tokens = re.findall(r"\b\d+\.\d+\b|\b[a-z0-9]{2,}\b", norm)
    return [t for t in tokens if t not in STOPWORDS]


@dataclass
class ArticuloCondicionado:
    chunk_id: str
    archivo: str
    nombre_documento: str
    ramo: str
    articulo_numero: str
    articulo_titulo: str
    encabezado_documento: str
    contenido: str
    texto_busqueda_norm: str
    tokens: list[str]


class BuscadorCondicionados:
    """Índice en memoria de los artículos de todos los condicionados."""

    def __init__(self, condicionados_dir: Path = CONDICIONADOS_DIR) -> None:
        self.condicionados_dir = condicionados_dir
        self.articulos: list[ArticuloCondicionado] = []
        self.idf: dict[str, float] = {}
        self._cargar_e_indexar()

    def _cargar_e_indexar(self) -> None:
        self.articulos.clear()

        for archivo, meta in DOCUMENTOS_META.items():
            ruta = self.condicionados_dir / archivo
            if not ruta.exists():
                continue

            texto = ruta.read_text(encoding="utf-8")
            partes = re.split(r"(?=^##\s+Artículo\s+\d+)", texto, flags=re.MULTILINE)

            encabezado = ""
            bloques_articulos: list[str] = []
            for parte in partes:
                parte_limpia = parte.strip()
                if not parte_limpia:
                    continue
                if parte_limpia.startswith("## Artículo"):
                    bloques_articulos.append(parte_limpia)
                else:
                    # Limpiar líneas de nota ficticia del encabezado
                    lineas_enc = [
                        ln for ln in parte_limpia.splitlines()
                        if not ln.strip().startswith(">") and not ln.strip().startswith("# ")
                    ]
                    encabezado = " ".join(ln.strip() for ln in lineas_enc if ln.strip())

            for bloque in bloques_articulos:
                primera_linea = bloque.splitlines()[0].lstrip("#").strip()
                match_num = re.search(r"Artículo\s+(\d+)", primera_linea, re.IGNORECASE)
                num_art = match_num.group(1) if match_num else "0"

                texto_completo_busqueda = (
                    f"{meta['nombre']} {meta['alias']} {encabezado} {primera_linea} {bloque}"
                )
                norm = normalizar_texto(texto_completo_busqueda)
                toks = tokenizar(texto_completo_busqueda)

                self.articulos.append(
                    ArticuloCondicionado(
                        chunk_id=f"{archivo}#Art{num_art}",
                        archivo=archivo,
                        nombre_documento=meta["nombre"],
                        ramo=meta["ramo"],
                        articulo_numero=num_art,
                        articulo_titulo=primera_linea,
                        encabezado_documento=encabezado,
                        contenido=bloque,
                        texto_busqueda_norm=norm,
                        tokens=toks,
                    )
                )

        # Calcular IDF por token para ponderar términos específicos sobre generales
        total_docs = max(len(self.articulos), 1)
        df: dict[str, int] = {}
        for art in self.articulos:
            for tok in set(art.tokens):
                df[tok] = df.get(tok, 0) + 1
        self.idf = {
            tok: math.log(1.0 + (total_docs - freq + 0.5) / (freq + 0.5))
            for tok, freq in df.items()
        }

    def buscar(
        self,
        consulta: str,
        ramo: str = "todos",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Busca los fragmentos (artículos) más relevantes para la consulta.
        Si se especifica `ramo` ('vehicular', 'salud', 'vida'), filtra o prioriza dicho ramo
        junto con 'general' (Condiciones Generales, que rigen a todos los contratos).
        """
        consulta_norm = normalizar_texto(consulta)
        tokens_base = tokenizar(consulta)

        # Expandir tokens con sinónimos del dominio
        tokens_expandidos = list(tokens_base)
        for tok in tokens_base:
            if tok in SINONIMOS_DOMINIO:
                for frase_sin in SINONIMOS_DOMINIO[tok]:
                    tokens_expandidos.extend(tokenizar(frase_sin))

        ramo_norm = normalizar_texto(ramo or "todos").strip()
        if ramo_norm not in {"vehicular", "salud", "vida", "general"}:
            ramo_norm = "todos"

        # Detectar si la consulta cita una cláusula específica (ej. "5.2", "6.3", "6.1", "1.1")
        clausulas_citadas = re.findall(r"\b(\d+)\.(\d+)\b", consulta_norm)

        resultados_puntuados: list[tuple[float, ArticuloCondicionado]] = []

        for art in self.articulos:
            score = 0.0

            # 1. Puntuación TF-IDF / BM25 sobre tokens base y expandidos
            conteo_art: dict[str, int] = {}
            for t in art.tokens:
                conteo_art[t] = conteo_art.get(t, 0) + 1

            for tok in tokens_base:
                if tok in conteo_art:
                    tf = 1.0 + math.log(conteo_art[tok])
                    score += tf * self.idf.get(tok, 1.0) * 2.5
                elif tok in art.texto_busqueda_norm:
                    score += 1.5

            for tok in tokens_expandidos:
                if tok in conteo_art:
                    score += self.idf.get(tok, 0.8) * 0.9
                elif tok in art.texto_busqueda_norm:
                    score += 0.5

            # 2. Impulso fuerte si coincide con una cláusula exacta (ej. "Vehicular 5.2")
            for num_art_citado, sub_num in clausulas_citadas:
                clausula_str = f"{num_art_citado}.{sub_num}"
                if art.articulo_numero == num_art_citado and clausula_str in art.contenido:
                    score += 15.0

            # 3. Impulso si el nombre del ramo o documento aparece explícitamente en la consulta
            if art.ramo != "general" and art.ramo in consulta_norm:
                score += 4.0
            if "condiciones generales" in consulta_norm and art.ramo == "general":
                score += 5.0

            # 4. Ajuste por filtro de ramo
            if ramo_norm != "todos":
                if art.ramo == ramo_norm:
                    score *= 1.4
                elif art.ramo == "general":
                    score *= 1.1  # Las condiciones generales complementan a todos los ramos
                else:
                    score *= 0.25

            if score > 0:
                resultados_puntuados.append((score, art))

        # Ordenar de mayor a menor relevancia
        resultados_puntuados.sort(key=lambda x: x[0], reverse=True)

        salida: list[dict[str, Any]] = []
        for score, art in resultados_puntuados[: max(1, min(top_k, 8))]:
            salida.append(
                {
                    "documento": art.archivo,
                    "nombre_documento": art.nombre_documento,
                    "ramo": art.ramo,
                    "articulo": art.articulo_titulo,
                    "nota_prelacion": art.encabezado_documento,
                    "contenido": art.contenido,
                    "relevancia_score": round(score, 2),
                }
            )

        return salida


# Instancia singleton para reutilizar el índice en memoria
_buscador_global: BuscadorCondicionados | None = None


def obtener_buscador() -> BuscadorCondicionados:
    global _buscador_global
    if _buscador_global is None:
        _buscador_global = BuscadorCondicionados()
    return _buscador_global
