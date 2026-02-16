import base64,sys
data=sys.stdin.read().strip()
code=base64.b64decode(data).decode("utf-8")
with open("C:/Users/jakew/Downloads/labor-data-project/scripts/temp_investigate.py","w",encoding="utf-8") as f:
    f.write(code)
print("Written",len(code),"chars")
