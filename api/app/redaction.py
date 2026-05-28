from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

ENTITY_TYPES = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "CRYPTO",
    "API_KEY",
    "US_SSN",
    "IP_ADDRESS",
    "PASSWORD",
]


@dataclass
class RedactionResult:
    text: str
    is_redacted: bool


def _build_analyzer() -> AnalyzerEngine:
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_md"}],
        }
    ).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine)

    # sk-... style keys (Anthropic, OpenAI, etc.) plus generic long tokens
    api_key_recognizer = PatternRecognizer(
        supported_entity="API_KEY",
        patterns=[
            Pattern("api_key_sk_prefix", r"sk-[a-zA-Z0-9_\-]{16,}", score=0.95),
            Pattern("api_key_bearer", r"Bearer\s+[a-zA-Z0-9\-_]{20,}", score=0.85),
        ],
    )

    # password=value or password: value assignments
    password_recognizer = PatternRecognizer(
        supported_entity="PASSWORD",
        patterns=[
            Pattern(
                "password_assignment",
                r"(?i)pass(?:word|wd)?\s*[=:]\s*\S+",
                score=0.85,
            ),
        ],
    )

    analyzer.registry.add_recognizer(api_key_recognizer)
    analyzer.registry.add_recognizer(password_recognizer)
    return analyzer


_analyzer = _build_analyzer()
_anonymizer = AnonymizerEngine()


def redact(text: str) -> RedactionResult:
    results = _analyzer.analyze(text=text, entities=ENTITY_TYPES, language="en")
    if not results:
        return RedactionResult(text=text, is_redacted=False)
    anonymized = _anonymizer.anonymize(text=text, analyzer_results=results)
    return RedactionResult(text=anonymized.text, is_redacted=True)
