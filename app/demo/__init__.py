"""Demo data architecture for PickPulse.

Public surface:
    DemoModeResolver  — central demo/live mode arbiter
    DemoLoadResult    — result of a demo data load operation

Usage in console_api.py::

    from .demo import DemoModeResolver
    demo_resolver = DemoModeResolver(demo_mode=DEMO_MODE)

    # In trigger_sync:
    if demo_resolver.should_use_synthetic(provider):
        result = demo_resolver.ensure_demo_data(tenant_id, provider)
        ...
"""
from .resolver import DemoModeResolver, DemoLoadResult

__all__ = ["DemoModeResolver", "DemoLoadResult"]
