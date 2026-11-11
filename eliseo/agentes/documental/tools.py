"""Tools de solo lectura del agente Documental (design D4).

El `consorcio_id` no es un argumento: se fija al construir las tools a partir de la Identidad
del estado, así el LLM no puede pedir documentos de otro consorcio.
"""
from dataclasses import dataclass

from langchain_core.tools import StructuredTool

from eliseo.agentes.documental import retriever
from eliseo.corpus import Documento, cargar_corpus

MAX_BUSQUEDAS = 3
LIMITE_ALCANZADO = "Límite de búsquedas alcanzado. Respondé con lo que ya encontraste."


def formatear(doc: Documento) -> str:
    """Un documento como dato delimitado, con su estado de vigencia."""
    if doc.reemplazado_por:
        estado = f"NO VIGENTE, reemplazado por {doc.reemplazado_por}"
    elif doc.modificado_por:
        estado = f"vigente, modificado por {', '.join(doc.modificado_por)}"
    else:
        estado = "vigente"
    return f'<documento ref="{doc.ref}" fecha="{doc.fecha}" estado="{estado}">\n{doc.titulo}. {doc.texto}\n</documento>'


@dataclass
class Contador:
    busquedas: int = 0


def crear_tools(consorcio_id: str, max_busquedas: int = MAX_BUSQUEDAS) -> tuple[list[StructuredTool], Contador]:
    contador = Contador()
    corpus = cargar_corpus(consorcio_id)

    def search_reglamento(consulta: str) -> str:
        """Busca en el reglamento y las actas del consorcio. `consulta` va en lenguaje de reglamento."""
        if contador.busquedas >= max_busquedas:
            return LIMITE_ALCANZADO
        contador.busquedas += 1
        # Sin resolver vigencia: el agente ve el artículo original con su estado y decide si leer el acta.
        refs = retriever.buscar(consorcio_id, consulta, k=3).etapas
        orden = refs.get("rerank") or refs["rrf"]
        docs = [corpus.get(r) for r in orden[:3]]
        return "\n".join(formatear(d) for d in docs) or "No se encontraron documentos."

    def get_acta(acta_id: str) -> str:
        """Devuelve un acta completa (ACTA-AAAA-MM-DD) o un punto (ACTA-AAAA-MM-DD#n)."""
        doc = corpus.get(acta_id)
        if doc is None or doc.tipo != "Acta":
            return f"No existe el acta {acta_id} en este consorcio."
        if "#" in acta_id:
            return formatear(doc)
        return "\n".join(formatear(d) for d in corpus.actas() if d.ref.startswith(acta_id + "#"))

    tools = [StructuredTool.from_function(search_reglamento), StructuredTool.from_function(get_acta)]
    return tools, contador
