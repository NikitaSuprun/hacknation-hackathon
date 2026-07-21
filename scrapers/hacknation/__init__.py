"""Hack Nation showcase source (WS-G): plug-and-play ingest of people + projects."""

from scrapers.hacknation.normalizer import HacknationNormalizer, merge_psrs

__all__ = ["HacknationNormalizer", "merge_psrs"]
