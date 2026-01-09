"""Compute ↔ Trade bridge.

This is the *only* allowed connector between compute-plane and trade-plane.
It forwards only whitelisted, contract-valid events (typically risk-approved orders).
"""
