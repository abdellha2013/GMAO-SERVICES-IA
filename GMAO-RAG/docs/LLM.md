# LLM — Stage 8

Module de génération de réponses par Large Language Model.

## Architecture

```
app/llm/
├── __init__.py              # API publique
├── base.py                  # LLMStrategy ABC
├── registry.py              # LLMRegistry
├── orchestrator.py          # LLMOrchestrator
└── strategies/
    ├── __init__.py          # ALL_STRATEGIES
    └── openai_llm.py        # OpenAILLM (Chat Completions API)
```

## Données d'entrée / sortie

**Entrée** : `query: str` + `candidates: list[RankedChunk]` (sortie du reranker Stage 7)

**Sortie** : `LLMResponse` structurée

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMResponse:
    answer: str                          # Réponse du LLM
    query: str                           # Requête originale
    strategy_name: str                   # e.g. "openai"
    model_name: str                      # e.g. "gpt-4o-mini"
    citations: tuple[Citation, ...]      # Sources utilisées
    tokens_input: int                    # Tokens en entrée
    tokens_output: int                   # Tokens en sortie
    duration_ms: float                   # Temps de réponse
    metadata: dict[str, Any]             # Champs libres

@dataclass(frozen=True, slots=True, kw_only=True)
class Citation:
    chunk_id: str
    source_name: str
    source_type: str
    rerank_score: float
```

## Stratégie OpenAI

### Configuration (.env)

```bash
OPENAI_API_KEY=sk-...              # Obligatoire
LLM_MODEL_NAME=gpt-4o-mini         # Défaut: gpt-4o-mini
LLM_TEMPERATURE=0.3                # Défaut: 0.3
LLM_MAX_TOKENS=1024                # Défaut: 1024
LLM_BASE_URL=                      # Optionnel (pour proxys)
```

### Prompt template

```python
SYSTEM_PROMPT = (
    "Tu es un assistant expert en maintenance industrielle (GMAO). "
    "Réponds à la question en te basant UNIQUEMENT sur le contexte fourni. "
    "Si le contexte ne contient pas assez d'information, dis-le explicitement. "
    "Cite tes sources en mentionnant [source_name]."
)

USER_TEMPLATE = "## Contexte\n{context}\n\n## Question\n{query}"
```

Le contexte est assemblé automatiquement depuis les `RankedChunk` :
```
[1] report.pdf:42 (score: 0.997)
Le moteur électrique présente des vibrations...

[2] panne:7 (score: 0.850)
Panne signalée le 2024-03-15...
```

### Usage

```python
from app.llm import build_default_orchestrator

orch = build_default_orchestrator()
response = orch.generate(query, candidates)

print(response.answer)
print(response.citations)
print(f"Tokens: {response.tokens_input}/{response.tokens_output}")
```

### Customisation du prompt

```python
from app.llm.strategies.openai_llm import OpenAILLM

llm = OpenAILLM(
    api_key="sk-...",
    system_prompt="Tu es un expert en maintenance.",
    user_template="Contexte:\n{context}\n\nQuestion: {query}",
)
```

## Hiérarchie d'exceptions

```
GMAOError
└── LLMError
    ├── LLMValidationError        (400)
    ├── LLMConnectionError        (502)
    ├── LLMRateLimitError         (429)
    ├── LLMModelError             (500)
    ├── LLMGenerationError        (500)
    └── LLMStrategyNotRegisteredError (400)
```

## Stratégies enregistrées

| Nom | Classe | Description |
|-----|--------|-------------|
| `openai` | `OpenAILLM` | OpenAI Chat Completions API |

## Pattern d'architecture

Le module suit le même pattern que les autres couches :
- **Base** : `LLMStrategy` ABC avec `name` class attribute + `__init_subclass__` validation
- **Registry** : `LLMRegistry` stocke des classes (pas d'instances)
- **Orchestrator** : `LLMOrchestrator` résout la stratégie, valide les inputs, délègue
- **Stratégies** : implémentations concrètes avec lazy-loading et cache

## Tests

```bash
# Tests unitaires (mockés)
python -m pytest tests/unit/llm/ -v --ignore=tests/unit/llm/test_llm_manual.py

# Test manuel (avec vraie API OpenAI)
GMAO_MANUAL_TESTS=1 python -m pytest tests/unit/llm/test_llm_manual.py -v -s
```
