import os
from feynman_img_convert import convert_svg_to_pdf

def batch_convert(img_dir):
    """Convert all SVG/SVGZ files in directory to PDF."""
    files = [f for f in os.listdir(img_dir) if f.endswith('.svg') or f.endswith('.svgz')]
    print(f'[LOG] Found {len(files)} SVG/SVGZ files to convert.')
    for f in files:
        input_path = os.path.join(img_dir, f)
        output_path = os.path.join(img_dir, f.replace('.svgz', '.pdf').replace('.svg', '.pdf'))
        if os.path.exists(output_path):
            print(f'[SKIP] {f} already converted.')
            continue
        print(f'[LOG] Converting {f}...')
        if convert_svg_to_pdf(input_path, output_path):
            print(f'[OK] Converted {f} to PDF.')
        else:
            print(f'[ERR] Failed to convert {f}')

if __name__ == '__main__':
    batch_convert('feynman_json/images')