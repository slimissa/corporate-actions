# Corpus Baseline

Recorded: 2026-09-30
Corpus: 2 positives, 9 negatives

## Extractor result

True positives:  2/2
False positives: 0/9

## Positives

- pos_01_meta_fb_to_meta_8k.html  → META
- pos_04_fisv_to_fi_8k.html       → FI

## Negatives

Nine 8-K filings that mention "symbol" or "ticker" but announce no change.

## What "passing" means

`test_corpus_extraction_accuracy` asserts TP=2/2 and FP=0/9.
Any regression that drops a true positive or introduces a false positive
must be resolved before the corpus is expanded.
