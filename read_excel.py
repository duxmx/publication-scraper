from openpyxl import load_workbook

wb = load_workbook('example_input.xlsx', read_only=True)
ws = wb['Sheet1']

print("Headers:")
headers = [cell.value for cell in list(ws.rows)[0]]
print(headers)

print("\nFirst few rows:")
for row in list(ws.rows)[1:5]:
    print([cell.value for cell in row])
