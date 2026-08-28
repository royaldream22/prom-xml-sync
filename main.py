import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# === ВАШИ НАСТРОЙКИ ===
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/10hXxId0pOiSP48f9__FjhhFTsmipeIMipJbKUSWNxMI/export?format=csv"

# Блок поставщиков: Жестко связываем ссылку с ее префиксом
SUPPLIERS = [
    {"url": "https://sumkioptom.com.ua/content/export/8f6bb4d4540177fa4d1590cf7e6677ba.xml", "prefix": ""},
    {"url": "https://backend.mydrop.com.ua/vendor/api/export/products/prom/yml?public_api_key=1968f586df409964df184253c728d3e7ebd97e78&price_field=price&stock_sync=true&only_available=true&static_sizes=true", "prefix": "P2-"},
    {"url": "https://backend.mydrop.com.ua/vendor/api/export/products/prom/yml?public_api_key=f707fd84c2f2713b8fd352a812516cab83a56ec3&price_field=price&param_name=Размер&stock_sync=true", "prefix": "P3-"}
]
# ======================

cdata_table = {}
cdata_counter = 0

def create_cdata_element(parent, tag, text):
    global cdata_counter
    elem = ET.SubElement(parent, tag)
    placeholder = f"##CDATA_BLOB_{cdata_counter}##"
    cdata_table[placeholder] = text if text else ""
    elem.text = placeholder
    cdata_counter += 1
    return elem

def clean_id(val):
    val_str = str(val).strip()
    if val_str.endswith('.0'): return val_str[:-2]
    return val_str

supplier_data = {}

# Скачиваем данные от всех поставщиков
for index, sup in enumerate(SUPPLIERS):
    print(f"Скачиваем прайс поставщика {index + 1}...")
    try:
        response = requests.get(sup["url"])
        supplier_root = ET.fromstring(response.content)
        
        for offer in supplier_root.findall('.//offer'):
            vendor_code = offer.find('vendorCode')
            if vendor_code is not None and vendor_code.text:
                vc = str(vendor_code.text).strip()
                
                # Добавляем префикс конкретного поставщика
                vc = f"{sup['prefix']}{vc}"
                    
                supplier_data[vc] = {
                    'price': offer.find('price').text if offer.find('price') is not None else "0",
                    'oldprice': offer.find('oldprice').text if offer.find('oldprice') is not None else "",
                    'quantity_in_stock': offer.find('quantity_in_stock').text if offer.find('quantity_in_stock') is not None else "0"
                }
    except Exception as e:
        print(f"Ошибка при скачивании прайса {sup['url']}: {e}")

# Дальше код остается без изменений...
# print("Загружаем Google Таблицу...")

# 2. Загружаем Google Таблицу
print("Загружаем Google Таблицу...")
df = pd.read_csv(GOOGLE_SHEET_CSV_URL, dtype=str).fillna("")

# 3. Читаем категории из шаблона template.xml
print("Импортируем структуру категорий...")
template_tree = ET.parse('template.xml')
template_root = template_tree.getroot()
categories_template = template_root.find('.//categories')

yml_catalog = ET.Element('yml_catalog', date=datetime.now().strftime('%Y-%m-%d %H:%M'))
shop = ET.SubElement(yml_catalog, 'shop')

if categories_template is not None:
    shop.append(categories_template)
else:
    ET.SubElement(shop, 'categories')

offers = ET.SubElement(shop, 'offers')

# 4. Сопоставляем товары
print("Сборка товаров...")
for index, row in df.iterrows():
    vc = clean_id(row.get('vendorCode', ''))
    if not vc: continue 
        
    # Строгая проверка по базе поставщиков
    if vc in supplier_data:
        # Товар есть - берем свежую цену и остаток
        sup_info = supplier_data[vc]
    else:
        # Товара нет в базе поставщика - значит его удалили или раскупили. 
        # Отправляем на Пром количество 0.
        sup_info = {
            'price': str(row.get('price', '0')).replace(',', '.'),
            'oldprice': str(row.get('oldprice', '0')).replace(',', '.'),
            'quantity_in_stock': "0"
        }
        
    # === МОДУЛЬ "ЗАГЛУШКА" И "ГОТОВО К ОТПРАВКЕ" ===
    sheet_available = str(row.get('available', 'TRUE')).strip().upper()
    sheet_ready = str(row.get('ready_to_ship', 'TRUE')).strip().upper()
    
    if sheet_available == "FALSE":
        is_available = "false"
        final_qty = "0"
        is_ready = "false"
    else:
        if int(float(sup_info['quantity_in_stock'])) > 0:
            is_available = "true"
            is_ready = "true" if sheet_ready != "FALSE" else "false"
        else:
            is_available = "false"
            is_ready = "false"
        final_qty = str(int(float(sup_info['quantity_in_stock'])))
    
    # Создаем тег offer с нужными атрибутами
    offer = ET.SubElement(offers, "offer", id=clean_id(row.get('id', '')), available=is_available, in_stock=is_ready)
    # ===============================================

    ET.SubElement(offer, "url").text = "" 
    ET.SubElement(offer, "name").text = str(row.get('name', '')).strip()
    ET.SubElement(offer, "name_ua").text = str(row.get('name_ua', '')).strip()
    ET.SubElement(offer, "categoryId").text = clean_id(row.get('categoryId', ''))
    ET.SubElement(offer, "portal_category_id").text = clean_id(row.get('portal_category_id', ''))
    
    # Модуль "Наценка"
    base_price = float(sup_info['price']) if sup_info['price'] else 0.0
    base_oldprice = float(sup_info['oldprice']) if sup_info['oldprice'] else 0.0
    markup_val = str(row.get('markup', '0')).strip()
    if markup_val.lower() == 'nan' or markup_val == '': markup_val = '0'
        
    final_price = base_price
    final_oldprice = base_oldprice
    
    if markup_val != '0':
        if markup_val.endswith('%'):
            try:
                percent = float(markup_val.replace('%', '').replace(',', '.')) / 100.0
                final_price = base_price * (1 + percent)
                if base_oldprice: final_oldprice = base_oldprice * (1 + percent)
            except ValueError: pass
        else:
            try:
                fixed_markup = float(markup_val.replace(',', '.'))
                final_price = base_price + fixed_markup
                if base_oldprice: final_oldprice = base_oldprice + fixed_markup
            except ValueError: pass
    
    ET.SubElement(offer, "price").text = str(int(round(final_price)))
    if base_oldprice: ET.SubElement(offer, "oldprice").text = str(int(round(final_oldprice)))
        
    ET.SubElement(offer, "currencyId").text = "UAH"
    ET.SubElement(offer, "quantity_in_stock").text = final_qty
    
    for i in range(1, 11):
        pic_col = f'picture{i}'
        if pic_col in row:
            pic_val = str(row[pic_col]).strip()
            if pic_val != "" and pic_val.lower() != "nan":
                ET.SubElement(offer, "picture").text = pic_val
            
    ET.SubElement(offer, "vendorCode").text = vc
    ET.SubElement(offer, "vendor").text = str(row.get('vendor', '')).strip()
    
    # Модуль тегов (Keywords)
    keywords_val = str(row.get('keywords', '')).strip()
    if keywords_val and keywords_val.lower() != 'nan':
        ET.SubElement(offer, "keywords").text = keywords_val
    
    create_cdata_element(offer, "description", str(row.get('description', '')).strip())
    create_cdata_element(offer, "description_ua", str(row.get('description_ua', '')).strip())
    
    for col in df.columns:
        if str(col).startswith('param:'):
            param_name = col.split('param:')[1]
            param_val = str(row[col]).strip()
            if param_val != "" and param_val.lower() != "nan":
                param_tag = ET.SubElement(offer, "param", name=param_name)
                param_tag.text = param_val

ET.indent(yml_catalog, space="    ")
xml_str = ET.tostring(yml_catalog, encoding='unicode')

for placeholder, raw_html in cdata_table.items():
    xml_str = xml_str.replace(placeholder, f"<![CDATA[{raw_html}]]>")

with open('my_prom_feed.xml', 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<!DOCTYPE yml_catalog SYSTEM "shops.dtd">\n')
    f.write(xml_str)

print("Файл успешно собран! Теги и статус отправки добавлены.")
