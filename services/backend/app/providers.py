"""The one rule about placeholder providers.

Two boundaries build a provider from configuration — speech-to-text and AI Core —
and both have a deterministic fake that must never reach a deployment: a fake that
ran in staging would fill the record with placeholder transcripts and placeholder
memories while every health check passed. The rule lives here, written once, so
the two boundaries cannot drift into disagreeing about when a fake is allowed —
a disagreement nothing in the system would report.

Where the fake may run: `development` and `test`, plus anywhere the operator has
said so explicitly with `REMEMBER_ALLOW_FAKE_PROVIDERS=true`. That override exists
for one case — bringing up an environment end to end before its real provider is
reachable — and it is logged as a warning when it is the reason a fake is built,
so an environment running on placeholders says so at startup rather than being
inferred from the record afterwards.
"""

import logging

from .config import Settings

logger = logging.getLogger(__name__)

FAKE_ENVIRONMENTS = ("development", "test")

OVERRIDE_SETTING = "REMEMBER_ALLOW_FAKE_PROVIDERS"


def refuse_fake_unless_permitted(settings: Settings, what: str) -> None:
    """Raise unless a placeholder provider may be built in this environment."""
    if settings.environment in FAKE_ENVIRONMENTS:
        return
    if settings.allow_fake_providers:
        logger.warning(
            "providers.fake_allowed_by_override",
            extra={
                "extra_fields": {
                    "environment": settings.environment,
                    "provider": what,
                    "setting": OVERRIDE_SETTING,
                }
            },
        )
        return
    raise ValueError(
        f"The fake {what} provider is only allowed in "
        f"{' and '.join(FAKE_ENVIRONMENTS)}, or anywhere with "
        f"{OVERRIDE_SETTING}=true; configure a real provider for "
        f"{settings.environment!r}"
    )