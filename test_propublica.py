import requests
import time

# Test basic search
response = requests.get('https://projects.propublica.org/nonprofits/api/v2/search.json?q=union')
data = response.json()

print(f"Total results: {data.get('total_results', 0)}")
print(f"First org: {data['organizations'][0] if data['organizations'] else 'None'}")

# Check available fields
if data['organizations']:
    org = data['organizations'][0]
    print(f"Fields: {org.keys()}")
    print(f"Has EIN: {'ein' in org}")
    print(f"Has name: {'name' in org}")
    print(f"Has state: {'state' in org}")
