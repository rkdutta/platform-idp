"""_rbac_policy_block is pure string-building (no k8s/network I/O) but is
exactly what teams-api's Argo CD RBAC self-service depends on — the
project-lifecycle e2e test in platform-infra/tests/e2e verifies this against
a live cluster; this pins the exact format at the unit level."""


def test_rbac_policy_block_format(operator):
    block = operator._rbac_policy_block("myproj", {"project-myproj-default"})

    assert block.startswith("# BEGIN project myproj\n")
    assert block.rstrip("\n").endswith("# END project myproj")
    assert "p, role:myproj-viewer, applications, get, myproj/*, allow" in block
    assert "p, role:myproj-maintainer, applications, *, myproj/*, allow" in block
    assert "g, project-myproj-default-viewer, role:myproj-viewer" in block
    assert "g, project-myproj-default-maintainer, role:myproj-maintainer" in block
    # exec is deliberately excluded from both roles (see the method's docstring)
    assert "exec" not in block


def test_rbac_policy_block_multiple_namespaces_sorted(operator):
    block = operator._rbac_policy_block("myproj", {"project-myproj-b", "project-myproj-a"})

    idx_a = block.index("project-myproj-a-viewer")
    idx_b = block.index("project-myproj-b-viewer")
    assert idx_a < idx_b  # sorted(namespaces) in the implementation
