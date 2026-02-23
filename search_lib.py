import os

search_path = r"C:\Users\jakew\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\langextract"
target = "def extract("

for root, dirs, files in os.walk(search_path):
    for file in files:
        if file.endswith(".py"):
            full_path = os.path.join(root, file)
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    if target in f.read():
                        print(f"FOUND IN: {full_path}")
            except:
                pass
