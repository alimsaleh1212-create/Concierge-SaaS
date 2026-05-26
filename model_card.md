# Model Card: Concierge Intent Classifier

## Model Overview

**Model name**: Concierge Intent Classifier  
**Owner**: C — Models, Security & Guardrails  
**Task type**: Multi-class text classification  
**Purpose**: Classify inbound visitor messages into router labels used by the Concierge system.

The classifier is used before the expensive LLM/agent path. It helps the main API decide whether a message is a clear FAQ, support request, lead/sales intent, human request, spam, or something that should fall back to the agent/out-of-scope handling.

This classifier is business-agnostic. It does not answer questions and does not use tenant CMS content. Tenant-specific answering is handled separately by RAG.

---

## Final Labels

The classifier predicts exactly one of these labels:

```text
faq
support
sales_or_leads
human_request
spam
other
```

## Label Definitions

| Label | Meaning |
|---|---|
| `faq` | A simple informational question that can likely be answered from tenant CMS/RAG content. |
| `support` | A request for help with an issue, account, order, refund, payment, or similar problem. |
| `sales_or_leads` | A message showing buying, signup, pricing, order, subscription, or lead intent. |
| `human_request` | A message explicitly asking for a human, agent, representative, or customer service. |
| `spam` | Junk, scam, promotional spam, or clearly abusive spam. |
| `other` | A normal message that does not clearly fit the fixed router labels above. |

---

## Dataset Sources

The classifier dataset is built from multiple public labeled datasets and mapped into the project’s router labels.

| Source Dataset | Rows Used | Project Label(s) |
|---|---|---|
| Bitext customer-support dataset | Customer-support intent rows manually mapped to Concierge labels | `faq`, `support`, `sales_or_leads`, `human_request` |
| SMS Spam Collection | Only rows originally labeled `spam` | `spam` |
| CLINC OOS | Only rows whose original CLINC intent is `oos` | `other` |

## Dataset Decisions

- Bitext is used for normal customer-support and business-intent examples.
- SMS Spam is used only for the `spam` class.
- SMS `ham` rows are not used as `other`.
- CLINC is used only for rows explicitly labeled `oos`.
- CLINC rows are not all labeled as `other`.
- The `other` label is trained from explicit out-of-scope examples, not from random unmapped rows.
- Tenant CMS content is not part of this classifier dataset. CMS content is used by the RAG system, not by this classifier.

---

## Bitext Label Mapping

| Bitext Intent Type | Project Label |
|---|---|
| Refund policy, cancellation fee, payment methods, delivery options, delivery period, invoice checks, order/refund tracking | `faq` |
| Complaints, payment issues, registration problems, password recovery, account edits, order changes, refunds, shipping address changes | `support` |
| Create account, place order, newsletter subscription | `sales_or_leads` |
| Contact customer service, contact human agent | `human_request` |

---

## Dataset Files

| File | Purpose | SHA-256 |
|---|---|---|
| `bitext_mapped_to_concierge_labels.csv` | Bitext rows mapped to Concierge labels | TODO |
| `sms_spam_mapped_to_concierge_labels.csv` | SMS spam rows only | TODO |
| `clinc_oos_mapped_to_other.csv` | CLINC `oos` rows mapped to `other` | TODO |
| `concierge_intent_spam_other_trainable_capped.csv` | Final capped trainable dataset | TODO |
| `train.csv` | Training split | TODO |
| `val.csv` | Validation split | TODO |
| `test.csv` | Held-out test split | TODO |

---

## Split

| Split | Ratio | Rows |
|---|---:|---:|
| Train | 70% | TODO |
| Validation | 15% | TODO |
| Test | 15% | TODO |

The test set is held out and used only for final evaluation.

---

## Model Approaches Compared

The project requires comparing three approaches before choosing the production model.

| Approach | Artifact Format | Notes |
|---|---|---|
| Classical ML: TF-IDF + Logistic Regression | `joblib` | Lean, fast, easy to serve |
| Small DL model exported to ONNX | `onnx` | Served with `onnxruntime`, no torch in container |
| LLM zero-shot baseline | API call only | Used as a comparison baseline, not served as local artifact |

---

## Evaluation Results

| Model | Macro F1 | Precision | Recall | Latency | Notes |
|---|---:|---:|---:|---:|---|
| Classical ML | TODO | TODO | TODO | TODO | TODO |
| DL / ONNX | TODO | TODO | TODO | TODO | TODO |
| LLM zero-shot baseline | TODO | TODO | TODO | TODO | TODO |

## Per-Class F1

| Label | F1 |
|---|---:|
| `faq` | TODO |
| `support` | TODO |
| `sales_or_leads` | TODO |
| `human_request` | TODO |
| `spam` | TODO |
| `other` | TODO |

---

## CI Threshold

The classifier CI gate uses Macro F1 on the held-out test set.

```text
Macro F1 threshold: TODO
```

The final threshold should also be recorded in `eval_thresholds.yaml`.

---

## Deployment Choice

**Chosen production model**: TODO — classical `joblib` or DL `onnx`

**Reason for choice**:

```text
TODO: Explain why this model was selected based on Macro F1, per-class F1, latency, cost, and serving simplicity.
```

The production model must be served lean:

- Classical model: `scikit-learn` + `joblib`
- DL model: `onnxruntime`
- No `torch`
- No `transformers`
- No training code inside the serving container

---

## Model Artifact

| Field | Value |
|---|---|
| Artifact path | TODO |
| Artifact format | TODO |
| Artifact SHA-256 | TODO |
| Model card path | `model_card.md` |

The model artifact SHA-256 recorded here is used to verify that the served artifact is the expected one.

---

## Limitations

- The classifier is not tenant-specific.
- The classifier does not answer user questions.
- Business-specific answers come from RAG over tenant CMS content.
- The `spam` class is trained from SMS spam examples, so it mainly covers obvious spam/scam patterns.
- The `other` class is trained from CLINC rows explicitly labeled `oos`, so it represents out-of-scope messages.
- Low-confidence predictions should be handled carefully by the router instead of forcing a direct workflow.
- Future improvement: add real website-chat spam and tenant-specific conversation examples.