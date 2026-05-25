# Model Card: Concierge Intent Classifier

## Task Description

Binary/multi-class intent classifier that routes incoming visitor messages to the
appropriate handler: RAG search, lead capture, escalation, or general conversation.
Deployed as an ONNX artifact served by the modelserver container (no torch, no
transformers). Inference target: < 100 ms p95.

## Dataset

- **Name**: TODO — Owner C to record exact dataset name before Monday coding
- **Source**: Public labeled text-classification dataset (sales/support/spam intent or close equivalent)
- **File SHA-256**: TODO — Owner C to record after download
- **Split**: TODO — record train/validation/test split ratios

## Model Results

| Metric | Value | Threshold |
|--------|-------|-----------|
| Macro F1 | TODO | ≥ 0.70 (CI floor) |
| Precision | TODO | — |
| Recall | TODO | — |

## Deployment Choice

- **Format**: TODO — ONNX (preferred) or scikit-learn joblib
- **Runtime**: onnxruntime (ONNX) or scikit-learn (joblib) — no torch, no transformers
- **Container size budget**: < 500 MB total modelserver image

## Artifact SHA-256

- TODO — record artifact SHA-256 after training; verified at container boot by `startup.py`
