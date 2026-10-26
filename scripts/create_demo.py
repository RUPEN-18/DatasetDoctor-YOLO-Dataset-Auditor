"""Create small synthetic PPE-like illustrations with deliberate audit issues.
No real people, photos or external datasets are used.
"""
from pathlib import Path
import random
import shutil
import sys
from PIL import Image, ImageDraw


def make_demo(root: Path):
    if root.exists():
        raise ValueError(f'Destination already exists: {root}. Choose a new folder.')
    for split in ['train', 'valid', 'test']:
        (root / split / 'images').mkdir(parents=True)
        (root / split / 'labels').mkdir(parents=True)
    (root / 'data.yaml').write_text('train: train/images\nval: valid/images\ntest: test/images\nnc: 2\nnames: [Safety-Helmet, Reflective-Jacket]\n', encoding='utf-8')
    rng = random.Random(18)
    for n in range(1, 37):
        split = 'train' if n <= 26 else ('valid' if n <= 33 else 'test')
        path = root / split / 'images' / f'site_{n:03}.png'
        im = Image.new('RGB', (800, 500), (220 + n % 15, 231, 235))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 330, 800, 500), fill='#b8c7cc')
        d.line((0, 330, 800, 330), fill='#8eaaae', width=3)
        for x in [65, 680]:
            d.rectangle((x, 55, x + 22, 330), fill='#9bb6bd')
        d.line((45, 55, 740, 55), fill='#a8bec4', width=12)
        d.rectangle((38, 363, 180, 458), fill='#d7aa70')
        d.rectangle((48, 373, 170, 448), outline='#b58a54', width=2)
        d.text((40, 23), f'SYNTHETIC SITE / {n:03}  -  DATASET DOCTOR DEMO', fill='#435a68')
        x = 330 + rng.randint(-85, 85)
        d.rounded_rectangle((x - 43, 220, x + 43, 360), radius=20, fill='#3f6076')
        d.rounded_rectangle((x - 40, 345, x - 10, 456), radius=12, fill='#3a5265')
        d.rounded_rectangle((x + 10, 345, x + 40, 456), radius=12, fill='#3a5265')
        d.ellipse((x - 30, 141, x + 30, 212), fill='#c68f6a')
        # Helmet box: x ± 43, y=127..173.
        d.pieslice((x - 39, 114, x + 39, 183), 180, 360, fill='#efbc36')
        d.rounded_rectangle((x - 43, 157, x + 43, 173), radius=4, fill='#e6a722')
        helmet = f'0 {x/800:.6f} {150/500:.6f} {86/800:.6f} {46/500:.6f}'
        rows = [helmet]
        if n % 7 == 0:
            d.polygon([(x-40,220),(x+40,220),(x+35,350),(x-35,350)], fill='#d5e94a')
            d.line((x, 220, x, 350), fill='#667f58', width=4)
            d.rectangle((x-36,277,x+36,289), fill='#f5f6d5')
            rows.append(f'1 {x/800:.6f} {285/500:.6f} {80/800:.6f} {130/500:.6f}')
        if n == 2:
            rows.append(helmet)  # duplicate annotation
        if n == 4:
            rows.append('3 0.5 0.5 0.2 0.2')  # invalid class
        if n == 6:
            rows.append('1 0.97 0.5 0.4 0.3')  # edges outside image
        if n == 9:
            rows.append('0 0.5 0.5 0.2')  # missing coordinate
        if n == 10:
            rows.append('0 nan 0.4 0.2 0.1')
        im.save(path)
        if n == 11:
            continue  # deliberately missing label
        if n == 12:
            # An actual empty scene is a valid background; keep it for review.
            bg = Image.new('RGB', (800, 500), '#cfdee2')
            ImageDraw.Draw(bg).text((40, 30), 'EMPTY SCENE - REVIEW AS BACKGROUND', fill='#486774')
            bg.save(path)
            rows = []
        (root / split / 'labels' / f'site_{n:03}.txt').write_text('\n'.join(rows) + ('\n' if rows else ''), encoding='utf-8')
    # Exact duplicate inside train and across train/validation.
    for split, name, source in [('train','copy_001', 'site_001'), ('valid','leaked_003','site_003')]:
        shutil.copy2(root / 'train/images' / f'{source}.png', root / split / 'images' / f'{name}.png')
        shutil.copy2(root / 'train/labels' / f'{source}.txt', root / split / 'labels' / f'{name}.txt')
    (root / 'test/images/broken.png').write_bytes(b'This is intentionally not a valid PNG image.')
    (root / 'test/labels/broken.txt').write_text('0 0.5 0.5 0.2 0.2\n', encoding='utf-8')
    (root / 'train/labels/orphan.txt').write_text('0 0.5 0.5 0.2 0.2\n', encoding='utf-8')
    return root


if __name__ == '__main__':
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'demo_dataset'
    print(make_demo(target))
