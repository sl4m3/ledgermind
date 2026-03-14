const fs = require('fs');

function safeParse(file) {
  try {
    if (fs.existsSync(file)) {
      const content = fs.readFileSync(file, 'utf8');
      const start = content.indexOf('{');
      const end = content.lastIndexOf('}');
      if (start !== -1 && end !== -1 && end >= start) {
        return JSON.parse(content.substring(start, end + 1));
      }
    }
  } catch (e) {
    console.log(`Failed to parse ${file}:`, e);
  }
  return {};
}

fs.writeFileSync('test.json', 'Warning: Deprecated stuff\n{"hello": "world"}');
console.log(safeParse('test.json'));
fs.writeFileSync('test_empty.json', '');
console.log(safeParse('test_empty.json'));
