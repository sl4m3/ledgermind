import json

def parse_report(filepath):
    try:
        with open(filepath) as f:
            content = f.read()
            if not content.strip():
                return {}
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                return json.loads(content[start:end+1])
            return json.loads(content)
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return {}

print("Safety:", parse_report("safety-report.json"))
print("Bandit:", parse_report("bandit-report.json"))
print("Pip-audit:", parse_report("pip-audit-report.json"))
