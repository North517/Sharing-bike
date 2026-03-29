import requests
r = requests.get(
    'https://restapi.amap.com/v3/geocode/geo',
    params={
        'key': 'fe48c16fd360355b2a506c6ab7c91f5e',
        'address': '山西省晋中市太谷区铭贤南路1号山西农业大学',
        'output': 'json'
    },
    timeout=10
)
print(r.text)
