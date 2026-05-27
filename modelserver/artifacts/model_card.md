# Model Card: Concierge Intent Classifier

## Task Description

This model classifies incoming visitor messages into one of six Concierge router categories:

- faq
- support
- sales_or_leads
- human_request
- spam
- other

The model returns a predicted label and a confidence score. The classifier is intended to support the Concierge routing layer by giving a cheap first-pass intent prediction before the main system decides what to do next.

## Dataset

The original dataset was split into:

- train.csv: 9,016 rows
- val.csv: 1,932 rows
- test.csv: 1,932 rows

Each file has two columns:

- text
- label

## Duplicate and Leakage Handling

To make evaluation more honest:

- duplicated training messages were deduplicated
- training texts with conflicting labels were removed
- validation/test messages that appeared exactly in training were removed
- duplicate messages inside validation/test were also removed

Clean evaluation sizes:

- clean train: 8,967 rows
- clean validation: 1,904 rows
- clean test: 1,915 rows

Training texts with conflicting labels removed: 0

## Model

Selected model:

- tfidf_word_1_2_logreg_C2
- TF-IDF word features
- Logistic Regression
- exported as joblib

## Output Format

The modelserver returns the predicted label and the confidence score.
```json
{
  "label": "faq",
  "confidence": 0.91
}
```


## Validation Results
Accuracy: 0.9848
Macro-F1: 0.9795
Weighted-F1: 0.9848
Average confidence: 0.9003
Average latency per example: 0.0595 ms


## Test Results
Accuracy: 0.9849
Macro-F1: 0.9818
Weighted-F1: 0.9849
Average confidence: 0.8990
Average latency per example: 0.0295 ms
Deployment Choice

This model is suitable for the first shipped classifier because it is lightweight, fast, and can run in the modelserver with scikit-learn and joblib only. It does not require torch or transformers in the serving container.

## Limitations

Manual testing showed that some real Concierge-style messages can be ambiguous.

For example:

> Can someone contact me about pricing?

This can look like both:

- sales_or_leads
- human_request

This is a label-definition issue, not only a model issue.

The dataset also appears cleaner and more template-like than real website chat traffic, so production behavior should be monitored using real widget messages over time.

---

## Artifact
```text
model.joblib
```
SHA-256:
```text
 cd9df32928a567d39a8b5e0246112e1dc6d80a6a215cef336b58e99e5bbae7f0
```
## Boot Verification

At modelserver startup, `startup.py` should compute the SHA-256 of:

```text
modelserver/artifacts/model.joblib
```

It should compare the computed value against the SHA-256 recorded in this model card.

If the values do not match, the modelserver must exit with a clear error message.