import pandas as pd
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom

# === ВАШИ НАСТРОЙКИ ===
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/10hXxId0pOiSP48f9__FjhhFTsmipeIMipJbKUSWNxMI/export?format=csv"
SUPPLIER_XML_URL = "https://sumkioptom.com.ua/content/export/8f6bb4d4540177fa4d1590cf7e6677ba.xml"
# ======================

def create_cdata_element(parent, tag, text):
    elem = ET.SubElement(parent, tag)
    elem.text = f"<![CDATA[{text}]]>" if text else ""
    return elem

# 1. Скачиваем данные поставщика
print("Скачиваем XML поставщика...")
response = requests.get(SUPPLIER_XML_URL)
supplier_root = ET.fromstring(response.content)

# Создаем словарь остатков и цен по vendorCode
supplier_data = {}
for offer in supplier_root.findall('.//offer'):
    vendor_code = offer.find('vendorCode')
    if vendor_code is not None and vendor_code.text:
        vc = str(vendor_code.text).strip()
        supplier_data[vc] = {
            'price': offer.find('price').text if offer.find('price') is not None else "0",
            'quantity_in_stock': offer.find('quantity_in_stock').text if offer.find('quantity_in_stock') is not None else "0",
            'available': offer.get('available', 'false')
        }

# 2. Скачиваем вашу таблицу
print("Загружаем Google Таблицу...")
df = pd.read_csv(GOOGLE_SHEET_CSV_URL)

# 3. Формируем новый XML
shop = ET.Element("shop")

# Добавляем ваши категории (жестко заданы по вашему примеру, можно расширить)
categories = ET.SubElement(shop, "categories")
cat_10 = ET.SubElement(categories, "category", id="10")
cat_10.text = "Рюкзаки"
cat_100 = ET.SubElement(categories, "category", id="100", parentId="10", portal_id="380601", portal_url="https://prom.ua/ua/Ryukzaki-gorodskie")
cat_100.text = "Чоловічі рюкзаки"

offers = ET.SubElement(shop, "offers")

# Перебираем строки из вашей таблицы
for index, row in df.iterrows():
    vc = str(row.get('vendorCode', '')).strip()
    
    # Если товара нет в таблице или у поставщика, пропускаем
    if not vc or vc not in supplier_data:
        continue
        
    sup_info = supplier_data[vc]
    
    # Если количество 0, ставим available="false"
    is_available = "true" if int(sup_info['quantity_in_stock']) > 0 else "false"
    
    offer = ET.SubElement(offers, "offer", id=str(row.get('id', '')), available=is_available)
    
    ET.SubElement(offer, "url").text = "" # Пустой URL по вашему шаблону
    ET.SubElement(offer, "name").text = str(row.get('name', ''))
    ET.SubElement(offer, "name_ua").text = str(row.get('name_ua', ''))
    ET.SubElement(offer, "categoryId").text = str(row.get('categoryId', ''))
    ET.SubElement(offer, "portal_category_id").text = str(row.get('portal_category_id', ''))
    
    # ЦЕНА И ОСТАТКИ - берем от поставщика!
    ET.SubElement(offer, "price").text = sup_info['price']
    ET.SubElement(offer, "currencyId").text = "UAH"
    ET.SubElement(offer, "quantity_in_stock").text = sup_info['quantity_in_stock']
    
    # Добавляем картинки (до 10 штук по вашему примеру)
    for i in range(1, 11):
        pic_col = f'picture{i}'
        if pic_col in row and pd.notna(row[pic_col]):
            ET.SubElement(offer, "picture").text = str(row[pic_col])
            
    ET.SubElement(offer, "vendorCode").text = vc
    ET.SubElement(offer, "vendor").text = str(row.get('vendor', ''))
    
    # Описания в CDATA
    create_cdata_element(offer, "description", str(row.get('description', '')))
    create_cdata_element(offer, "description_ua", str(row.get('description_ua', '')))
    
    # Параметры (характеристики)
    for col in df.columns:
        if str(col).startswith('param:'):
            param_name = col.split('param:')[1]
            param_val = row[col]
            if pd.notna(param_val):
                param_tag = ET.SubElement(offer, "param", name=param_name)
                param_tag.text = str(param_val)

# === ДОБАВЛЯЕМ КРАСИВЫЕ ОТСТУПЫ ===
ET.indent(shop, space="    ")

# Сохраняем итоговый файл
xml_str = ET.tostring(shop, encoding='utf-8')
# Восстанавливаем CDATA
xml_str = xml_str.decode('utf-8').replace('&lt;![CDATA[', '<![CDATA[').replace(']]&gt;', ']]>')

with open('my_prom_feed.xml', 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write(xml_str)

print("Файл my_prom_feed.xml успешно создан с разметкой!")
