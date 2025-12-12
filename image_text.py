import os.path
import random
from PIL import Image, ImageDraw, ImageFont
import logging
import numpy as np


def calculate_luminance(rgb_color):
    r, g, b = rgb_color[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def get_text_color(background_color):
    luminance = calculate_luminance(background_color)
    if luminance > 128:
        return (74, 74, 74)
    else:
        return (255, 255, 255)


def add_text_with_rounded_background(text, image_path, font_size=200):
    try:
        if not os.path.exists(image_path):
            logging.error(f"Файл зображення не знайдено: {image_path}")
            return None

        font_path = "SFPRODISPLAYMEDIUM.OTF"

        if not os.path.exists(font_path):
            logging.error(f"Файл шрифту не знайдено за шляхом: {font_path}")
            return None

        image = Image.open(image_path).convert("RGBA")
        (width, height) = image.size

        text_position = (int(width / 2), int(height * 0.75))

        pixel_color = image.getpixel((int(width / 2), int(height / 2)))

        font = ImageFont.truetype(font_path, font_size)

        text_color = get_text_color(pixel_color)

        draw = ImageDraw.Draw(image)

        text_bbox = draw.textbbox((0, 0), text, font=font)

        padding = font_size // 2
        box_width = text_bbox[2] - text_bbox[0] + padding * 2
        box_height = text_bbox[3] - text_bbox[1] + padding * 2

        background = Image.new("RGBA", (box_width, box_height), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(background)

        bg_draw.rounded_rectangle([0, 0, box_width, box_height], radius=20, fill=pixel_color)

        text_layer = Image.new("RGBA", (box_width, box_height), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_layer)

        text_draw.text((padding, padding), text, font=font, fill=text_color)

        rotated_text = text_layer.rotate(random.randint(-3, 3), expand=1)
        rotated_background = background.rotate(random.randint(-3, 3), expand=1)

        rotated_position = (text_position[0] - rotated_text.size[0] // 2, text_position[1] - rotated_text.size[1] // 2)

        image.paste(rotated_background, rotated_position, rotated_background)
        image.paste(rotated_text, rotated_position, rotated_text)

        output_path = image_path
        image.save(output_path, "PNG")

        logging.info(f"Текст додано до зображення: {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Помилка у функції add_text_with_rounded_background: {e}")
        return None
