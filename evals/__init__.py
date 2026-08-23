"""Evaluation harness for MAGI.

Runs a fixed suite of questions through the real pipeline and scores the
council on the things that actually make it good or bad: whether the three
lenses say different things, whether it commits to an answer, whether the
prose is vague, and how long it takes.

    python -m evals run --out evals/runs/baseline.json
    python -m evals score evals/runs/baseline.json
    python -m evals compare evals/runs/baseline.json evals/runs/after.json
"""
