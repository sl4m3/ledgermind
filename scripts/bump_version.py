import os
import re
import sys
from datetime import datetime

def bump_version(new_version):
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    today_date = datetime.now().strftime("%B %d, %2Y") # e.g., February 24, 2026
    
    # 1. Update VERSION file
    v_path = os.path.join(root_dir, "src/ledgermind/VERSION")
    with open(v_path, "w") as f:
        f.write(new_version + "\n")
    print(f"✓ Updated VERSION to {new_version}")

    # 2. Update pyproject.toml
    pp_path = os.path.join(root_dir, "pyproject.toml")
    with open(pp_path, "r") as f:
        content = f.read()
    content = re.sub(r'version = "[^"]+"', f'version = "{new_version}"', content, count=1)
    with open(pp_path, "w") as f:
        f.write(content)
    print("✓ Updated pyproject.toml")

    # 3. Update README.md (including Benchmarks date and multiple version mentions)
    readme_path = os.path.join(root_dir, "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, "r") as f:
            content = f.read()
        
        # Update main version tag
        content = re.sub(r'\*\*v[0-9.]+\*\*', f'**v{new_version}**', content)
        # Update inline version mentions like (v2.7.5)
        content = re.sub(r'\(v[0-9.]+\)', f'(v{new_version})', content)
        # Update Benchmark header with date
        content = re.sub(r'## Benchmarks \([^)]+\)', f'## Benchmarks ({today_date}, v{new_version})', content)
        # Update table columns
        content = re.sub(r'Mean \(v[0-9.]+\)', f'Mean (v{new_version})', content)
        
        with open(readme_path, "w") as f:
            f.write(content)
        print("✓ Updated README.md (Version and Benchmark date)")

    # 4. Update Docs
    docs_dir = os.path.join(root_dir, "docs")
    if os.path.exists(docs_dir):
        for doc_file in os.listdir(docs_dir):
            if doc_file.endswith(".md"):
                path = os.path.join(docs_dir, doc_file)
                with open(path, "r") as f:
                    content = f.read()
                
                # Update titles: # Title (vX.X.X)
                content = re.sub(r'\(v[0-9.]+\)', f'(v{new_version})', content)
                # Update technical notes: As of vX.X.X
                content = re.sub(r'v[0-9.]+', lambda m: new_version if m.group(0).startswith('v') and m.group(0)[1].isdigit() else m.group(0), content)
                # Specific fix for "As of v..." and "In v..."
                content = re.sub(r'(As of v|In v|version v)[0-9.]+', r'\g<1>' + new_version, content)
                
                with open(path, "w") as f:
                    f.write(content)
                print(f"✓ Updated docs/{doc_file}")

    # 5. Update Tests
    test_path = os.path.join(root_dir, "tests/test_verify_tools_and_audit.py")
    if os.path.exists(test_path):
        with open(test_path, "r") as f:
            content = f.read()
        pattern = r"mcp_api_version'\]\s*,\s*\"[^\"]+\"\)"
        replacement = f"mcp_api_version'], \"{new_version}\")"
        content = re.sub(pattern, replacement, content)
        with open(test_path, "w") as f:
            f.write(content)
        print("✓ Updated tests/test_verify_tools_and_audit.py")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bump_version.py <new_version>")
        sys.exit(1)
    bump_version(sys.argv[1])
