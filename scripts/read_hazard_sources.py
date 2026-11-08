#!/usr/bin/env python3
"""Retain pinned private hazard reads using only the existing offline ILSpy."""

from read_static_tilemap_sources import ROOT, retain_sources


def main():
    retain_sources(ROOT / ".audit/native-room-hazards", ("Celeste.Spikes", "Celeste.PlayerCollider", "Celeste.LedgeBlocker"))


if __name__ == "__main__":
    main()
