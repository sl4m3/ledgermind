import os
import re
import sys

def bump_version(new_version):
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 1. Update VERSION file
    v_path = os.path.join(root_dir, "src/ledgermind/VERSION")
    with open(v_path, "w") as f:
        f.write(new_version + "\n")
    print(f"Updated VERSION to {new_version}")

    # 2. Update pyproject.toml
    pp_path = os.path.join(root_dir, "pyproject.toml")
    with open(pp_path, "r") as f:
        content = f.read()
    content = re.sub(r'version = "[^"]+"', f'version = "{new_version}"', content, count=1)
    with open(pp_path, "w") as f:
        f.write(content)
    print("Updated pyproject.toml")

    # 3. Update README.md
    readme_path = os.path.join(root_dir, "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, "r") as f:
            content = f.read()
        content = re.sub(r'\*\*v[0-9.]+\*\*', f'**v{new_version}**', content)
        with open(readme_path, "w") as f:
            f.write(content)
        print("Updated README.md")

    # 4. Update specification.py (already dynamic now via contracts)
    
    # 5. Update tests
    test_path = os.path.join(root_dir, "tests/test_verify_tools_and_audit.py")
    if os.path.exists(test_path):
        with open(test_path, "r") as f:
            content = f.read()
        # Fix: correctly handle nested quotes in regex
        pattern = r"mcp_api_version'\]\s*,\s*\"[^\"]+\"\)"
        replacement = f"mcp_api_version'], \"{new_version}\")"
        content = re.sub(pattern, replacement, content)
        with open(test_path, "w") as f:
            f.write(content)
        print("Updated tests")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bump_version.py <new_version>")
        sys.exit(1)
    bump_version(sys.argv[1])
