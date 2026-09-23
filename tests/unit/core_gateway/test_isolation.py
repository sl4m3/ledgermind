from __future__ import annotations

from ledgermind_local.core_gateway.isolation import (
    IsolationCapabilities,
    IsolationPlan,
    IsolationRequirements,
)


def test_requirements_report_independent_missing_capabilities() -> None:
    capabilities = IsolationCapabilities(
        network_isolated=True,
        rounds_database_hidden=False,
        filesystem_allowlisted=False,
        environment_sanitized=True,
        file_descriptors_closed=True,
        binary_signature_verified=False,
    )
    requirements = IsolationRequirements(
        require_network_isolation=True,
        require_rounds_database_hidden=True,
        require_filesystem_allowlist=True,
        require_environment_sanitized=True,
        require_signature=True,
    )

    assert requirements.missing(capabilities) == (
        "rounds_database_hidden",
        "filesystem_allowlisted",
        "binary_signature_verified",
    )


def test_isolation_plan_keeps_command_and_capabilities_together() -> None:
    capabilities = IsolationCapabilities(
        network_isolated=True,
        sandbox_backend="unshare",
        detail="network namespace",
    )
    plan = IsolationPlan(command=("core", "--database", "knowledge.db"), capabilities=capabilities)

    assert plan.command == ("core", "--database", "knowledge.db")
    assert plan.capabilities is capabilities
