"""Create artificial camera labels for checking the app. No real device data."""
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_PATHS = ['/System/Library/Fonts/Supplemental/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/arial.ttf']
font_path = next((p for p in FONT_PATHS if Path(p).exists()), None)


def make_label(path, lines, rotation=0):
    font = ImageFont.truetype(font_path, 32) if font_path else ImageFont.load_default(size=32)
    image = Image.new('RGB', (1100, 500), '#f9f9f5')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 1082, 482), radius=18, outline='#a8aba3', width=2)
    for i, line in enumerate(lines):
        draw.text((55, 45 + i * 56), line, font=font, fill='#151515')
    image.rotate(rotation, expand=True).save(path)


if __name__ == '__main__':
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'ukazkove-stitky'
    target.mkdir(parents=True, exist_ok=True)
    make_label(target / 'kamera-01.png', ['HIKVISION', 'Model: DS-2CD2043G2-I', 'S/N: 000123456789', 'MAC: A4:14:37:00:12:AB', 'Power: 12 V DC, 0.5 A', 'IP Address: 192.168.1.64', 'DEMO LABEL - NOT A REAL DEVICE'])
    make_label(target / 'kamera-02-otocena.png', ['DAHUA', 'Model: IPC-HFW1234', 'S/N: 000987654321', 'MAC: 00-11-22-33-44-55', 'Power: 12 V DC', 'DEMO LABEL - NOT A REAL DEVICE'], 90)
    print(target)
