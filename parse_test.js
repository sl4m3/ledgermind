const fs = require('fs');

let safetyData = {};
try {
  const fileContent = fs.readFileSync('safety-report.json', 'utf8');
  safetyData = JSON.parse(fileContent || '{}');
  console.log('Safety vulns:', safetyData.vulnerabilities.length);
} catch(e) {
  console.error('Failed to parse safety-report.json:', e);
}
