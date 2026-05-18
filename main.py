import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# === ВАШИ НАСТРОЙКИ ===
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/10hXxId0pOiSP48f9__FjhhFTsmipeIMipJbKUSWNxMI/export?format=csv"
SUPPLIER_XML_URL = "https://sumkioptom.com.ua/content/export/8f6bb4d4540177fa4d1590cf7e6677ba.xml"
# ======================

cdata_table = {}
cdata_counter = 0

def create_cdata_element(parent, tag, text):
    global cdata_counter
    elem = ET.SubElement(parent, tag)
    placeholder = f"##CDATA_BLOB_{cdata_counter}##"
    cdata_table[placeholder] = text if text and pd.notna(text) else ""
    elem.text = placeholder
    cdata_counter += 1
    return elem

# 1. Скачиваем данные поставщика
print("Скачиваем XML поставщика...")
response = requests.get(SUPPLIER_XML_URL)
supplier_root = ET.fromstring(response.content)

supplier_data = {}
for offer in supplier_root.findall('.//offer'):
    vendor_code = offer.find('vendorCode')
    if vendor_code is not None and vendor_code.text:
        vc = str(vendor_code.text).strip()
        supplier_data[vc] = {
            'price': offer.find('price').text if offer.find('price') is not None else "0",
            'oldprice': offer.find('oldprice').text if offer.find('oldprice') is not None else "",
            'quantity_in_stock': offer.find('quantity_in_stock').text if offer.find('quantity_in_stock') is not None else "0"
        }

# 2. Загружаем вашу Google Таблицу
print("Загружаем Google Таблицу...")
df = pd.read_csv(GOOGLE_SHEET_CSV_URL)

# 3. Читаем категории из вашего шаблона template.xml
print("Импортируем структуру категорий...")
template_tree = ET.parse('template.xml')
template_root = template_tree.getroot()
categories_template = template_root.find('.//categories')

# 4. Создаем структуру по эталону Prom.ua
yml_catalog = ET.Element('yml_catalog', date=datetime.now().strftime('%Y-%m-%d %H:%M'))
shop = ET.SubElement(yml_catalog, 'shop')

if categories_template is not None:
    shop.append(categories_template)
else:
    ET.SubElement(shop, 'categories')

offers = ET.SubElement(shop, 'offers')

# 5. Заполняем товары из таблицы
print("Сопоставляем товары по vendorCode и обновляем цены...")
for index, row in df.iterrows():
    vc = str(row.get('vendorCode', '')).strip()
    if not vc or vc not in supplier_data:
        continue
        
    sup_info = supplier_data[vc]
    is_available = "true" if int(sup_info['quantity_in_stock']) > 0 else "false"
    
    offer = ET.SubElement(offers, "offer", id=str(row.get('id', '')), available=is_available)
    
    ET.SubElement(offer, "url").text = "" 
    ET.SubElement(offer, "name").text = str(row.get('name', ''))
    ET.SubElement(offer, "name_ua").text = str(row.get('name_ua', ''))
    ET.SubElement(offer, "categoryId").text = str(row.get('categoryId', ''))
    ET.SubElement(offer, "portal_category_id").text = str(row.get('portal_category_id', ''))
    
    # СИНХРОНИЗАЦИЯ ЦЕНЫ, СТАРOЙ ЦЕНЫ И ОСТАТКОВ
    ET.SubElement(offer, "price").text = sup_info['price']
    if sup_info['oldprice']:
        ET.SubElement(offer, "oldprice").text = sup_info['oldprice']
        
    ET.SubElement(offer, "currencyId").text = "UAH"
    ET.SubElement(offer, "quantity_in_stock").text = sup_info['quantity_in_stock']
    
    for i in range(1, 11):
        pic_col = f'picture{i}'
        if pic_col in row and pd.notna(row[pic_col]):
            ET.SubElement(offer, "picture").text = str(row[pic_col])
            
    ET.SubElement(offer, "vendorCode").text = vc
    ET.SubElement(offer, "vendor").text = str(row.get('vendor', ''))
    
    create_cdata_element(offer, "description", str(row.get('description', '')))
    create_cdata_element(offer, "description_ua", str(row.get('description_ua', '')))
    
    for col in df.columns:
        if str(col).startswith('param:'):
            param_name = col.split('param:')[1]
            param_val = row[col]
            if pd.notna(param_val):
                param_tag = ET.SubElement(offer, "param", name=param_name)
                param_tag.text = str(param_val)

# === КРАСИВЫЕ ОТСТУПЫ И ЗАПИСЬ ===
ET.indent(yml_catalog, space="    ")
xml_str = ET.tostring(yml_catalog, encoding='unicode')

for placeholder, raw_html in cdata_table.items():
    xml_str = xml_str.replace(placeholder, f"<![CDATA[{raw_html}]]>")

with open('my_prom_feed.xml', 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<!DOCTYPE yml_catalog SYSTEM "shops.dtd">\n')
    f.write(xml_str)

print("Новый эталонный файл с ценами и скидками успешно создан!")
