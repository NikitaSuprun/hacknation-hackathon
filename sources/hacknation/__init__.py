# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Hack Nation showcase source (WS-G): plug-and-play ingest of people + projects."""

from sources.hacknation.normalizer import HacknationNormalizer, merge_psrs

__all__ = ["HacknationNormalizer", "merge_psrs"]
