'''
4 байта - b'NL' и версия (4E 4C 00 01 должны всегда быть!)
4 байта - кол-во файлов
00 00 00 00 00 00 - заглушка
BA AB - маркер (флаги)?

8 байт - повторяющиеся 4 байта (2 первых байта - ключ для XOR расшифровки)

Смещенеие по 10 = file info

Возможный конец структуры файла (Байты в файле написаны с конца, поэтому конец - это заголовок): 
00 00 00 00 00 00 00 00 D0 00 00 00 0C 01 00 00 20 56 B2 01 08 80 42 43 20 51 01 00 00 00 00 00 - последние байты файлов в архиве (raw заголовок DIB изображений)
D0 00 00 00 0C 01 00 00 - размер изображения (ширина и высота по 4 байта)
20 56 - неизвестно
08 80 - флаги. Если 88 88 то изображение не сжато. Если 08 80, то сжато RLE
42 43 - сигнатура? (BC)
20 51 01 00 - размер в байтах (не считая заголовок)
'''

from PIL import Image
import numpy as np
import sys
import os
import struct

output_path = "output/textures"

# Декодер RLE сжатия в 32 бит
def decode_ngi_dib_rle_to_8888(dword_input: list[int], width: int, height: int) -> bytes:
    out_stride = width * 4
    out_buffer = bytearray(out_stride * height)
    
    # Симуляция глобальных переменных
    dword_10013690 = 0
    dword_10013698 = 0
    dword_1001369C = 0
    dword_10013694 = []

    dst_offset = 0
    src_idx = 0
    rows_remaining = height

    while rows_remaining > 0 and src_idx < len(dword_input):
        cmd = dword_input[src_idx]
        src_idx += 1
        opcode = cmd & 0xFFFF
        count = (cmd >> 16) & 0xFFFF

        if opcode == 1:
            dword_10013690 = dst_offset
            dword_10013698 = count
            dword_1001369C = 0
            fill_color = dword_1001369C.to_bytes(4, 'little') * count
            out_buffer[dword_10013690:dword_10013690 + len(fill_color)] = fill_color
            dst_offset += 4 * count

        elif opcode == 2:
            dword_10013698 = count
            dword_1001369C = dword_input[src_idx]
            src_idx += 1
            dword_10013690 = dst_offset
            fill_color = dword_1001369C.to_bytes(4, 'little') * count
            out_buffer[dword_10013690:dword_10013690 + len(fill_color)] = fill_color
            dst_offset += 4 * count

        elif opcode == 3:
            dword_10013690 = dst_offset
            dword_10013698 = count
            dword_10013694 = dword_input[src_idx:src_idx + count]
            for i in range(count):
                val = dword_10013694[i]
                out_buffer[dword_10013690 + i*4 : dword_10013690 + (i+1)*4] = val.to_bytes(4, 'little')
            dst_offset += 4 * count
            src_idx += count

        elif opcode == 4:
            dst_offset = (height - rows_remaining + 1) * out_stride
            rows_remaining -= 1

    return bytes(out_buffer)

# Создание изображения из байтов (палитры)
def save_rgba_image(data, width, height, output_filename):
    clipped = False
    expected_size = width * height * 4

    # Отбрасываем лишние байты, если их больше, чем нужно
    if len(data) > expected_size:
        data = data[:expected_size]
        clipped = True
    elif len(data) < expected_size:
        return -1

    # Реверс байтов
    reversed_data = data[::-1]

    # Преобразование из (A,B,G,R) в (R,G,B,A) по каждому пикселю
    rgba_data = bytearray(expected_size)
    for i in range(0, expected_size, 4):
        a = reversed_data[i]
        b = reversed_data[i + 3]
        g = reversed_data[i + 2]
        r = reversed_data[i + 1]
        rgba_data[i]     = r
        rgba_data[i + 1] = g
        rgba_data[i + 2] = b
        rgba_data[i + 3] = a

    # Создание изображения
    image = Image.frombytes('RGBA', (width, height), bytes(rgba_data))

    # Отзеркаливание по вертикали
    image = image.transpose(Image.FLIP_LEFT_RIGHT)

    # Сохранение результата
    image.save(output_filename)

    if (clipped):
        return 2
    else:
        return 1

# XOR расшифровщик данных по ключу
def nl_decrypt(data, ax):
    ah = (ax >> 8) & 0xFF
    al = ax & 0xFF
    for i in range(len(data)):
        al = ((al << 1) & 0xFF) ^ ah
        ah = ((ah >> 1) & 0xFF) ^ al
        data[i] ^= al

# Чтение и работа с NL файлом
def extract_images(filePath):
    # На основе названия файла, создаем папку, куда будем сохранять изображения
    basename = os.path.basename(filePath)
    filename = os.path.splitext(basename)[0]
    save_path = output_path + "/" + filename
    os.makedirs(save_path, exist_ok=True)

    # Работа с NL файлом
    with open(filePath, 'rb') as f:
        header = f.read(32) # Заголовок файла
        sig = header[:2] # Сигнатура
        version = header[2:4] # Версия
        total_files = struct.unpack('<HH', header[4:8])[0] # Кол-во изображений в файле
        file_info_size = total_files * 32 # Размер структуры с информацией о каждом изображении

        if sig != b'NL':
            print("[ОШИБКА] Формат файла не NL!")
            return 0
        if version != b'\x00\x01':
            print("[ОШИБКА] Неправильная версия NL файл!")
            return 0

        key = struct.unpack('<H', header[16:18])[0] # Достаем ключ для расшифровки
        data = bytearray(f.read(file_info_size)) # Получаем байты структуры с информацией о изображениях
        nl_decrypt(data, key)
        
        # Работа со структурой с информацией о изображениях
        files = []
        for i in range(total_files):
            entry = struct.unpack_from('<12sIHHII', data, i * 32) # Получение массива с информацией о изображении ([Название файла], [Идентификатор], 0, [Размер изображения в байтах (включая заголовок)], [Начало смещения])
            files.append(entry)
            #print(f'Файл {i+1}: {entry}')
        
        # Достаем данные о изображении и создаем изображение
        for i in range(len(files)):
            if (files[i][5] == 0): # Проверка на наличие поврежденных изображений (если начало смещения == 0) на всякий случай, но в данной игре встречается только одно повреждение (в 00000330.nl)
                print(f"[ВНИМАНИЕ] ({basename}) Обнаружено поврежденное изображение (начало смещения = 0)! Пропускаем...")
                continue
            if (i != 0 and files[i][4] <= 32): # Если сцена в игре не имеет своего основного фона, то он имеет заглушку (например, в 00000300.nl). 
                continue
    
            f.seek(files[i][5])
            pallete = f.read(files[i][4]-32)
            raw_size = f.read(16)
            width = struct.unpack('I', raw_size[8:12])[0]
            height = struct.unpack('I', raw_size[12:])[0]
            dib_info = f.read(16)
            if (dib_info[4:5] == b'\x08'):
                dword_input = list(struct.unpack("<%dI" % ((len(pallete)) // 4), pallete))
                pallete = decode_ngi_dib_rle_to_8888(dword_input, width, height)
            image_name = files[i][0].decode("UTF-8")
            if (width == 0 or height == 0):
                print(f"[ОШИБКА] ({basename} - {image_name}) Изображение имеет неправильное разрешение! ({width}x{height})")
                continue

            print(f"Текущий NL файл: {basename}       \nПрогресс: {i}/{len(files)}             \nРаспаковка {image_name}...\033[2F\r", end='')
            result_code = save_rgba_image(pallete, width, height, f"{save_path}/{image_name}.png")
            if (result_code == 2):
                print(f"[ВНИМАНИЕ] ({basename} - {image_name}) Получившихся пикселей больше, чем требуется! Изображение обрезано.")
            elif (result_code == -1):
                print("[ОШИБКА] ({basename} - {image_name}) Получившихся пикселей меньше, чем требуется! Изображение не сохранено.")

if __name__ == "__main__":
    count_detected = 0
    detected_nl = []
    
    for filePath in os.listdir():
        fileName, fileExtension = os.path.splitext(filePath)
        if (fileExtension == ".nl"):
            count_detected += 1
            detected_nl.append(filePath)
    print("Обнаружено NL файлов:", count_detected)

    for filePath in detected_nl:
        extract_images(filePath)
        print("\n\n\nГотово! Изображения сохранены в", output_path)